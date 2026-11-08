"""Evaluate a selective PubMed response extractor without changing release outputs."""
import argparse
import hashlib
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request

from gate_local import indexed, paired_gain, score
from predict_full import LOCAL_HTTP, PRODUCT_MENTIONS, PRODUCT_NAMES, load_rows, split, write_atomic
from filter_efficacy import grounded_outcome

URL = "http://127.0.0.1:18083/v1/chat/completions"
OUTCOME = re.compile(
    r"\b(?:responded|responses?|regression|tumou?r shrank|disease control|stable disease|"
    r"progress(?:ed|ion)|survival|mortality|PFS|OS|benefit|remission)\b", re.I
)
CLINICAL_CUES = re.compile(
    r"\b(?:respond\w*|responses?|regress\w*|shr[au]nk|remission|progress\w*|resistan\w*|"
    r"surviv\w*|mortality|(?:rw)?(?:PFS|OS|ORR|TTNT)|benefit|efficac\w*|"
    r"(?:disease|tumou?r|symptom|CNS) (?:control|stabili\w*|reduction|improvement)|"
    r"stable disease|met (?:the |its )?(?:primary )?endpoint)\b", re.I
)
OBSERVED = re.compile(
    r"\b(?:achieved|showed|experienced|developed|observed|documented|improved|"
    r"prolonged|reduced|reported|comparable|similar|versus|compared|after|during|despite)\b", re.I
)
HYPOTHETICAL_OR_NONCLINICAL = re.compile(
    r"\b(?:aim(?:s|ed)? to|would|might|could|whether|planned|in vitro|mice|"
    r"murine|xenografts?|cell lines?|not|never|no)\b", re.I
)
OUT_OF_CLINICAL_SCOPE = re.compile(
    r"^(?:OBJECTIVES?|METHODS?|PURPOSE):|\b(?:in vitro|cell lines?|xenografts?|"
    r"mice|murine|aim(?:s|ed)? to|designed to|suggested included|potential therapeutic approach)\b",
    re.I,
)
NEUTRAL_COMPARISON = re.compile(
    r"\b(?:no (?:statistically |significant |statistically significant )?differences? "
    r"in (?:the )?(?:PFS|OS|progression-free survival|overall survival|response rates?)|"
    r"(?:PFS|OS|progression-free survival|overall survival|response rates?) "
    r"(?:did not differ(?: significantly)?|(?:was|were) (?:similar|comparable))|"
    r"comparable (?:effectiveness|survival|progression-free survival|overall survival))\b", re.I
)
PROMPT = """Classify the effect of the target treatment on a clinical outcome using these excerpts.
Use UNSUPPORTED if none states an observed patient outcome for the target. A plan, study aim, toxicity,
molecular or animal result, or outcome for a different drug does not establish efficacy. A favorable
outcome for a comparator is unfavorable for the target only if the two groups are explicitly compared.
Stable disease or comparable outcomes are neutral. Death or progression unrelated to target treatment
does not establish unfavorable efficacy. Check for uncertainty and negation.
Return a verdict, evidence unit, exact contiguous quote from that unit, and strength (ordinary or strong).
Only use strong for clearly exceptional or explicitly strong results under the task guide.
For UNSUPPORTED use unit -1, an empty quote, and ordinary strength."""


def target_pattern(row):
    key = row["product"]
    return "|".join(PRODUCT_MENTIONS.values()) if key == "both" else PRODUCT_MENTIONS.get(key, "")


def explicit_clinical_scope(row, evidence):
    pattern = target_pattern(row)
    return bool(pattern and re.search(pattern, evidence, re.I) and not OUT_OF_CLINICAL_SCOPE.search(evidence))


