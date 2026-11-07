#!/usr/bin/env python3
"""Label items with Gemini through the Gemini CLI (headless) to make teacher / silver labels.

    python3 "drug track/src/teacher/gemini_label.py" --items "drug track/data/dev.full.jsonl" \
        --out "drug track/out/teacher/dev_gemini.jsonl" --jobs 6

Each call sends one prompt with the full LABELING_GUIDE.md, k worked examples from dev (same source,
never the item itself) and the item. The raw replies are cached in <out>.raw/, so a rerun skips items
already done and retries only the failures. Token use and the model that served the call are summed into
<out>.stats.json.

--backend api calls the REST API directly (key from GEMINI_API_KEY or ~/.config/gemini/key), with the label
schema enforced by the API and --thinking low|medium|high. It is about 5-10x faster than the CLI, which
thinks ~10k tokens per item and adds a ~10k-token agent prompt.

NEVER run this on test_inputs (CLAUDE.md rule 6). The script refuses any file whose name contains "test".
"""
import argparse, json, os, re, subprocess, sys, tempfile, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PKG = Path(__file__).resolve().parents[2]
ASPECTS = ["efficacy", "safety", "convenience", "access_cost", "evidence_quality"]
INPUT_KEYS = ["item_id", "source", "product", "published", "url", "title", "text"]
LABEL_KEYS = ["item_id", "signal_type", "actionable"] + ASPECTS

HEADER = """You are an expert pharma launch-intelligence annotator. Label ONE item following the labeling
guide below exactly, including the rulings at the end. Return ONLY one JSON object (no markdown fences,
no prose) with the keys: item_id, signal_type, actionable, efficacy, safety, convenience, access_cost,
evidence_quality, comment. Every span must be copied character for character from the item's "text"
field, from a single sentence. Do not use any tools; answer from the text alone.

===== LABELING GUIDE =====
"""


def load(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def pick_examples(item, pool, k):
    """k dev examples from the same source (others if too few), never the item itself, chosen stably."""
    same = [g for g in pool if g["source"] == item["source"] and g["item_id"] != item["item_id"]]
    other = [g for g in pool if g["source"] != item["source"] and g["item_id"] != item["item_id"]]
    # prefer examples that have at least one aspect, so the model sees span/polarity format
    same.sort(key=lambda g: (all(g.get(a) is None for a in ASPECTS), g["item_id"]))
    return (same + other)[:k]


def build_prompt(item, examples, guide):
    parts = [HEADER, guide, "\n===== WORKED EXAMPLES (gold labels) =====\n"]
    for ex in examples:
        parts.append("ITEM:\n" + json.dumps({k: ex.get(k) for k in INPUT_KEYS}, ensure_ascii=False))
        parts.append("LABEL:\n" + json.dumps({k: ex.get(k) for k in LABEL_KEYS}, ensure_ascii=False) + "\n")
    parts.append("===== ITEM TO LABEL =====")
    parts.append(json.dumps({k: item.get(k) for k in INPUT_KEYS}, ensure_ascii=False))
    parts.append("LABEL:")
    return "\n".join(parts)


def parse_reply(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def normalize(item, lab):
    out = {"item_id": item["item_id"], "signal_type": lab.get("signal_type", "none"),
           "actionable": lab.get("actionable", "no")}
    for a in ASPECTS:
        v = lab.get(a)
        out[a] = v if isinstance(v, dict) and v.get("span") is not None else None
    if lab.get("comment"):
        out["comment"] = lab["comment"]
    return out


API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
SIGNALS = ["efficacy", "safety", "regulatory", "trial_update", "competitor_move", "access_pricing",
           "guideline", "expert_opinion", "none"]
SPEAKERS = ["researcher", "company", "regulator", "hcp", "patient", "payer", "media"]
_ASPECT = {"type": "OBJECT", "nullable": True,
           "properties": {"polarity": {"type": "INTEGER"}, "speaker": {"type": "STRING", "enum": SPEAKERS},
                          "span": {"type": "STRING"}},
           "required": ["polarity", "speaker", "span"], "propertyOrdering": ["span", "polarity", "speaker"]}
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {"item_id": {"type": "STRING"}, "signal_type": {"type": "STRING", "enum": SIGNALS},
                   "actionable": {"type": "STRING", "enum": ["yes", "no"]},
                   **{a: _ASPECT for a in ASPECTS}, "comment": {"type": "STRING"}},
    "required": LABEL_KEYS,
    "propertyOrdering": LABEL_KEYS + ["comment"],
}


_NORM = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
                       " ": " "})


