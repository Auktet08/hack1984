#!/usr/bin/env python3
"""Harvest dated public coverage of an analog drug launch with the Exa search API.

Build-time only (never called by inference). Reads the key from ~/.config/exa/key,
saves every raw response under research/raw/, appends one ledger row per run, and
writes items in the track's item format after deduping against the test set (R6).

    python3 src/startup/exa_harvest.py src/startup/queries_probe.json --tag probe
"""
import argparse, datetime as dt, hashlib, json, os, re, sys, urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # drug track/
RAW = ROOT / "research" / "raw"
LEDGER = ROOT / "research" / "ledger.jsonl"
OUT = ROOT / "out" / "startup"
TEST = ROOT / "data" / "test_inputs.full.jsonl"
API = "https://api.exa.ai/search"

PRESS_DOMAINS = ("takeda.com", "sppirx.com", "spectrumpharm", "businesswire.com", "prnewswire.com", "globenewswire.com")
PAPER_DOMAINS = ("pubmed", "ncbi.nlm.nih.gov", "nature.com", "sciencedirect", "ascopubs", "jto.org", "springer", "wiley", "nejm", "thelancet")


def key():
    return (Path.home() / ".config" / "exa" / "key").read_text().strip()


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def test_index():
    urls, titles, shas = set(), set(), set()
    for line in TEST.open():
        d = json.loads(line)
        urls.add((d.get("url") or "").rstrip("/"))
        titles.add(norm_title(d.get("title")))
        shas.add(d.get("text_sha256"))
    return urls, titles, shas


def search(q, k):
    body = {"query": q["query"], "type": "auto", "numResults": q.get("n", 10),
            "contents": {"text": {"maxCharacters": 2500}}}
    for f in ("startPublishedDate", "endPublishedDate", "category"):
        if q.get(f):
            body[f] = q[f]
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST",
                                 headers={"x-api-key": k, "content-type": "application/json",
                                          "user-agent": "hack1984-harvest/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def source_of(url):
    u = url.lower()
    if any(d in u for d in PRESS_DOMAINS):
        return "press_release"
    if any(d in u for d in PAPER_DOMAINS):
        return "paper"
    if u.endswith(".pdf") or "fda.gov" in u:
        return "document"
    return "news"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("queries")
    ap.add_argument("--tag", required=True)
    a = ap.parse_args()
    spec = json.loads(Path(a.queries).read_text())
    k = key()
    urls, titles, shas = test_index()
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    total_usd, n_search, items, seen, dropped = 0.0, 0, [], set(), Counter()
    for drug, d in spec["drugs"].items():
        for i, q in enumerate(d["queries"], 1):
            try:
                resp = search(q, k)
            except Exception as e:  # keep going; log the failure
                print(f"[{drug} q{i}] FAILED: {e}", file=sys.stderr)
                continue
            n_search += 1
            total_usd += float((resp.get("costDollars") or {}).get("total") or 0)
            (RAW / f"exa-{a.tag}-{drug}-{i:02d}.json").write_text(json.dumps({"request": q, "response": resp}, indent=1))
            for r in resp.get("results", []):
                url = (r.get("url") or "").rstrip("/")
                text = (r.get("text") or "").strip()
                if not url or not text:
                    dropped["empty"] += 1; continue
                if url in seen:
                    dropped["dup"] += 1; continue
                sha = hashlib.sha256(text.encode()).hexdigest()
                if url in urls or norm_title(r.get("title")) in titles or sha in shas:
                    dropped["test_overlap"] += 1; continue
                seen.add(url)
                items.append({"item_id": f"{d['prefix']}-{len([x for x in items if x['product']==d['product']])+1:04d}",
                              "source": source_of(url), "source_id": r.get("id"), "url": url,
                              "published": (r.get("publishedDate") or "")[:10] or None,
                              "product": d["product"], "title": r.get("title"), "text": text,
                              "text_sha256": sha, "query": q["query"]})

    out = OUT / f"{a.tag}_items.jsonl"
    with out.open("w") as f:
        for it in items:
            f.write(json.dumps(it) + "\n")
    with LEDGER.open("a") as f:
        f.write(json.dumps({"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "who": "claude-startup", "tool": "exa", "endpoint": f"search API x{n_search} (text 2500 chars)",
                            "bucket": "ad-hoc", "purpose": spec.get("purpose", a.tag), "credits": None,
                            "usd": round(total_usd, 4), "note": f"costDollars from API; R6 dedupe vs test dropped {dropped['test_overlap']}",
                            "out": f"research/raw/exa-{a.tag}-*.json; out/startup/{a.tag}_items.jsonl"}) + "\n")
    print(f"searches={n_search} usd={total_usd:.4f} items={len(items)} dropped={dict(dropped)} -> {out}")


if __name__ == "__main__":
    main()
