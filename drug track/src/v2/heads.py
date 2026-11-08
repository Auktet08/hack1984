"""Linear heads on local Qwen embeddings, trained on teacher (silver) labels, merged over Rules L3."""
import json
import re
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "inference"), str(HERE.parent)]
from clauses import split, trim  # noqa: E402
from embed import Embedder, item_text, sentence_text, sentences  # noqa: E402
from rules.predict import ASP, SPEAKER, predict  # noqa: E402

MODEL_SOURCES = ("pubmed", "news", "press_release")
SECTION = re.compile(r"\b(BACKGROUND|INTRODUCTION|PURPOSE|OBJECTIVES?|AIMS?|METHODS?|PATIENTS AND METHODS|MATERIALS AND METHODS|"
                     r"RESULTS|FINDINGS|CASE (?:DESCRIPTION|PRESENTATION|REPORT)|CONCLUSIONS?|INTERPRETATION|DISCUSSION)\s*:")
SECTION_GROUP = {"BACKGROUND": "bg", "INTRODUCTION": "bg", "PURPOSE": "bg", "OBJECTIVE": "bg", "OBJECTIVES": "bg",
                 "AIM": "bg", "AIMS": "bg", "METHOD": "methods", "METHODS": "methods", "PATIENTS AND METHODS": "methods",
                 "MATERIALS AND METHODS": "methods", "RESULTS": "results", "FINDINGS": "results",
                 "CASE DESCRIPTION": "results", "CASE PRESENTATION": "results", "CASE REPORT": "results",
                 "CONCLUSION": "conclusion", "CONCLUSIONS": "conclusion", "INTERPRETATION": "conclusion",
                 "DISCUSSION": "conclusion"}
SECTION_GROUPS = ("none", "bg", "methods", "results", "conclusion", "other")
PRODUCT_RE = {"A": re.compile(r"\b(?:tagrisso|osimertinib)\b", re.I),
              "B": re.compile(r"\b(?:rybrevant|amivantamab|lazcluze|lazertinib)\b", re.I),
              "both": re.compile(r"\b(?:tagrisso|osimertinib|rybrevant|amivantamab|lazcluze|lazertinib)\b", re.I)}
SIGNALS = ["efficacy", "safety", "regulatory", "trial_update", "competitor_move",
           "access_pricing", "guideline", "expert_opinion", "none"]


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def source_onehot(rows):
    return np.array([[r["source"] == s for s in MODEL_SOURCES] + [r["product"] == p for p in ("A", "B", "both")]
                     for r in rows], dtype=np.float32)


def normalize(x):
    return x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-8)


def span_sentence(row, span, sents):
    start = row["text"].find(span)
    if start < 0:
        return None
    end = start + len(span)
    best = max(sents, key=lambda s: min(end, s["end"]) - max(start, s["start"]))
    return best["id"] if min(end, best["end"]) - max(start, best["start"]) > 0 else None