def _norm_with_map(s):
    """Lowercase, straighten quotes/dashes, collapse whitespace; return (normalized, index map to s)."""
    out, idx, prev_space = [], [], False
    for i, ch in enumerate(s.translate(_NORM).lower()):
        if ch.isspace():
            if prev_space:
                continue
            ch, prev_space = " ", True
        else:
            prev_space = False
        out.append(ch)
        idx.append(i)
    return "".join(out), idx


def check_span(text, span, min_cover=0.8):
    """Make a span verbatim. Returns (span_or_None, status): ok | fixed_norm | fixed_fuzzy | dropped."""
    import difflib
    if not span or not text:
        return None, "dropped"
    if span in text and "…" not in span:
        return span, "ok"
    nt, imap = _norm_with_map(text)
    ns, _ = _norm_with_map(span.strip())
    j = nt.find(ns)
    if ns and j >= 0:
        fixed = text[imap[j]: imap[j + len(ns) - 1] + 1]
        if "…" not in fixed:
            return fixed, "fixed_norm"
    # fuzzy: best single sentence, keep the stretch between the first and last matching blocks
    best = (0.0, None)
    for m in re.finditer(r"[^.!?…]+[.!?]?", text):
        sent = m.group(0)
        sm = difflib.SequenceMatcher(None, span, sent, autojunk=False)
        blocks = [b for b in sm.get_matching_blocks() if b.size >= 3]
        if not blocks:
            continue
        cover = sum(b.size for b in blocks) / len(span)
        if cover > best[0]:
            lo, hi = blocks[0].b, blocks[-1].b + blocks[-1].size
            while lo > 0 and sent[lo - 1].isalnum():  # never start or end mid-word
                lo -= 1
            while hi < len(sent) and sent[hi].isalnum():
                hi += 1
            piece = sent[lo:hi].strip(" ,;:")
            best = (cover, piece)
    if best[0] >= min_cover and best[1] and best[1] in text:
        return best[1], "fixed_fuzzy"
    return None, "dropped"


def apply_span_check(item, lab, counts):
    lab = json.loads(json.dumps(lab))
    for a in ASPECTS:
        if lab[a]:
            span, status = check_span(item.get("text") or "", lab[a].get("span"))
            counts[status] += 1
            lab[a] = dict(lab[a], span=span) if span else None
    return lab


def call_api(prompt, model, timeout, thinking):
    """Direct Gemini API call: schema-constrained JSON, chosen thinking level. Returns the CLI-shaped dict."""
    import urllib.request, urllib.error
    split = prompt.index("===== WORKED EXAMPLES")  # guide = stable system prefix, so implicit caching can apply
    gen = {"responseMimeType": "application/json", "responseSchema": RESPONSE_SCHEMA, "temperature": 0}
    if thinking:
        gen["thinkingConfig"] = {"thinkingLevel": thinking}
    body = {"systemInstruction": {"parts": [{"text": prompt[:split]}]},
            "contents": [{"role": "user", "parts": [{"text": prompt[split:]}]}], "generationConfig": gen}
    req = urllib.request.Request(API_URL.format(model=model), data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:300]}") from None
    text = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"] if not p.get("thought"))
    u = d.get("usageMetadata", {})
    tokens = {"input": u.get("promptTokenCount", 0), "candidates": u.get("candidatesTokenCount", 0),
              "thoughts": u.get("thoughtsTokenCount", 0), "cached": u.get("cachedContentTokenCount", 0)}
    return {"response": text, "stats": {"models": {d.get("modelVersion", model): {
        "api": {"totalRequests": 1, "totalLatencyMs": int((time.time() - t0) * 1000)}, "tokens": tokens}}}}


def call_gemini(prompt, model, cwd, timeout):
    cmd = ["gemini", "--skip-trust", "--approval-mode", "plan", "-o", "json", "-p", ""]
    if model:
        cmd[1:1] = ["-m", model]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=cwd, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"exit {r.returncode}: {r.stderr[-400:]}")
    return json.loads(r.stdout)


