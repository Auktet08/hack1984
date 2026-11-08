"""Run Rules L3 with opt-in clause-grounded local model predictions."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
from clauses import split, trim
from rules.predict import ASP, CUES, SPEAKER, predict

SOURCES = {"pubmed", "news", "press_release", "fda_label"}
SIGNALS = ["efficacy", "safety", "regulatory", "trial_update", "competitor_move",
           "access_pricing", "guideline", "expert_opinion", "none"]
GROUPS = ("aspects", "signal", "actionable")
SIGNAL_SOURCES = {"pubmed", "news"}
SPEAKERS = {*SPEAKER.values(), "hcp", "patient", "payer"}
PRODUCT_NAMES = {
    "A": "Tagrisso (osimertinib)",
    "B": "Rybrevant or Rybrevant Faspro (amivantamab), with or without Lazcluze (lazertinib)",
    "both": "Tagrisso (osimertinib) and Rybrevant or Rybrevant Faspro with Lazcluze",
}
PRODUCT_MENTIONS = {
    "A": r"\b(?:tagrisso|osimertinib)\b",
    "B": r"\b(?:rybrevant|amivantamab|lazcluze|lazertinib)\b",
}
ADMINISTRATION = re.compile(r"\b(?:infusions?|injections?|dosing|administration|tablets?)\b", re.I)
BURDEN = re.compile(
    r"\bmade (?:treatment|dosing|administration) (?:much )?"
    r"(?P<direction>easier|harder|more convenient|less convenient|more burdensome|less burdensome)\b", re.I
)
UNCERTAIN_JUDGMENT = re.compile(r"\b(?:not|never|whether|doubt|unclear|may|might)\b", re.I)
TRANSCRIPT_GUIDE = (
    "The track products are A: Tagrisso (osimertinib) and B: Rybrevant or Rybrevant Faspro "
    "(amivantamab) with Lazcluze (lazertinib). If a different target drug is specified, use it. "
    "For each aspect, choose the shortest unit that contains the actual claim and its direction. "
    "A trial name, design, or background alone is not evidence of efficacy. Look for the outcome "
    "and whether it improved, worsened, or stayed the same. Use safety for adverse effects or "
    "tolerability. A change in administration, dose schedule, time, or burden is convenience. "
    "Always include convenience when the speaker explicitly says treatment became easier or "
    "more burdensome, even if actionable is no. Easier treatment is positive convenience. "
    "Use access_cost only for explicit coverage, affordability, reimbursement, or availability. "
    "For an isolated adverse event use safety and actionable no. For administration experience "
    "with no other signal type, use expert_opinion and judge convenience when the speaker does. "
    'For example, "The weekly home injection saved me three clinic visits" judges convenience +1. '
    '"My insurance refused to cover the treatment" judges access_cost -1.'
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


LOCAL_HTTP = build_opener(ProxyHandler({}), NoRedirect())


def load_rows(path):
    with Path(path).open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def write_atomic(path, text):
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
        temp = Path(file.name)
        try:
            file.write(text)
            file.close()
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)


def schema(units):
    fields = {"unit_id": {"type": "integer", "enum": [u["id"] for u in units]},
              "aspect": {"type": "string", "enum": ASP},
              "polarity": {"type": "integer", "enum": [-2, -1, 0, 1, 2]}}
    props = {"signal_type": {"type": "string", "enum": SIGNALS},
             "actionable": {"type": "string", "enum": ["yes", "no"]},
             "aspects": {"type": "array", "maxItems": 5, "items": {
                 "type": "object", "properties": fields, "required": list(fields),
                 "additionalProperties": False}}}
    return {"type": "object", "properties": props, "required": list(props),
            "additionalProperties": False}


def prompt(row, units, guide=""):
    evidence = "\n".join(f'{u["id"]}: {u["text"]}' for u in units)
    return (
        'Label only the supplied evidence about the target product. Return only JSON with '
        'signal_type, actionable ("yes" or "no"), and aspects (list of objects with unit_id, '
        'aspect and integer polarity -2 through 2). Include one unit per judged aspect. '
        'Use an empty aspects list if the text makes no judgment.\n'
        f'Signal types: {", ".join(SIGNALS)}. Aspects: {", ".join(ASP)}.\n'
        f'{guide}\nSource: {row["source"]}\nProduct: {row["product"]}\nTitle: {row["title"]}\n'
        f'Evidence units:\n{evidence}'
    )


def parse(content, units):
    content = re.sub(r"^\s*<think>.*?</think>", "", content, flags=re.S).strip()
    content = re.sub(r"^\x60\x60\x60(?:json)?\s*|\s*\x60\x60\x60$", "", content)
    data = json.loads(content)
    if (not isinstance(data, dict) or data.get("signal_type") not in SIGNALS
            or data.get("actionable") not in ("yes", "no") or not isinstance(data.get("aspects"), list)):
        raise ValueError("Invalid model fields")
    valid = []
    for a in data["aspects"]:
        if (not isinstance(a, dict) or a.get("aspect") not in ASP
                or type(a.get("unit_id")) is not int or not 0 <= a["unit_id"] < len(units)
                or type(a.get("polarity")) is not int or not -2 <= a["polarity"] <= 2):
            raise ValueError("Invalid model aspect")
        valid.append(a)
    return {**data, "aspects": valid}


def add_aspects(text, base, model, units, speaker, guard_polarity):
    for a in model["aspects"]:
        name = a["aspect"]
        if base[name] is not None:
            continue
        unit = units[a["unit_id"]]
        start, end = trim(text, unit["start"], unit["end"])
        span = text[start:end]
        polarity = a["polarity"]
        if guard_polarity and abs(polarity) == 2 and not any(
            aspect == name and cue == polarity and re.search(pattern, span, re.I)
            for aspect, cue, pattern in CUES
        ):
            polarity = 1 if polarity > 0 else -1
        base[name] = {"span": span, "polarity": polarity, "speaker": speaker}


def can_override_signal(row, base):
    return row["source"] in SIGNAL_SOURCES and base["signal_type"] == "efficacy"


def merge(row, base, model, units, groups):
    if "aspects" in groups:
        add_aspects(row["text"], base, model, units, SPEAKER[row["source"]], guard_polarity=True)
    if "signal" in groups and can_override_signal(row, base):
        base["signal_type"] = model["signal_type"]
    if "actionable" in groups and model["actionable"] == "yes":
        base["actionable"] = "yes"
    return base


def explicit_convenience(row, units, speaker):
    product = row["product"]
    mention = "|".join(PRODUCT_MENTIONS.values()) if product == "both" else PRODUCT_MENTIONS.get(product)
    if mention is None:
        mention = rf"\b{re.escape(product)}\b"
    for unit in units:
        text = unit["text"]
        judgment = BURDEN.search(text)
        if (judgment and ADMINISTRATION.search(text) and re.search(mention, text, re.I)
                and not UNCERTAIN_JUDGMENT.search(text[:judgment.start()])):
            negative = judgment["direction"].lower() in {"harder", "less convenient", "more burdensome"}
            return {"span": judgment.group(0), "polarity": -1 if negative else 1, "speaker": speaker}
    return None


def label_local(row, url, model, cache, guide=""):
    """Label a transcript turn or a separate product's evidence on the local server."""
    transcript = row["source"] == "transcript"
    units = split(row["text"], max_words=32, separate_clauses=False) if transcript else split(row["text"])
    if transcript:
        guide = f'{guide}\nSpeaker role: {row.get("speaker_role", "unknown")}. {TRANSCRIPT_GUIDE}'
    model_row = {**row, "product": PRODUCT_NAMES.get(row["product"], row["product"])} if transcript else row
    result = call(url, model, prompt(model_row, units, guide), units, cache, plain=False)
    label = {"item_id": row["item_id"], "signal_type": result["signal_type"],
             "actionable": result["actionable"], **dict.fromkeys(ASP)}
    speaker = row.get("speaker_role") if transcript else SPEAKER.get(row["source"])
    if speaker in SPEAKERS:
        add_aspects(row["text"], label, result, units, speaker, guard_polarity=False)
        if transcript and label["convenience"] is None:
            label["convenience"] = explicit_convenience(row, units, speaker)
            if label["convenience"] is not None and label["signal_type"] == "none":
                label["signal_type"] = "expert_opinion"
    return label


