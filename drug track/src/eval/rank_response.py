"""Evaluate an abstaining one-token clinical response ranker on loopback."""
import argparse
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from urllib.request import Request

from clinical_response import CLINICAL_CUES, explicit_clinical_scope, indexed, shortlist
from gate_local import paired_gain, score
from predict_full import LOCAL_HTTP, PRODUCT_NAMES, split, write_atomic

CODES = {" A": 1, " B": -1, " C": 0, " D": None}
PATIENT_OUTCOME = re.compile(
    r"\b(?:response|responded|remission|tumou?r (?:regression|shrinkage)|"
    r"(?:overall|progression-free|median) survival|(?:rw)?(?:PFS|OS|ORR|DCR|TTNT)|"
    r"disease (?:progression|control)|progressive disease|stable disease|clinical benefit|"
    r"(?:primary|efficacy) end\s?point|improved efficacy)\b", re.I
)
MECHANISM = re.compile(
    r"\b(?:assays?|cellular|cell lines?|(?:kinase |compound )?library|"
    r"molecular docking|synergi[sz]\w*|mechanism in mediating|signaling pathway)\b", re.I
)
DIRECTION_CUES = {
    1: re.compile(r"\b(?:responded|(?:partial|complete|durable|measurable|radiological|clinical|near-complete) response|"
                  r"response to|benefit|improv\w*|prolong\w*|regression|remission|"
                  r"disease control|better|longer|higher (?:objective )?response)\b", re.I),
    -1: re.compile(r"\b(?:progress\w*|resistan\w*|failed|failure|worse|shorter|"
                   r"no response|did not meet|inferior)\b", re.I),
    0: re.compile(r"\b(?:comparable|similar|stable disease|equivalent|"
                  r"no (?:significant )?differences?|did not differ)\b", re.I),
}
SECTION = re.compile(
    r"\b(BACKGROUND|INTRODUCTION|METHODS|RESULTS|FINDINGS|CASE DESCRIPTION|"
    r"CASE PRESENTATION|CONCLUSIONS?)\s*:", re.I
)
OBSERVED_FAILURE = re.compile(
    r"\b(?:developed|experienced|had|showed|documented|revealed) "
    r"(?:a |an )?(?:[\w-]+ ){0,3}(?:recurrence|progression|progressive disease)\b"
    r"|\b(?:progressed|recurred) (?:on|during|despite|while receiving)\b", re.I
)
TASK = (
    "Classify the observed clinical effect of the target drug in the evidence sentence. "
    "Background, plans, nonclinical assays, safety alone, or effects of an unrelated treatment are unsupported. "
    "Use preceding context only to resolve which treatment the evidence refers to. "
    "Improved response or survival favors the target. Progression on the target or a better explicit "
    "comparator is unfavorable. Similar outcomes or stable disease are neutral. "
    "A = favorable, B = unfavorable, C = neutral, D = unsupported."
)


def scores(url, prompt, cache, chat=False):
    payload = {"prompt": prompt, "n_predict": 1, "n_probs": 256, "temperature": -1,
               "post_sampling_probs": False, "cache_prompt": True}
    key = hashlib.sha256(url.encode() + json.dumps(payload).encode() + (b"chat" if chat else b"")).hexdigest()
    path = cache / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    if chat:
        template = {"messages": [{"role": "user", "content": prompt}],
                    "chat_template_kwargs": {"enable_thinking": False}}
        req = Request(url.removesuffix("/completion") + "/apply-template", json.dumps(template).encode(),
                      {"Content-Type": "application/json"})
        with LOCAL_HTTP.open(req, timeout=15) as response:
            payload["prompt"] = json.load(response)["prompt"]
        payload["n_probs"] = 1024
    req = Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with LOCAL_HTTP.open(req, timeout=45) as response:
        reply = json.load(response)
    alternatives = reply["completion_probabilities"][0]["top_logprobs"]
    if chat:
        # The supervised answer has no leading space. The model may add one.
        result = {}
        for code in CODES:
            mass = sum(math.exp(a["logprob"]) for a in alternatives
                       if a["token"] in {code, code.strip()})
            if mass:
                result[code] = math.log(mass)
    else:
        result = {a["token"]: a["logprob"] for a in alternatives if a["token"] in CODES}
    write_atomic(path, json.dumps(result))
    return result


def background_units(row, units):
    """Identify background units when the paper itself reports target-linked failure."""
    headings = list(SECTION.finditer(row["text"]))
    sections = {}
    for _, unit, sentence, _ in units:
        start = row["text"].find(sentence)
        active = [h[1].upper() for h in headings if h.start() <= start]
        sections[unit] = active[-1] if active else None
    found_failure = any(
        sections[unit] in {"RESULTS", "FINDINGS", "CASE DESCRIPTION", "CASE PRESENTATION", "CONCLUSION", "CONCLUSIONS"}
        and explicit_clinical_scope(row, sentence) and OBSERVED_FAILURE.search(sentence)
        and not re.search(r"\b(?:no|without) (?:\w+ ){0,2}(?:progression|recurrence)\b", sentence, re.I)
        for _, unit, sentence, _ in units
    )
    return {unit for unit, section in sections.items() if found_failure and section in {"BACKGROUND", "INTRODUCTION"}}