def run_one(item, pool, k, guide, model, rawdir, cwd, timeout, retries, backend="cli", thinking=None):
    raw_path = rawdir / f"{item['item_id']}.json"
    if raw_path.exists():
        return json.load(open(raw_path))
    prompt = build_prompt(item, pick_examples(item, pool, k), guide)
    err = None
    for attempt in range(retries + 1):
        try:
            res = (call_api(prompt, model, timeout, thinking) if backend == "api"
                   else call_gemini(prompt, model, cwd, timeout))
            parse_reply(res["response"])  # fail early so we retry on malformed JSON
            json.dump(res, open(raw_path, "w"))
            return res
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{item['item_id']}: {err}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--examples", default=str(PKG / "data/dev.full.jsonl"), help="labeled pool for few-shot")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--model", default="gemini-3.5-flash")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sources", default="", help="comma list, e.g. pubmed,news,press_release,fda_label")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--backend", choices=["cli", "api"], default="cli",
                    help="api = direct REST call (needs GEMINI_API_KEY), schema-constrained, faster")
    ap.add_argument("--thinking", default=None, help="api only: thinkingLevel, e.g. minimal|low|medium|high")
    a = ap.parse_args()
    if "test" in Path(a.items).name.lower():
        sys.exit("Refusing: never send test items to a frontier model (CLAUDE.md rule 6).")
    keyfile = Path.home() / ".config/gemini/key"
    if a.backend == "api" and not os.environ.get("GEMINI_API_KEY") and keyfile.exists():
        os.environ["GEMINI_API_KEY"] = keyfile.read_text().strip()
    if a.backend == "api" and not os.environ.get("GEMINI_API_KEY"):
        sys.exit("Set GEMINI_API_KEY or put the key in ~/.config/gemini/key for --backend api.")

    items = load(a.items)
    if a.sources:
        items = [it for it in items if it["source"] in a.sources.split(",")]
    items = items[: a.limit or None]
    pool = load(a.examples)
    guide = (PKG / "LABELING_GUIDE.md").read_text()
    out = Path(a.out)
    rawdir = Path(str(out) + ".raw")
    rawdir.mkdir(parents=True, exist_ok=True)
    cwd = tempfile.mkdtemp(prefix="gemini_cwd_")  # empty dir: no repo files for the CLI agent to read

    results, failed = {}, []
    with ThreadPoolExecutor(a.jobs) as ex:
        futs = {ex.submit(run_one, it, pool, a.k, guide, a.model, rawdir, cwd, a.timeout, a.retries,
                          a.backend, a.thinking): it
                for it in items}
        for n, f in enumerate(as_completed(futs), 1):
            it = futs[f]
            try:
                results[it["item_id"]] = f.result()
            except Exception as e:  # noqa: BLE001
                failed.append(it["item_id"])
                print(f"FAIL {e}", file=sys.stderr)
            print(f"\r{n}/{len(items)} done, {len(failed)} failed", end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)

    tok, models, bad_spans, checks = defaultdict(int), defaultdict(int), 0, defaultdict(int)
    checked_path = Path(str(out).removesuffix(".jsonl") + ".checked.jsonl")
    with open(out, "w") as fo, open(checked_path, "w") as fc:
        for it in items:
            res = results.get(it["item_id"])
            if res is None:
                continue
            lab = normalize(it, parse_reply(res["response"]))
            for a_ in ASPECTS:
                if lab[a_] and lab[a_]["span"] not in (it.get("text") or ""):
                    bad_spans += 1
            fo.write(json.dumps(lab, ensure_ascii=False) + "\n")
            fc.write(json.dumps(apply_span_check(it, lab, checks), ensure_ascii=False) + "\n")
            for m, s in res.get("stats", {}).get("models", {}).items():
                models[m] += s["api"]["totalRequests"]
                for kk, vv in s["tokens"].items():
                    tok[kk] += vv
    stats = {"items": len(items), "labeled": len(results), "failed": failed, "non_verbatim_spans": bad_spans,
             "span_check": dict(checks), "checked_out": str(checked_path),
             "models_served": dict(models), "tokens": dict(tok)}
    json.dump(stats, open(str(out) + ".stats.json", "w"), indent=2)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