def call(url, model, message, units, cache, plain):
    if urlparse(url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("The model endpoint must be on this machine")
    payload = {"model": model, "messages": [{"role": "user", "content": message}],
               "temperature": 0, "max_tokens": 768, "chat_template_kwargs": {"enable_thinking": False}}
    if not plain:
        payload["response_format"] = {"type": "json_schema", "json_schema": {
            "name": "prediction", "strict": True, "schema": schema(units)}}
    body = json.dumps(payload).encode()
    key = hashlib.sha256(url.encode() + body).hexdigest()
    path = cache / f"{key}.json"
    if path.exists():
        return parse(json.loads(path.read_text()), units)
    req = Request(url, data=body, headers={"Content-Type": "application/json"})
    with LOCAL_HTTP.open(req, timeout=120) as response:
        content = json.load(response)["choices"][0]["message"]["content"]
    result = parse(content, units)
    write_atomic(path, json.dumps(content))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("items")
    ap.add_argument("out", type=Path)
    ap.add_argument("--url", default="http://127.0.0.1:18080/v1/chat/completions")
    ap.add_argument("--model", default="qwen3.5-2b")
    ap.add_argument("--cache", type=Path, default=Path("out/model_cache"))
    ap.add_argument("--guide", type=Path)
    ap.add_argument("--plain", action="store_true")
    ap.add_argument("--transcripts", action="store_true", help="Label transcript turns with the selected model")
    for group in GROUPS:
        ap.add_argument(f"--model-{group}", action="store_true")
    args = ap.parse_args()
    if urlparse(args.url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        ap.error("The model endpoint must be on this machine")
    groups = {g for g in GROUPS if getattr(args, f"model_{g}")}
    guide = args.guide.read_text(encoding="utf-8") if args.guide else ""
    rows = load_rows(args.items)
    if len({r["item_id"] for r in rows}) != len(rows) or any(not r.get("text") for r in rows):
        ap.error("Inputs must have unique item IDs and complete text")
    args.cache.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    failures = calls = 0
    predictions = []
    for row in rows:
        base = predict(row, 3)
        if args.transcripts and row["source"] == "transcript":
            calls += 1
            base = label_local(row, args.url, args.model, args.cache, guide)
        elif row["source"] in SOURCES and (
            ("aspects" in groups and any(base[aspect] is None for aspect in ASP))
            or ("signal" in groups and can_override_signal(row, base))
            or ("actionable" in groups and base["actionable"] == "no")
        ):
            calls += 1
            units = split(row["text"])
            try:
                model = call(args.url, args.model, prompt(row, units, guide), units, args.cache, args.plain)
                base = merge(row, base, model, units, groups)
            except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
                failures += 1
                print(f'{row["item_id"]}: {error}', file=sys.stderr, flush=True)
        predictions.append(json.dumps(base, ensure_ascii=False) + "\n")
    write_atomic(args.out, "".join(predictions))
    print(f"{len(rows)} rows, {calls} model items, {failures} rules fallbacks", file=sys.stderr)


if __name__ == "__main__":
    main()
