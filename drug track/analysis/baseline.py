import json,sys,re
sys.path.insert(0, sys.argv[1]+"/scoring"); from score import score, load, span_f1
D=sys.argv[1]; gold=load(f"{D}/data/dev.jsonl"); items=load(f"{D}/data/dev.full.jsonl")
ASP=["efficacy","safety","convenience","access_cost","evidence_quality"]
SPEC_NULL={"off label use","product use issue","no adverse event"}
SPEC_EFF={"drug ineffective","disease progression","malignant neoplasm progression"}
SPEC_AC={"inability to afford medication","product unavailable"}
def fda_event(t, mode):
    rx=re.search(r"Reactions: (.*?)\. Serious",t).group(1).split(", ")
    rep=re.search(r"Reporter: ([^.]*)",t).group(1)
    spk="patient" if rep=="consumer" else "hcp"
    keep=[x for x in rx if x.lower() not in SPEC_NULL|SPEC_EFF|SPEC_AC]
    o={a:None for a in ASP}
    if keep:
        k = keep if mode=="all" else keep[:int(mode)]
        # contiguous run in original text required; take prefix of original list up to last kept
        span=", ".join(k)
        if span not in t: span=k[0]
        o["safety"]={"polarity":-1,"speaker":spk,"span":span}
    e=[x for x in rx if x.lower() in SPEC_EFF]
    if e: o["efficacy"]={"polarity":-1,"speaker":spk,"span":e[0]}
    return o
def rules(r, mode="all", default_sig=None):
    s=r["source"]; t=r["text"]; o={"item_id":r["item_id"],"signal_type":"none","actionable":"no",**{a:None for a in ASP}}
    if s=="ctgov":
        o["signal_type"]="trial_update"
        if "New registration" in t and "PHASE3" in t: o["actionable"]="yes"
    elif s=="fda_event": o["signal_type"]="safety"; o.update(fda_event(t,mode))
    elif s=="fda_notice": o.update(signal_type="regulatory",actionable="yes")
    elif s=="fda_label": o["signal_type"]="regulatory"
    elif default_sig: o["signal_type"]=default_sig.get(s,"none")
    if s=="press_release": o["actionable"]="yes" if default_sig else "no"
    return o
def run(name, preds):
    p={x["item_id"]:x for x in preds}
    res=score(gold,p,items); keys=["signal_macro_f1","actionable_f1","aspect_f1","polarity_qwk","speaker_accuracy","span_f1","citation_validity","composite"]
    print(f"{name:42s}", "  ".join(f"{k.split('_')[0][:5]}={res[k]}" for k in keys))
run("B0 all-none (sample_submission)", [])
for m in ("all","1","3"): run(f"B1 rules only, fda_event span={m}", [rules(r,m) for r in items.values()])
run("B2 rules + pubmed/news/PR->efficacy", [rules(r,"all",{"pubmed":"efficacy","news":"efficacy","press_release":"efficacy"}) for r in items.values()])
# upper bound: gold everywhere except fda_event spans per strategy
for m in ("all","1","3"):
    f=[span_f1(fda_event(items[i]["text"],m)["safety"]["span"], g["safety"]["span"]) for i,g in gold.items() if items[i]["source"]=="fda_event"]
    print(f"fda_event safety span_f1 strategy={m}: {sum(f)/len(f):.3f}")
# oracle: gold for rule sources only, none elsewhere
o=[]
for i,g in gold.items():
    if items[i]["source"] in ("ctgov","fda_event","fda_notice"): o.append({k:g[k] for k in ["item_id","signal_type","actionable",*ASP]})
run("O1 gold on rule sources only", o)
run("O2 gold everywhere (ceiling)", [{k:g[k] for k in ["item_id","signal_type","actionable",*ASP]} for g in gold.values()])
