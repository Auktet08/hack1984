"""Rules-only predictor for HACK1984 Track 1. No model, standard library only.

  python3 predict.py <items.full.jsonl> <out.jsonl> [--level 1|2|3]

Level 1: source rules straight from LABELING_GUIDE.md.
Level 2: + guide-driven signal/actionable keywords for rare classes (rulings 4, 5; guideline; HTA/access).
Level 3: + cue-word aspect triggers with verbatim spans (PubMed, press, news); hedges the QWK cliff.
Rules come from the guide and dev only; never from test inputs.
"""
import argparse
import json
import re

ASP = ["efficacy", "safety", "convenience", "access_cost", "evidence_quality"]
SPEAKER = {"pubmed": "researcher", "ctgov": "company", "press_release": "company",
           "fda_label": "regulator", "fda_notice": "regulator", "news": "media"}

# fda_event special reactions (guide: Rules per source -> fda_event)
NULL_REACT = {"off label use", "product use issue", "no adverse event"}
EFF_REACT = {"drug ineffective", "disease progression", "malignant neoplasm progression"}
ACC_REACT = {"inability to afford medication", "product unavailable"}

# Cue patterns: (aspect, polarity, regex). The match itself is the span, so it is always verbatim.
# Ordered most specific first; the first hit per aspect wins.
CUES = [
    ("evidence_quality", -1, r"\b(?:a )?retrospective(?:ly)? (?:\w+ ){0,2}(?:study|analysis|analyzed|cohort|review)\b"),
    ("evidence_quality", -1, r"\b(?:small sample size|immature data|further (?:studies|research|investigation) (?:are|is) (?:needed|warranted))\b"),
    ("safety", 0, r"\b(?:no new safety signals|consistent with the known (?:safety )?profiles?)\b"),
    ("safety", 1, r"\b(?:a )?(?:manageable|acceptable|favou?rable) safety(?: profile)?\b"),
    ("safety", 1, r"\bwell[- ]tolerated\b"),
    ("efficacy", 2, r"\bstatistically significant and clinically meaningful [\w\s()-]{0,60}?(?:benefit|improvement)(?: over [\w-]+)?"),
    ("efficacy", 2, r"\bsignificantly (?:improved|prolonged) (?:[\w-]+ ){0,4}?(?:survival|PFS|OS)\b"),
    ("efficacy", -1, r"\b(?:did not meet (?:its|the) primary endpoint|is not warranted)\b"),
]
REAL_WORLD = re.compile(r"real[- ]world|retrospective", re.I)
PUBMED_ONLY = {"evidence_quality", "safety"}  # press/news mention other studies; these cues misfire there
SPAN_MODE = "match"  # "match" | "clause"


def widen(t, start, end, max_words=16):
    """Grow a cue match to its clause: back to the sentence start or a ';'/':', forward to sentence end.
    Never crosses a sentence (ruling 10) or an ellipsis. Trims to max_words around the cue."""
    left = max(t.rfind(". ", 0, start), t.rfind("; ", 0, start), t.rfind(": ", 0, start), t.rfind("…", 0, start))
    left = 0 if left < 0 else left + 2 if t[left] != "…" else left + 1
    rights = [i for i in (t.find(". ", end), t.find("; ", end), t.find("…", end)) if i >= 0]
    right = min(rights) if rights else len(t)
    words_left = t[left:start].split()
    words_right = t[end:right].split()
    budget = max(0, max_words - len(t[start:end].split()))
    keep_left = words_left[-min(len(words_left), budget):] if budget else []
    keep_right = words_right[:max(0, budget - len(keep_left))]
    span = " ".join(keep_left + [t[start:end]] + keep_right).strip(" ,.;")
    return span if span in t else t[start:end]


def empty(item_id):
    return {"item_id": item_id, "signal_type": "none", "actionable": "no", **{a: None for a in ASP}}


def fda_event(r, o):
    t = r["text"] or ""
    o["signal_type"] = "safety"
    rep = re.search(r"Reporter: ([^.]*)", t)
    spk = "patient" if rep and rep.group(1).strip() == "consumer" else "hcp"
    m = re.search(r"Reactions: (.*?)\. Serious", t)
    reacts = [x.strip() for x in m.group(1).split(",")] if m else []
    saf = [x for x in reacts if x.lower() not in NULL_REACT | EFF_REACT | ACC_REACT]
    eff = [x for x in reacts if x.lower() in EFF_REACT]
    acc = [x for x in reacts if x.lower() in ACC_REACT]
    if saf:
        span = ", ".join(saf)
        o["safety"] = {"polarity": -1, "speaker": spk, "span": span if span in t else saf[0]}
    if eff:
        o["efficacy"] = {"polarity": -1, "speaker": spk, "span": eff[0]}
    if acc:
        o["access_cost"] = {"polarity": -1, "speaker": spk, "span": acc[0]}


