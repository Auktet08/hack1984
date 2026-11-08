"""Check the startup file contracts: fixtures always, real outputs under out/startup/ when present.

    python3 "drug track/contracts/validate.py"            # fixtures + any real outputs
    python3 "drug track/contracts/validate.py" --fixtures # fixtures only

Beyond the JSON Schemas it checks what a schema can't: every evidence span is an exact substring of its
field at `start`, every quote span appears in its source row (when that row is loadable), and the
cross-field rules (case_id, missing, flag references). Exit code 1 on any error.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

HERE = Path(__file__).resolve().parent
DT = HERE.parent  # "drug track/"
FIX = HERE / "fixtures"
OUT = DT / "out" / "startup"

SCHEMAS = {
    "label_row": "label_row.schema.json",
    "triage_record": "triage_record.schema.json",
    "triage_audit": "triage_audit.schema.json",
    "gap_view": "gap_view.schema.json",
    "label_cost": "label_cost.schema.json",
}

FIXTURES = [
    ("label_row", FIX / "odac_labels.sample.jsonl"),
    ("triage_record", FIX / "triage.sample.jsonl"),
    ("triage_audit", FIX / "triage_audit.sample.jsonl"),
    ("gap_view", FIX / "gap_poziotinib.sample.json"),
    ("label_cost", FIX / "odac.gemini.cost.sample.json"),
]

ASPECTS = ["efficacy", "safety", "convenience", "access_cost", "evidence_quality"]
CRITERIA = ["adverse_event", "suspect_product", "identifiable_patient", "identifiable_reporter"]


def _load_schemas():
    raw = {k: json.loads((HERE / f).read_text()) for k, f in SCHEMAS.items()}
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in raw.values())
    return {k: Draft202012Validator(s, registry=registry) for k, s in raw.items()}


VALIDATORS = _load_schemas()


def real_outputs():
    """Contract files that exist under out/startup/. Intermediates (x.gemini.jsonl, x.items.jsonl,
    x.smoke.jsonl) have more than one dot in the name and are skipped."""
    found = []
    for p in sorted((OUT / "labels").glob("*.jsonl")):
        if p.name.count(".") == 1:
            found.append(("label_row", p))
    found += [("label_cost", p) for p in sorted((OUT / "labels").glob("*.*.cost.json"))]
    found += [("triage_record", p) for p in sorted((OUT / "triage").glob("*.jsonl"))]
    if (OUT / "triage_audit.jsonl").exists():
        found.append(("triage_audit", OUT / "triage_audit.jsonl"))
    found += [("gap_view", p) for p in sorted((OUT / "gap").glob("*.json"))]
    return found


def read_docs(path):
    """List of (line_label, doc). JSONL gives one doc per non-empty line; .json gives one doc."""
    text = Path(path).read_text()
    if str(path).endswith(".jsonl"):
        return [(f"{Path(path).name}:{i}", json.loads(line))
                for i, line in enumerate(text.splitlines(), 1) if line.strip()]
    return [(Path(path).name, json.loads(text))]


def schema_errors(kind, doc):
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in sorted(VALIDATORS[kind].iter_errors(doc), key=lambda e: list(e.absolute_path))]


# ---- semantic checks (run only when the schema passes) ------------------------------------------

def _span_at(haystack, span, start):
    return haystack is not None and haystack[start:start + len(span)] == span


def _check_evidence(ev_list, texts, speaker_name, where):
    errs = []
    for i, ev in enumerate(ev_list):
        if ev["field"] == "text":
            hay = texts.get(ev["item_id"]) if texts is not None else None
            if texts is not None and hay is None:
                errs.append(f"{where}[{i}]: item_id {ev['item_id']} not in texts")
                continue
        else:
            hay = speaker_name
        if hay is not None and not _span_at(hay, ev["span"], ev["start"]):
            errs.append(f"{where}[{i}]: span {ev['span']!r} not at offset {ev['start']} of "
                        f"{ev['item_id']}.{ev['field']}")
    return errs


def check_label_row(doc, ctx):
    errs = []
    for a in ASPECTS:
        v = doc.get(a)
        if v and v["span"] not in doc["text"]:
            errs.append(f"{a}.span {v['span']!r} is not a substring of text")
    return errs


def check_triage_record(doc, ctx):
    errs = []
    if doc["case_id"] != f"TRI-{doc['turn_id']}":
        errs.append(f"case_id {doc['case_id']} != TRI-{doc['turn_id']}")
    want_missing = [k for k in CRITERIA if not doc["criteria"][k]["met"]]
    if sorted(doc["missing"]) != sorted(want_missing):
        errs.append(f"missing {doc['missing']} != unmet criteria {want_missing}")
    if set(doc["texts"]) != set(doc["item_ids"]):
        errs.append("texts keys != item_ids")
    for k in CRITERIA:
        for ev in doc["criteria"][k]["evidence"]:
            if ev["item_id"] not in doc["item_ids"]:
                errs.append(f"criteria.{k}: evidence item_id {ev['item_id']} not in item_ids")
        errs += _check_evidence(doc["criteria"][k]["evidence"], doc["texts"], doc["source"]["speaker_name"],
                                f"criteria.{k}.evidence")
    h = doc["safety_hint"]
    if h and h["span"] not in doc["texts"].get(h["item_id"], ""):
        errs.append(f"safety_hint.span {h['span']!r} not in texts[{h['item_id']}]")
    if h and h["stand_in"] != doc["provenance"]["stand_in"]:
        errs.append("safety_hint.stand_in != provenance.stand_in")
    ctx.setdefault("triage", {})[doc["case_id"]] = doc
    return errs


def check_triage_audit(doc, ctx):
    rec = ctx.get("triage", {}).get(doc["case_id"])
    if rec is None:  # the case may come from another build; offsets can't be checked without its texts
        return []
    errs = []
    for k in CRITERIA:
        errs += _check_evidence(doc["snapshot"]["criteria"][k]["evidence"], rec["texts"],
                                doc["snapshot"]["source"]["speaker_name"], f"snapshot.criteria.{k}.evidence")
    return errs


def check_gap_view(doc, ctx):
    errs = []
    cols = [c["key"] for c in doc["columns"]]
    got = {(c["aspect"], c["column"]) for c in doc["cells"]}
    want = {(a, c) for a in doc["aspects"] for c in cols}
    if got != want or len(doc["cells"]) != len(want):
        errs.append(f"cells must be exactly one per aspect x column ({len(want)}), got {len(doc['cells'])}")
    if doc["provenance"]["stand_in"] != any(i["stand_in"] for i in doc["provenance"]["inputs"]):
        errs.append("provenance.stand_in must be true iff any input is stand-in")
    flag_ids = [f["flag_id"] for f in doc["flags"]]
    if len(set(flag_ids)) != len(flag_ids):
        errs.append("duplicate flag_id")
    for f in doc["flags"]:
        for c in f["columns"]:
            if c not in cols:
                errs.append(f"flag {f['flag_id']}: unknown column {c}")
    if sum(1 for f in doc["flags"] if f["kind"] == "split") > len(doc["aspects"]):
        errs.append("more split flags than aspects")
    for kind in ("split", "thin"):
        aspects = [f["aspect"] for f in doc["flags"] if f["kind"] == kind]
        if len(set(aspects)) != len(aspects):
            errs.append(f"more than one {kind} flag on one aspect")
    for q in doc["questions"]:
        if q["flag_id"] not in flag_ids:
            errs.append(f"question {q['question_id']}: unknown flag_id {q['flag_id']}")
    # quote spans: check against any label row we can load
    rows = ctx.get("label_rows", {})
    quotes = [(f"cells[{c['aspect']}/{c['column']}]", q) for c in doc["cells"] for q in c["quotes"]]
    quotes += [(f"flags[{f['flag_id']}]", q) for f in doc["flags"] for q in f["evidence"]]
    quotes += [(f"questions[{q['question_id']}]", c) for q in doc["questions"] for c in q["citations"]]
    unchecked = 0
    for where, q in quotes:
        r = rows.get(q["item_id"])
        if r is None:
            unchecked += 1
        elif q["span"] not in r["text"]:
            errs.append(f"{where}: span {q['span']!r} not in {q['item_id']}.text")
    ctx.setdefault("notes", []).append(f"{unchecked} of {len(quotes)} gap quote spans unchecked "
                                       f"(source rows not loaded)" if unchecked else "")
    return errs


def check_label_cost(doc, ctx):
    errs = []
    if doc["tokens"] and doc["price"] and doc["usd_total"] is not None:
        want = (doc["tokens"]["input"] * doc["price"]["input_per_m"]
                + doc["tokens"]["output"] * doc["price"]["output_per_m"]) / 1e6
        if abs(want - doc["usd_total"]) > 1e-4:
            errs.append(f"usd_total {doc['usd_total']} != tokens x price {want:.6f}")
    if doc["usd_total"] is not None and doc["usd_per_100"] is not None:
        if abs(doc["usd_total"] / doc["items"] * 100 - doc["usd_per_100"]) > 1e-3:
            errs.append("usd_per_100 != usd_total / items * 100")
    return errs


SEMANTIC = {
    "label_row": check_label_row,
    "triage_record": check_triage_record,
    "triage_audit": check_triage_audit,
    "gap_view": check_gap_view,
    "label_cost": check_label_cost,
}

# Order matters: label rows and triage records feed the context the later checks use.
ORDER = ["label_row", "triage_record", "triage_audit", "gap_view", "label_cost"]


def validate_docs(kind, docs, ctx=None):
    """Validate (label, doc) pairs of one kind. Returns a list of error strings."""
    ctx = {} if ctx is None else ctx
    errs = []
    for label, doc in docs:
        se = schema_errors(kind, doc)
        if se:
            errs += [f"{label}: {e}" for e in se]
            continue
        if kind == "label_row":
            ctx.setdefault("label_rows", {})[doc["item_id"]] = doc
        errs += [f"{label}: {e}" for e in SEMANTIC[kind](doc, ctx)]
    return errs


def validate_files(files, ctx=None):
    """files: [(kind, path)]. Returns {path: [errors]}."""
    ctx = {} if ctx is None else ctx
    files = sorted(files, key=lambda kp: ORDER.index(kp[0]))
    return {str(p): validate_docs(k, read_docs(p), ctx) for k, p in files}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixtures", action="store_true", help="check fixtures only, skip out/startup/")
    a = ap.parse_args()

    groups = [("fixtures", FIXTURES)]
    if not a.fixtures:
        groups.append(("real outputs", real_outputs()))

    # Real label rows (incl. probe) help check fixture gap quotes, so load them into a shared context first.
    ctx = {}
    for _, p in [kp for kp in real_outputs() if kp[0] == "label_row"]:
        for _, d in read_docs(p):
            ctx.setdefault("label_rows", {})[d.get("item_id")] = d

    bad = 0
    for name, files in groups:
        print(f"== {name} ({len(files)} files)")
        for path, errs in validate_files(files, ctx).items():
            rel = Path(path).relative_to(DT)
            print(f"  {'FAIL' if errs else 'ok  '} {rel}" + (f"  ({len(errs)} errors)" if errs else ""))
            for e in errs[:20]:
                print(f"       {e}")
            bad += bool(errs)
    for n in filter(None, ctx.get("notes", [])):
        print(f"  note: {n}")
    print("FAILED" if bad else "all contracts ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