def propose(row, url, cache, prior, clinical_scope=False, chat=False, observed=False,
            grounded_sign=False, prioritize_study=False):
    target = PRODUCT_NAMES[row["product"]]
    proposals = []
    units = shortlist(row, broad=True)
    if prioritize_study:
        full = split(row["text"], max_words=100000, separate_clauses=False)
        blocked = background_units(row, [(False, u["id"], u["text"], "") for u in full])
    else:
        blocked = set()
    for _, unit, sentence, prev in units:
        if not CLINICAL_CUES.search(sentence):
            continue
        if clinical_scope and not explicit_clinical_scope(row, sentence):
            continue
        if observed and (not PATIENT_OUTCOME.search(sentence) or MECHANISM.search(sentence)):
            continue
        prompt = f"{TASK}\nTarget: {target}\nPreceding context: {prev}\nEvidence: {sentence}\nAnswer:"
        raw = scores(url, prompt, cache, chat=chat)
        if raw.keys() != CODES.keys():
            continue
        ranked = sorted(((raw[k] - prior[k], k) for k in CODES), reverse=True)
        (best, code), (next_best, _) = ranked[:2]
        if (code != " D" and (unit not in blocked or CODES[code] != 1)
                and (not grounded_sign or DIRECTION_CUES[CODES[code]].search(sentence))):
            proposals.append({"unit": unit, "span": sentence.rstrip(" .!?;"),
                              "polarity": CODES[code], "margin": best - next_best})
    return max(proposals, key=lambda x: x["margin"], default=None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("items")
    parser.add_argument("out", type=Path)
    parser.add_argument("--baseline")
    parser.add_argument("--gold")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--paired", action="store_true")
    parser.add_argument("--raw", action="store_true", help="Ablate content-free score subtraction")
    parser.add_argument("--clinical-scope", action="store_true")
    parser.add_argument("--chat", action="store_true", help="Render the runtime chat template before scoring")
    parser.add_argument("--observed", action="store_true", help="Require an explicit clinical outcome cue")
    parser.add_argument("--grounded-sign", action="store_true", help="Require wording supporting the predicted direction")
    parser.add_argument("--prioritize-study", action="store_true", help="Prefer the paper's observed outcome over background")
    parser.add_argument("--favorable-only", action="store_true", help="Allow only favorable additions after ranking")
    parser.add_argument("--predict-only", action="store_true", help="Write predictions without reading labels")
    args = parser.parse_args()
    if args.predict_only and not args.baseline:
        parser.error("Prediction mode requires an existing baseline file")
    items = indexed(args.items)
    baseline = indexed(args.baseline) if args.baseline else {k: {"efficacy": None} for k in items}
    if items.keys() != baseline.keys():
        parser.error("Item and baseline IDs must match")
    candidate = {k: dict(r) for k, r in baseline.items()}
    args.out.mkdir(parents=True, exist_ok=True)
    cache = args.out.parent / "rank-cache"
    cache.mkdir(exist_ok=True)
    url = f"http://127.0.0.1:{args.port}/completion"
    if args.raw:
        prior = dict.fromkeys(CODES, 0)
    else:
        prior = scores(url, f"{TASK}\nTarget: N/A\nPreceding context: N/A\nEvidence: N/A\nAnswer:", cache, args.chat)
        if prior.keys() != CODES.keys():
            parser.error("Runtime did not return scores for all four single-token codes")
    audit = []
    for key, row in items.items():
        if row["source"] != "pubmed" or baseline[key]["efficacy"] is not None:
            continue
        proposal = propose(row, url, cache, prior, args.clinical_scope, args.chat,
                           args.observed, args.grounded_sign, args.prioritize_study)
        accepted = bool(proposal and proposal["margin"] >= math.log(2) and
                        (not args.favorable_only or proposal["polarity"] == 1))
        if accepted:
            candidate[key]["efficacy"] = {k: proposal[k] for k in ("span", "polarity")}
            candidate[key]["efficacy"]["speaker"] = "researcher"
        audit.append({"item_id": key, "proposal": proposal, "accepted": accepted})
    write_atomic(args.out / "audit.json", json.dumps(audit, indent=2) + "\n")
    report = {"eligible": len(audit), "changes": sum(r["accepted"] for r in audit)}
    if args.baseline:
        if not args.predict_only:
            gold = indexed(args.gold) if args.gold else items
            report["all"] = score(gold, candidate, items)
            report["baseline"] = score(gold, baseline, items)
            reviewed = {k: r for k, r in gold.items() if r.get("human_reviewed") or
                        r.get("label_origin") == "reviewed_60"}
            if reviewed:
                report["human_reviewed_only"] = score(reviewed, candidate, items)
            report["correct"] = sum(bool(gold[r["item_id"]]["efficacy"] and
                                         gold[r["item_id"]]["efficacy"]["polarity"] == r["proposal"]["polarity"])
                                    for r in audit if r["accepted"])
            if args.paired:
                report["paired_win"] = paired_gain(gold, items, baseline, candidate)
        write_atomic(args.out / "predictions.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n"
                                                            for r in candidate.values()))
    else:
        groups = {}
        for key, row in items.items():
            value = candidate[key]["efficacy"]
            groups.setdefault(row["group"], []).append((value["polarity"] if value else None) == row["expected"])
        report["correct"] = sum(sum(g) for g in groups.values())
        report["pairs"] = sum(all(g) for g in groups.values())
        report["groups"] = groups
    write_atomic(args.out / "score.json", json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