def level1(r):
    o = empty(r["item_id"])
    s, ti = r["source"], r["title"].lower()
    if s == "ctgov":
        o["signal_type"] = "trial_update"  # aspects null unless stop reason judges the drug
        t = r["text"] or ""
        if re.search(r"futility|insufficient efficacy|lack of efficacy", t, re.I):
            o["efficacy"] = {"polarity": -2, "speaker": "company",
                             "span": re.search(r"[^.]*(?:futility|insufficient efficacy|lack of efficacy)", t, re.I).group(0).strip()}
        elif re.search(r"toxicity", t, re.I) and "TERMINATED" in t:
            o["safety"] = {"polarity": -2, "speaker": "company", "span": "toxicity"}
    elif s == "fda_event":
        fda_event(r, o)
    elif s == "fda_label":
        o["signal_type"], o["actionable"] = "regulatory", "yes"
    elif s == "fda_notice":
        o["signal_type"], o["actionable"] = "regulatory", "yes"
    elif s == "press_release":
        o["signal_type"], o["actionable"] = "efficacy", "yes"
    elif s == "news":
        o["signal_type"] = "efficacy"
    elif s == "pubmed":
        safety_words = ["adverse", "toxicit", "safety", "dermat", "thromboemb", "pneumonitis"]
        o["signal_type"] = "safety" if any(k in ti for k in safety_words) else "efficacy"
    return o


def level2(r, o):
    s, ti = r["source"], r["title"].lower()
    text = (r["text"] or "")[:1500].lower()
    if s in ("press_release", "news"):
        if re.search(r"reports? (?:q[1-4]|first|second|third|fourth|full)[- ]", ti) or "quarter" in ti and "results" in ti:
            o.update(signal_type="competitor_move", actionable="no")  # ruling 5: earnings
        elif re.search(r"guideline|nccn|esmo|pathway", ti):
            o.update(signal_type="guideline", actionable="yes")
        elif re.search(r"\bpbs\b|reimburs|\bnice\b|coverage|pricing|price|formulary|access", ti):
            o.update(signal_type="access_pricing", actionable="yes")
        elif re.search(r"\bapprov|\bfda\b|\bema\b|\bchmp\b", ti):
            o.update(signal_type="regulatory", actionable="yes")
        elif s == "press_release" and not re.search(r"tagrisso|osimertinib|rybrevant|amivantamab|lazcluze|lazertinib", ti + text):
            o.update(signal_type="none", actionable="no")
    if s == "fda_label" and "adverse reactions" in ti and "warning" not in (r["text"] or "").lower():
        o.update(signal_type="none", actionable="no")  # guide: table rows only -> none
    if s == "pubmed":
        if re.search(r"\bcase report\b|\ba case\b", ti):
            o["actionable"] = "no"
        if re.search(r"protocol|study design|rationale and design", ti):
            o["signal_type"] = "trial_update"  # ruling 4
        elif re.search(r"\breview\b|rethinking|perspective|commentary|editorial", ti):
            o["signal_type"] = "expert_opinion"
        if re.search(r"phase (?:iii|3)", ti) and not re.search(r"protocol|design", ti):
            o["actionable"] = "yes"
    return o


def level3(r, o):
    s, t = r["source"], r["text"] or ""
    if s not in ("pubmed", "press_release", "news") or o["signal_type"] in ("competitor_move", "none"):
        return o
    spk = SPEAKER[s]
    for asp, pol, pat in CUES:
        if o[asp] is not None or (asp in PUBMED_ONLY and s != "pubmed"):
            continue
        m = re.search(pat, t, re.I)
        if not m:
            continue
        span = widen(t, m.start(), m.end()) if SPAN_MODE == "clause" else m.group(0).strip()
        if asp == "efficacy" and pol == 2 and REAL_WORLD.search(t) and s == "pubmed":
            pol = 1  # guide: when unsure pick the milder level; real-world data is rarely +2
        o[asp] = {"polarity": pol, "speaker": spk, "span": span}
    return o


def predict(r, level):
    o = level1(r)
    if level >= 2:
        o = level2(r, o)
    if level >= 3:
        o = level3(r, o)
    # citation guard: drop any span that is not verbatim in the text
    for a in ASP:
        if o[a] and (not r["text"] or o[a]["span"] not in r["text"]):
            o[a] = None
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("items")
    ap.add_argument("out")
    ap.add_argument("--level", type=int, default=3)
    a = ap.parse_args()
    with open(a.items, encoding="utf-8") as f, open(a.out, "w", encoding="utf-8") as g:
        for line in f:
            if line.strip():
                g.write(json.dumps(predict(json.loads(line), a.level), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