class Heads:
    def __init__(self, emb, C_item=1.0, C_sent=1.0, C_pol=1.0, seed=1984):
        self.emb, self.C_item, self.C_sent, self.C_pol, self.seed = emb, C_item, C_sent, C_pol, seed

    def item_features(self, rows):
        return np.hstack([normalize(self.emb.embed([item_text(r) for r in rows], batch=4)), source_onehot(rows)])

    def sentence_features(self, row, sents):
        return normalize(self.emb.embed([sentence_text(row, s) for s in sents]))

    def lr(self, C, balanced=False):
        return LogisticRegression(C=C, max_iter=3000, class_weight="balanced" if balanced else None,
                                  random_state=self.seed)

    def sentence_design(self, row, sents, F):
        """Dense embedding + lexical TF-IDF + position/section/product features for each sentence."""
        from scipy.sparse import csr_matrix, hstack
        text = row["text"]
        heads = [(m.start(), m.group(1).upper()) for m in SECTION.finditer(text)]
        mention = PRODUCT_RE.get(row["product"], PRODUCT_RE["both"])
        n = len(sents)
        pos = []
        for i, sent in enumerate(sents):
            active = [h for st, h in heads if st <= sent["start"]]
            sec = SECTION_GROUP.get(active[-1], "other") if active else "none"
            pos.append([i / max(1, n - 1), i == 0, i == n - 1, len(sent["text"].split()) / 40,
                        bool(mention.search(sent["text"]))] + [sec == g for g in SECTION_GROUPS])
        lex = self.tfidf.transform([sent["text"] for sent in sents]) * self.lex_weight
        return hstack([csr_matrix(F), lex, csr_matrix(np.array(pos, dtype=np.float32))]).tocsr()

    def fit(self, rows, labels):
        from scipy.sparse import vstack
        from sklearn.feature_extraction.text import TfidfVectorizer
        X = self.item_features(rows)
        y_sig = [labels[r["item_id"]]["signal_type"] for r in rows]
        self.signal = self.lr(self.C_item).fit(X, y_sig)
        self.signal_bal = self.lr(self.C_item, balanced=True).fit(X, y_sig)
        self.actionable = self.lr(self.C_item).fit(X, [labels[r["item_id"]]["actionable"] == "yes" for r in rows])
        self.presence = {}
        for a in ASP:
            y = [labels[r["item_id"]][a] is not None for r in rows]
            self.presence[a] = self.lr(self.C_item).fit(X, y) if 2 <= sum(y) < len(y) else None
        all_sents = {r["item_id"]: sentences(r) for r in rows}
        self.lex_weight = getattr(self, "lex_weight", 1.0)
        self.tfidf = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=40000).fit(
            [s["text"] for v in all_sents.values() for s in v])
        sent_X, sent_y, pol = [], {a: [] for a in ASP}, {a: ([], []) for a in ASP}
        for r in rows:
            sents = all_sents[r["item_id"]]
            if not sents:
                continue
            D = self.sentence_design(r, sents, self.sentence_features(r, sents))
            lab = labels[r["item_id"]]
            hits = {a: span_sentence(r, lab[a]["span"], sents) if lab[a] else None for a in ASP}
            sent_X.append(D)
            for a in ASP:
                sent_y[a].extend(s["id"] == hits[a] for s in sents)
                if hits[a] is not None:
                    pol[a][0].append(D[hits[a]])
                    pol[a][1].append(lab[a]["polarity"])
        S = vstack(sent_X).tocsr()
        self.locator, self.polarity = {}, {}
        for a in ASP:
            y = np.array(sent_y[a])
            self.locator[a] = self.lr(self.C_sent, balanced=True).fit(S, y) if y.sum() >= 2 else None
            Xp, yp = pol[a]
            if len(set(yp)) >= 2:
                self.polarity[a] = self.lr(self.C_pol).fit(vstack(Xp).tocsr(), yp)
            else:
                self.polarity[a] = yp[0] if yp else 1
        return self

    def infer(self, rows):
        """Return raw head outputs per item."""
        X = self.item_features(rows)
        sig_p = self.signal.predict_proba(X)
        sig_b = self.signal_bal.predict_proba(X)
        act_p = self.actionable.predict_proba(X)[:, 1]
        out = {}
        for i, r in enumerate(rows):
            sents = sentences(r)
            res = {"signal": dict(zip(self.signal.classes_, sig_p[i])),
                   "signal_bal": dict(zip(self.signal_bal.classes_, sig_b[i])), "actionable": float(act_p[i]),
                   "aspects": {}}
            D = self.sentence_design(r, sents, self.sentence_features(r, sents)) if sents else None
            for a in ASP:
                pres = self.presence[a].predict_proba(X[i:i + 1])[0, 1] if self.presence[a] else 0.0
                if D is None or self.locator[a] is None:
                    continue
                loc = self.locator[a].predict_proba(D)[:, 1]
                j = int(np.argmax(loc))
                model = self.polarity[a]
                if isinstance(model, LogisticRegression):
                    probs = dict(zip(model.classes_.tolist(), model.predict_proba(D[j])[0]))
                else:
                    probs = {model: 1.0}
                res["aspects"][a] = {"presence": float(pres), "loc": float(loc[j]), "sentence": sents[j],
                                     "loc_all": loc.tolist(),
                                     "polarity_probs": {int(k): float(v) for k, v in probs.items()}}
                units = getattr(self, "units", None)
                if units is not None and units.emb is not None:
                    res["aspects"][a]["unit_span"] = units.choose(r, a, sents[j])
            out[r["item_id"]] = res
        return out


