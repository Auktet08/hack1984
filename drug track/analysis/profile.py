import json, sys, statistics as st
from collections import Counter, defaultdict
D = sys.argv[1]
def load(p): return [json.loads(l) for l in open(p) if l.strip()]
dev, test, unl = (load(f"{D}/data/{n}.full.jsonl") for n in ("dev","test_inputs","unlabeled"))
ASP = ["efficacy","safety","convenience","access_cost","evidence_quality"]
for name, S in (("dev",dev),("test",test),("unl",unl)):
    print(f"\n== {name} n={len(S)}")
    print(" source", Counter(r["source"] for r in S).most_common())
    print(" product", Counter(r["product"] for r in S).most_common())
    print(" null text", sum(r["text"] is None for r in S))
    months = Counter(r["published"][:7] for r in S); print(" date range", min(months), max(months))
    print(" by year", Counter(r["published"][:4] for r in S))
    print(" id prefixes", Counter(r["item_id"].split("-")[0] for r in S))
    for src in sorted(set(r["source"] for r in S)):
        L=[len(r["text"].split()) for r in S if r["source"]==src and r["text"]]
        print(f"  words {src}: median {st.median(L)} min {min(L)} max {max(L)}")
print("\n== dev labels")
print(" human_reviewed", Counter(r.get("human_reviewed") for r in dev))
print(" keys", sorted(set(k for r in dev for k in r)))
ct = defaultdict(Counter)
for r in dev: ct[r["source"]][r["signal_type"]]+=1
for s,c in ct.items(): print(" sig by src", s, dict(c))
ac = defaultdict(Counter)
for r in dev: ac[r["source"]][r["actionable"]]+=1
for s,c in ac.items(): print(" act by src", s, dict(c))
print(" actionable by signal", dict(Counter((r["signal_type"],r["actionable"]) for r in dev)))
print(" n aspects per item", Counter(sum(r[a] is not None for a in ASP) for r in dev))
sp=defaultdict(Counter); pol=defaultdict(Counter); spans=[]
for r in dev:
  for a in ASP:
    v=r[a]
    if v:
      sp[r["source"]][v["speaker"]]+=1; pol[a][v["polarity"]]+=1
      spans.append((len(v["span"].split()), v["span"] in r["text"], a, r["source"], v["polarity"], v["span"]))
for s,c in sp.items(): print(" speaker by src", s, dict(c))
for a,c in pol.items(): print(" polarity", a, dict(sorted(c.items())))
L=[s[0] for s in spans]; print(" span words median",st.median(L),"min",min(L),"max",max(L),"mean",round(st.mean(L),1))
print(" spans verbatim", sum(s[1] for s in spans), "/", len(spans))
print(" aspect by source", dict(Counter((s[3],s[2]) for s in spans)))