def literal_response(row, units, comparative=False, clinical_failure=False):
    target = target_pattern(row)
    if not target:
        return None, "literal_abstained"
    clinical_response = r"(?:(?:partial|complete|durable|clinical|objective|radiographic) )?response"
    patterns = [
        (rf"\b(?:achieved|had|documented|showed|experienced) (?:a )?{clinical_response} "
         rf"(?:to|on|during treatment with) (?:{target})", 1),
        (rf"\bresponded (?:well |favorably )?to (?:treatment with )?(?:{target})", 1),
        (rf"\b(?:developed|experienced|had|showed) (?:disease |radiographic )?progression "
         rf"(?:despite|on|during treatment with) (?:{target})", -1),
        (rf"\b(?:had|maintained|showed) stable disease (?:on|during treatment with) (?:{target})", 0),
    ]
    if clinical_failure:
        patterns.extend([
            (rf"\b(?:progressed|recurred) (?:on|despite|during treatment with|while receiving) (?:{target})", -1),
            (rf"\bafter (?:\d+(?:\.\d+)? (?:weeks?|months?|years?) (?:of )?)?"
             rf"(?:treatment with )?(?:TKI )?(?:{target})(?: treatment| therapy)?, "
             r"(?:the patient |a |an )?(?:developed |experienced |had )?"
             r"(?:[\w-]+ ){0,3}(?:recurrence|progression)(?: [\w-]+){0,8}?"
             r"(?: was (?:detected|observed|documented))?(?=[,.;]|$)", -1),
        ])
    matches = []
    for _, _, sentence, _ in units:
        if (comparative and row["product"] != "both" and explicit_clinical_scope(row, sentence)
                and NEUTRAL_COMPARISON.search(sentence) and re.search(r"\bbetween\b", sentence, re.I)):
            matches.append((sentence.rstrip(" .!?;"), 0))
        if HYPOTHETICAL_OR_NONCLINICAL.search(sentence):
            continue
        for pattern, polarity in patterns:
            match = re.search(pattern, sentence, re.I)
            if match:
                matches.append((match[0], polarity))
    if not matches or len({polarity for _, polarity in matches}) > 1:
        return None, "literal_abstained"
    span, polarity = matches[0]
    return {"span": span, "speaker": "researcher", "polarity": polarity}, "literal_match"


def shortlist(row, broad=False):
    target = target_pattern(row)
    if not target:
        return []
    units = split(row["text"], max_words=100000, separate_clauses=False)
    if broad:
        ranked = []
        for i, unit in enumerate(units):
            evidence = unit["text"]
            previous = units[i - 1]["text"] if i else ""
            named = bool(re.search(target, evidence, re.I))
            nearby = bool(re.search(target, previous, re.I))
            cues = len(CLINICAL_CUES.findall(evidence))
            if not (named or nearby or cues):
                continue
            rank = 3 * named + nearby + min(cues, 3) + bool(OBSERVED.search(evidence))
            if named and cues:
                rank += 2
            ranked.append((rank, named, i, evidence, previous if not named else ""))
        return [(named, i, evidence, previous) for _, named, i, evidence, previous in
                sorted(ranked, key=lambda u: (-u[0], u[2]))[:8]]
    ranked = []
    for i, unit in enumerate(units):
        evidence = unit["text"]
        previous = units[i - 1]["text"] if i else ""
        named = bool(re.search(target, evidence, re.I))
        if OUTCOME.search(evidence) and (named or re.search(target, previous, re.I)):
            ranked.append((named, i, evidence, previous if not named else ""))
    return sorted(ranked, key=lambda u: (-u[0], u[1]))[:5]


def make_prompt(row, units, pointer):
    target = PRODUCT_NAMES[row["product"]]
    evidence = "\n".join(
        f"Unit {i}: {json.dumps(sentence)}"
        + (f" | preceding context: {json.dumps(previous)}" if previous else "")
        for _, i, sentence, previous in units
    )
    instructions = PROMPT
    if pointer:
        instructions = PROMPT.split("Return a verdict")[0] + (
            "Return the verdict, the unit number, and ordinary or strong strength. "
            "Use unit -1 and ordinary strength for UNSUPPORTED."
        )
    return f"{instructions}\nTarget: {target}\n{evidence}"