HEADER = re.compile(
    r"^(?:BACKGROUND|INTRODUCTION|PURPOSE|OBJECTIVES?|AIMS?|METHODS?|PATIENTS AND METHODS|MATERIALS AND METHODS|"
    r"DESIGN|SETTING|PARTICIPANTS|INTERVENTIONS?|RESULTS|FINDINGS|CASE (?:DESCRIPTION|PRESENTATION|REPORT|SUMMARY)|"
    r"CONCLUSIONS?|INTERPRETATION|DISCUSSION|SIGNIFICANCE|IMPORTANCE|RATIONALE|SUMMARY|OBSERVATIONS|IMPLICATIONS|"
    r"MAIN OUTCOMES? AND MEASURES?|EXPOSURES?|TRIAL REGISTRATION|CLINICAL RELEVANCE|PRACTICAL IMPLICATIONS|"
    r"(?:CLINICAL )?TRIAL (?:REGISTRATION|NUMBER))\s*:\s*")


def strip_header(text, s, e):
    """Drop a leading abstract section label such as 'CONCLUSIONS:' from a quote."""
    m = HEADER.match(text[s:e])
    return s + m.end() if m and e - (s + m.end()) > 10 else s


def span_candidates(row, sentence):
    """Whole sentence plus its clause windows, as trimmed (start, end) offsets."""
    text = row["text"]
    s, e = trim(text, sentence["start"], sentence["end"])
    s = strip_header(text, s, e)
    cands = {(s, e)}
    for u in split(text[s:e]):
        us, ue = trim(text, s + u["start"], s + u["end"])
        if ue > us:
            cands.add((us, ue))
    return sorted(cands), (s, e)


def unit_features(emb, row, aspect, cands, bounds):
    text = row["text"]
    s, e = bounds
    E = normalize(emb.embed([text[a:b] for a, b in cands], batch=64))
    extra = np.array([[aspect == x for x in ASP] + [len(text[a:b].split()) / 20, (a - s) / max(1, e - s),
                       (a, b) == (s, e)] for a, b in cands], dtype=np.float32)
    return np.hstack([E, extra])


class UnitScorer:
    """Ridge regression of span F1 against the teacher span, over candidate quotes in the chosen sentence.

    Features: Qwen embedding of the candidate, lexical TF-IDF (cue words), aspect, length and position.
    A small length penalty at selection favours the short quotes gold uses.
    """

    def __init__(self, emb, alpha=3.0, lex=True, length_penalty=0.005):
        self.emb, self.alpha, self.lex, self.length_penalty = emb, alpha, lex, length_penalty

    def design(self, row, aspect, cands, bounds):
        from scipy.sparse import csr_matrix, hstack
        dense = unit_features(self.emb, row, aspect, cands, bounds)
        if not self.lex:
            return dense
        texts = [row["text"][a:b] for a, b in cands]
        lex = self.tfidf.transform(texts)
        inter = [lex.multiply(np.array([[aspect == x] for _ in texts], dtype=np.float32)) for x in ASP]
        return hstack([csr_matrix(dense), lex] + inter).tocsr()

    def fit(self, rows, labels, span_f1):
        from scipy.sparse import vstack
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import Ridge
        groups = []
        for r in rows:
            sents = sentences(r)
            lab = labels[r["item_id"]]
            for a in ASP:
                if not lab[a]:
                    continue
                j = span_sentence(r, lab[a]["span"], sents)
                if j is None:
                    continue
                cands, bounds = span_candidates(r, sents[j])
                groups.append((r, a, cands, bounds, [span_f1(r["text"][p:q], lab[a]["span"]) for p, q in cands]))
        if self.lex:
            self.tfidf = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=30000).fit(
                [r["text"][p:q] for r, _, cands, _, _ in groups for p, q in cands])
        X = [self.design(r, a, cands, bounds) for r, a, cands, bounds, _ in groups]
        y = [f for *_, fs in groups for f in fs]
        X = vstack(X).tocsr() if self.lex else np.vstack(X)
        self.model = Ridge(alpha=self.alpha).fit(X, np.array(y))
        return self

    def choose(self, row, aspect, sentence):
        cands, bounds = span_candidates(row, sentence)
        scores = self.model.predict(self.design(row, aspect, cands, bounds))
        lengths = np.array([len(row["text"][a:b].split()) for a, b in cands])
        a, b = cands[int(np.argmax(scores - getattr(self, "length_penalty", 0.0) * lengths))]
        return row["text"][a:b]


def pick_polarity(probs, mode="argmax"):
    if mode == "mild":
        # argmax, but step a strong label down when the expected value is milder, and never flip sign via averaging
        top = max(probs, key=probs.get)
        e = sum(k * v for k, v in probs.items())
        if abs(top) == 2 and abs(e) < 1.5:
            return 1 if top > 0 else -1
        return top
    if mode == "expected":
        e = sum(k * v for k, v in probs.items())
        return int(np.clip(round(e), -2, 2))
    return max(probs, key=probs.get)


def choose_span(row, sentence, max_words=15, emb=None, locator=None):
    """Shortest useful quote inside the chosen sentence."""
    text = row["text"]
    s, e = trim(text, sentence["start"], sentence["end"])
    if len(text[s:e].split()) <= max_words or emb is None:
        return text[s:e]
    cands = []
    for u in split(text[s:e]):
        us, ue = trim(text, s + u["start"], s + u["end"])
        if ue > us:
            cands.append((us, ue))
    if not cands:
        return text[s:e]
    F = normalize(emb.embed([sentence_text(row, {"text": text[a:b]}) for a, b in cands]))
    scores = locator.predict_proba(F)[:, 1]
    a, b = cands[int(np.argmax(scores))]
    return text[a:b]


PRESS_SAFETY = re.compile(
    r"(?:manageable|tolerable|acceptable|favou?rable|consistent|well[- ]characteri[sz]ed) safety profile|"
    r"safety profile (?:\w+ ){0,6}?(?:was|remained|continued to be|is) (?:manageable|consistent|tolerable|favou?rable)|"
    r"well[- ]tolerated|very tolerable|no new safety (?:signals|concerns)|"
    r"(?:safety|tolerability) (?:\w+ ){0,6}?consistent with (?:its|the) (?:established|known)|"
    r"reduction in infusion[- ]related reactions", re.I)
PRESS_CONVENIENCE = re.compile(
    r"administration time[^.]{0,60}|(?:in|of) (?:five|5|a few) minutes or less|from hours to minutes|"
    r"(?:fast|more|highly) convenient[^.]{0,40}|convenient (?:treatment|option|dosing|administration)[^.]{0,30}|"
    r"all-oral[^.]{0,40}|once[- ](?:daily|monthly)[^.]{0,30}(?:oral|subcutaneous)", re.I)
COST_CUE = re.compile(r"cost[- ]effective|cost-utility|\bICER\b|\bQALY|willingness[- ]to[- ]pay|cost saving|"
                      r"economic|\bcosts?\b|expensive|affordab|budget", re.I)


def _cue_span(text, m):
    span = m.group(0).strip(" ,;:.")
    return span if span and span in text else None


def fill_aspect_rules(r, base, policy, src):
    """High-precision cue extraction for aspects the heads rarely emit (designed on the silver pool)."""
    text, pm = r["text"], policy.get("polarity_model")
    if src in ("press_release", "news"):
        if base["safety"] is None:
            m = PRESS_SAFETY.search(text)
            if m and (span := _cue_span(text, m)):
                neutral = re.search(r"no new|consistent", span, re.I)
                base["safety"] = {"polarity": 0 if neutral else 1, "speaker": SPEAKER[src], "span": span}
        if base["convenience"] is None:
            m = PRESS_CONVENIENCE.search(text)
            if m and (span := _cue_span(text, m)):
                base["convenience"] = {"polarity": 1, "speaker": SPEAKER[src], "span": span}
    if src == "pubmed" and base["access_cost"] is None and base["signal_type"] == "access_pricing":
        sents = [x for x in sentences(r) if COST_CUE.search(x["text"])]
        if sents:
            sent = sents[-1]
            s0, e0 = trim(text, sent["start"], sent["end"])
            s0 = strip_header(text, s0, e0)
            quote = text[s0:e0]
            words = quote.split()
            if len(words) > 20:
                m = COST_CUE.search(quote)
                left = len(quote[:m.start()].split())
                lo = max(0, left - 6)
                piece = " ".join(words[lo:lo + 14])
                quote = piece if piece in text else quote
            polarity = -1
            if pm is not None:
                probs = pm.probs(r, "access_cost", text[s0:e0])
                polarity = max(probs, key=probs.get)
            base["access_cost"] = {"polarity": polarity, "speaker": SPEAKER[src], "span": quote}