def label(row, units, cache, control=False, pointer=False, broad=False,
          url=URL, model="qwen35-2b-lora-v1", attributed=False):
    if control:
        for _, _, sentence, _ in units:
            outcome = grounded_outcome(row, sentence)
            if outcome:
                return outcome, "control_match"
        return None, "control_abstained"
    if not units:
        return None, "retrieval_empty"
    prompt = make_prompt(row, units, pointer)
    fields = {
        "verdict": {"enum": ["UNSUPPORTED", "FAVORABLE", "NEUTRAL", "UNFAVORABLE"]},
        "unit": {"enum": [-1, *[u[1] for u in units]]},
        "quote": {"type": "string"},
        "strength": {"enum": ["ordinary", "strong"]},
    }
    if pointer:
        del fields["quote"]
    payload = {
        "model": model, "temperature": 0, "max_tokens": 80 if pointer else 256,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "response", "schema": {
            "type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}}},
    }
    body = json.dumps(payload).encode()
    path = cache / (hashlib.sha256(url.encode() + body).hexdigest() + ".json")
    if path.exists():
        answer = json.loads(path.read_text())
    else:
        request = Request(url, body, {"Content-Type": "application/json"})
        try:
            with LOCAL_HTTP.open(request, timeout=45) as reply:
                answer = json.loads(json.load(reply)["choices"][0]["message"]["content"])
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            return None, "inference_error"
        if (not isinstance(answer, dict) or set(answer) != set(fields) or
                any(answer[key] not in spec["enum"] for key, spec in fields.items() if "enum" in spec) or
                (not pointer and not isinstance(answer["quote"], str))):
            return None, "inference_error"
        write_atomic(path, json.dumps(answer))
    if answer["verdict"] == "UNSUPPORTED":
        return None, "model_abstained"
    sentence = next((u[2] for u in units if u[1] == answer["unit"]), "")
    span = sentence.rstrip(" .!?;") if pointer else answer["quote"].strip()
    if not span or span not in sentence or not (CLINICAL_CUES if broad else OUTCOME).search(span):
        return None, "invalid_outcome_quote"
    if attributed and not explicit_clinical_scope(row, span):
        return None, "missing_clinical_attribution"
    direction = {"FAVORABLE": 1, "NEUTRAL": 0, "UNFAVORABLE": -1}[answer["verdict"]]
    polarity = direction * (2 if answer["strength"] == "strong" else 1)
    return {"span": span, "speaker": "researcher", "polarity": polarity}, "added"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("items")
    parser.add_argument("out", type=Path)
    parser.add_argument("--baseline")
    parser.add_argument("--gold")
    parser.add_argument("--control", action="store_true")
    parser.add_argument("--literal", action="store_true")
    parser.add_argument("--comparative", action="store_true", help="Include explicit neutral comparisons in the literal control")
    parser.add_argument("--clinical-failure", action="store_true", help="Include explicit observed progression in the literal control")
    parser.add_argument("--pointer", action="store_true")
    parser.add_argument("--broad", action="store_true")
    parser.add_argument("--attributed", action="store_true")
    parser.add_argument("--port", type=int, default=18083)
    parser.add_argument("--model", default="qwen35-2b-lora-v1")
    parser.add_argument("--paired", action="store_true")
    args = parser.parse_args()
    items = indexed(args.items)
    baseline = indexed(args.baseline) if args.baseline else {k: {"efficacy": None} for k in items}
    if items.keys() != baseline.keys():
        parser.error("Item and baseline IDs must match")
    candidate = {k: dict(row) for k, row in baseline.items()}
    args.out.mkdir(parents=True, exist_ok=True)
    cache = args.out.parent / "response-cache"
    cache.mkdir(exist_ok=True)
    eligible = [k for k, row in items.items() if row["source"] == "pubmed" and not baseline[k]["efficacy"]]
    def predict_item(key):
        row = items[key]
        units = shortlist(row, broad=args.broad)
        if args.literal:
            return literal_response(row, units, args.comparative, args.clinical_failure)
        return label(row, units, cache, args.control, args.pointer, args.broad,
                     f"http://127.0.0.1:{args.port}/v1/chat/completions", args.model, args.attributed)

    with ThreadPoolExecutor(max_workers=2) as pool:
        proposed = list(pool.map(predict_item, eligible))
    audit = []
    for key, (value, reason) in zip(eligible, proposed):
        candidate[key]["efficacy"] = value
        audit.append({"item_id": key, "label": value, "reason": reason})
    write_atomic(args.out / "audit.json", json.dumps(audit, indent=2) + "\n")
    report = {"eligible": len(eligible), "counts": dict(Counter(r["reason"] for r in audit))}
    if args.baseline:
        write_atomic(args.out / "predictions.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n"
                                                            for r in candidate.values()))
        gold = indexed(args.gold) if args.gold else items
        report["all"] = score(gold, candidate, items)
        report["baseline"] = score(gold, baseline, items)
        reviewed = {k: r for k, r in gold.items() if r.get("human_reviewed") or
                    r.get("label_origin") == "reviewed_60"}
        if reviewed:
            report["human_reviewed_only"] = score(reviewed, candidate, items)
        changes = [r for r in audit if r["label"]]
        report["changes"] = len(changes)
        report["correct"] = sum(bool(gold[r["item_id"]]["efficacy"] and
                                     gold[r["item_id"]]["efficacy"]["polarity"] == r["label"]["polarity"])
                                for r in changes)
        if args.paired:
            report["paired_win"] = paired_gain(gold, items, baseline, candidate)
    else:
        groups = {}
        for key, row in items.items():
            value = candidate[key]["efficacy"]
            ok = (value["polarity"] if value else None) == row["expected"]
            groups.setdefault(row["group"], []).append(ok)
        report["contrast_groups"] = groups
        report["passed_pairs"] = sum(all(values) for values in groups.values())
    write_atomic(args.out / "score.json", json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