LABEL_SAFETY = [
    re.compile(r"to reduce the risk(?: and severity)? of [\w -]{3,40}?(?:reactions|events|toxicity)", re.I),
    re.compile(r"Permanently discontinue(?: [A-Z][A-Za-z]+(?: and [a-z]+)?)?", re.I),
    re.compile(r"[Ww]ithhold [A-Z]{3,}(?: and [a-z]+)?(?: until [^.]{0,60}?(?=\s(?:or|and)\s|[.;]))?"),
    re.compile(r"(?:Boxed Warning|WARNING:)[^.]{0,60}", re.I),
]
LABEL_CONVENIENCE = [
    (1, re.compile(r"may switch to [^.]{0,80}?every 4-week dosing regimen", re.I)),
    (1, re.compile(r"every 4-week dosing regimen", re.I)),
    (-1, re.compile(r"(?:prophylactic and concomitant medications are recommended|"
                    r"Administer prophylactic and concomitant medications|premedicat\w+ [^.]{0,40})", re.I)),
]


def fill_label_rules(r, base):
    """fda_label diffs: discontinue/withhold/risk-reduction -> safety -1; dosing burden -> convenience (regulator)."""
    if r["source"] != "fda_label" or base["signal_type"] != "regulatory":
        return
    text = r["text"]
    new = text.split("Removed text:")[0]
    if base["safety"] is None:
        for pat in LABEL_SAFETY:
            m = pat.search(new)
            if m and (span := _cue_span(text, m)) and "…" not in span:
                base["safety"] = {"polarity": -1, "speaker": "regulator", "span": span}
                break
    if base["convenience"] is None:
        for pol, pat in LABEL_CONVENIENCE:
            m = pat.search(new)
            if m and (span := _cue_span(text, m)) and "…" not in span:
                base["convenience"] = {"polarity": pol, "speaker": "regulator", "span": span}
                break


def compose(rows, raw, policy, heads=None):
    """Build submission rows: L3 base plus head overrides chosen by the policy."""
    out = {}
    from rules4 import predict as predict_l4
    for r in rows:
        sig = policy.get("model_signal", {}).get(r["item_id"])
        base = predict_l4(r, policy.get("l4_flags"), sig) if policy.get("base") == "l4" else predict(r, 3)
        h = raw.get(r["item_id"])
        if policy.get("label_rules"):
            fill_label_rules(r, base)
        if h is None or r["source"] not in MODEL_SOURCES:
            out[r["item_id"]] = base
            continue
        src = r["source"]
        if src in policy.get("llm_signal_sources", ()) and policy.get("llm") is not None:
            from llm_feats import zero_shot_signal
            base["signal_type"] = zero_shot_signal(policy["llm"], r)
            if base["signal_type"] in ("none", "competitor_move") and policy.get("llm_signal_clear_actionable"):
                base["actionable"] = "no"
        if (src in policy.get("llm_signal_efficacy_sources", ()) and policy.get("llm") is not None
                and base["signal_type"] == "efficacy"):
            from llm_feats import zero_shot_signal
            base["signal_type"] = zero_shot_signal(policy["llm"], r)
        if src in policy.get("signal_sources", ()):
            probs = h[policy.get("signal_head", "signal")]
            best = max(probs, key=probs.get)
            allowed_from = policy.get("signal_from")
            if (probs[best] >= policy.get("signal_min", 0.0)
                    and (allowed_from is None or base["signal_type"] in allowed_from)):
                base["signal_type"] = best
        if src in policy.get("actionable_sources", ()):
            base["actionable"] = "yes" if h["actionable"] >= policy.get("actionable_threshold", 0.5) else "no"
        if src in policy.get("aspect_sources", ()):
            for a, info in h["aspects"].items():
                if policy.get("keep_rules", True) and base[a] is not None:
                    continue
                if policy.get("replace_rules") and base[a] is not None:
                    base[a] = None
                thr = policy.get("presence", {}).get(a, policy.get("presence_default", 0.5))
                stack = policy.get("presence_stack", {}).get(a)
                presence = stack.prob(r, info["presence"]) if stack is not None else info["presence"]
                llm_thr = policy.get("llm_presence", {}).get(a)
                if llm_thr is not None and policy.get("llm") is not None:
                    from llm_feats import presence_score
                    presence = 1.0 if presence_score(policy["llm"], r, a) >= llm_thr else 0.0
                if presence < thr:
                    continue
                xe = policy.get("xenc")
                if xe is not None and info.get("loc_all"):
                    import math
                    sents_ = sentences(r)
                    la = info["loc_all"]
                    order = sorted(range(len(sents_)), key=lambda i: -la[i])[:policy.get("xenc_k", 4)]
                    w = policy.get("xenc_w", 1.0)
                    best = max(order, key=lambda i: math.log(max(la[i], 1e-9)) + w * xe.score(r, a, sents_[i]["text"]))
                    if best != info["sentence"]["id"]:
                        info = {**info, "sentence": sents_[best], "unit_span": None}
                joint = policy.get("joint_span")
                if joint is not None:
                    span, jsent = joint.choose(r, a, info["loc_all"], sentences(r))
                    if jsent is not None:
                        info = {**info, "sentence": jsent}
                elif policy.get("unit_scorer") and info.get("unit_span"):
                    span = info["unit_span"]
                elif policy.get("unit_scorer") and heads is not None and getattr(heads, "units", None):
                    span = heads.units.choose(r, a, info["sentence"])
                else:
                    span = choose_span(r, info["sentence"], policy.get("span_words", 15),
                                       heads.emb if heads and policy.get("unit_spans") else None,
                                       heads.locator[a] if heads else None)
                if not span or span not in r["text"]:
                    continue
                probs = info["polarity_probs"]
                pm = policy.get("polarity_model")
                if pm is not None:
                    on = policy.get("polarity_on", "span")
                    s0, e0 = trim(r["text"], info["sentence"]["start"], info["sentence"]["end"])
                    sentence_text_ = r["text"][s0:e0]
                    if on == "sentence":
                        probs = pm.probs(r, a, sentence_text_)
                    elif on == "both":
                        p1, p2 = pm.probs(r, a, span), pm.probs(r, a, sentence_text_)
                        probs = {k: (p1.get(k, 0) + p2.get(k, 0)) / 2 for k in set(p1) | set(p2)}
                    else:
                        probs = pm.probs(r, a, span)
                    mix = policy.get("polarity_mix")
                    if mix is not None:
                        emb_p = info["polarity_probs"]
                        probs = {k: mix * probs.get(k, 0) + (1 - mix) * emb_p.get(k, 0) for k in set(probs) | set(emb_p)}
                base[a] = {"polarity": pick_polarity(probs, policy.get("polarity_mode", "argmax")),
                           "speaker": SPEAKER[src], "span": span}
        if policy.get("aspect_rules"):
            fill_aspect_rules(r, base, policy, src)
        out[r["item_id"]] = base
    return out


class JointSpan:
    """Pick the quote across the locator's top-k sentences: ridge on span F1 with sentence-score features."""

    def __init__(self, units, k=3, alpha=3.0, length_penalty=0.005):
        self.units, self.k, self.alpha, self.length_penalty = units, k, alpha, length_penalty

    def candidates(self, row, aspect, loc_all, sents):
        import math
        from scipy.sparse import csr_matrix, hstack
        order = sorted(range(len(sents)), key=lambda i: -loc_all[i])[:self.k]
        blocks, spans = [], []
        top = math.log(max(loc_all[order[0]], 1e-9))
        for rank, i in enumerate(order):
            cands, bounds = span_candidates(row, sents[i])
            if not cands:
                continue
            D = self.units.design(row, aspect, cands, bounds)
            lg = math.log(max(loc_all[i], 1e-9))
            extra = np.array([[lg, lg - top, rank == 0, rank == 1, rank == 2] for _ in cands], dtype=np.float32)
            blocks.append(hstack([D, csr_matrix(extra)]).tocsr())
            spans.extend(cands)
        from scipy.sparse import vstack
        return (vstack(blocks).tocsr() if blocks else None), spans

    def fit(self, rows, labels, raw, span_f1):
        from scipy.sparse import vstack
        from sklearn.linear_model import Ridge
        X, y = [], []
        for r in rows:
            info = raw.get(r["item_id"])
            if not info:
                continue
            sents = sentences(r)
            for a in ASP:
                g = labels[r["item_id"]][a]
                if not g or a not in info["aspects"]:
                    continue
                M, spans = self.candidates(r, a, info["aspects"][a]["loc_all"], sents)
                if M is None:
                    continue
                X.append(M)
                y.extend(span_f1(r["text"][p:q], g["span"]) for p, q in spans)
        self.model = Ridge(alpha=self.alpha).fit(vstack(X).tocsr(), np.array(y))
        return self

    def choose(self, row, aspect, loc_all, sents):
        M, spans = self.candidates(row, aspect, loc_all, sents)
        if M is None:
            return None, None
        lengths = np.array([len(row["text"][a:b].split()) for a, b in spans])
        j = int(np.argmax(self.model.predict(M) - self.length_penalty * lengths))
        a, b = spans[j]
        sent = next(s for s in sents if s["start"] <= a < s["end"] + 1)
        return row["text"][a:b], sent
