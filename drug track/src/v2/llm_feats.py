"""Local Qwen next-token scores used as features: 5-point polarity rating of a quote for one aspect."""
import hashlib
import json
import math
import sys
from pathlib import Path
from urllib.request import Request

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "inference")]
from predict_full import LOCAL_HTTP, PRODUCT_NAMES  # noqa: E402

LETTERS = ["A", "B", "C", "D", "E"]
ASPECT_HINT = {
    "efficacy": "efficacy (does it work: response, survival, progression, benefit, resistance)",
    "safety": "safety (side effects, adverse events, toxicity, tolerability)",
    "convenience": "convenience (dosing, administration, treatment burden)",
    "access_cost": "access and cost (price, coverage, reimbursement, cost-effectiveness, availability)",
    "evidence_quality": "evidence quality (study design strength, sample size, retrospective design, follow-up)",
}


def polarity_prompt(row, aspect, quote, context=0):
    target = PRODUCT_NAMES.get(row["product"], row["product"])
    ctx = f"Text: {row['text'][:context]}\n" if context else ""
    return (
        f"A {row['source']} item about {target}.\n"
        f"Title: {row['title']}\n{ctx}"
        f"Quote: \"{quote}\"\n\n"
        f"How does this quote judge the target drug on {ASPECT_HINT[aspect]}?\n"
        "A = strongly negative (failed, fatal, boxed warning)\n"
        "B = mildly negative (a concern, more frequent, limited, retrospective, small sample)\n"
        "C = neutral or mixed (mentioned, comparable, no new safety signals)\n"
        "D = mildly positive (encouraging, manageable, well tolerated, improved)\n"
        "E = strongly positive (significantly prolonged, statistically significant and clinically meaningful)\n"
        "When unsure between two levels, pick the milder one. Answer with one letter."
    )


class LLM:
    def __init__(self, port=18080, cache=Path("out/v2/llm-cache")):
        self.base = f"http://127.0.0.1:{port}"
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)

    def _post(self, path, payload, timeout=60):
        req = Request(self.base + path, json.dumps(payload).encode(), {"Content-Type": "application/json"})
        with LOCAL_HTTP.open(req, timeout=timeout) as response:
            return json.load(response)

    def letter_scores(self, message, letters=LETTERS):
        key = hashlib.sha256((self.base + message + "".join(letters)).encode()).hexdigest()
        path = self.cache / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text())
        prompt = self._post("/apply-template", {"messages": [{"role": "user", "content": message}],
                                                "chat_template_kwargs": {"enable_thinking": False}})["prompt"]
        reply = self._post("/completion", {"prompt": prompt, "n_predict": 1, "n_probs": 64, "temperature": -1,
                                           "post_sampling_probs": False, "cache_prompt": True})
        alts = reply["completion_probabilities"][0]["top_logprobs"]
        mass = {c: sum(math.exp(a["logprob"]) for a in alts if a["token"].strip() == c) for c in letters}
        total = sum(mass.values()) or 1.0
        out = [math.log(max(mass[c] / total, 1e-6)) for c in letters]
        path.write_text(json.dumps(out))
        return out

    def polarity(self, row, aspect, quote, context=0):
        return self.letter_scores(polarity_prompt(row, aspect, quote, context))


class PolarityModel:
    """Logistic calibration of local-Qwen 5-point ratings (+ aspect/source), trained on teacher quotes."""

    def __init__(self, llm, C=1.0, context=0):
        self.llm, self.C, self.context = llm, C, context

    def features(self, row, aspect, quote):
        import numpy as np
        f = self.llm.polarity(row, aspect, quote, getattr(self, "context", 0))
        return np.array(f + [aspect == a for a in ASPECT_HINT] +
                        [row["source"] == s for s in ("pubmed", "news", "press_release")], dtype=float)

    def fit(self, rows, labels):
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        X, y = [], []
        for r in rows:
            for a in ASPECT_HINT:
                g = labels[r["item_id"]][a]
                if g:
                    X.append(self.features(r, a, g["span"]))
                    y.append(g["polarity"])
        self.model = LogisticRegression(C=self.C, max_iter=3000).fit(np.array(X), y)
        return self

    def probs(self, row, aspect, quote):
        p = self.model.predict_proba(self.features(row, aspect, quote)[None])[0]
        return {int(k): float(v) for k, v in zip(self.model.classes_, p)}


def locate_prompt(row, aspect, quotes):
    target = PRODUCT_NAMES.get(row["product"], row["product"])
    opts = "\n".join(f"{LETTERS[i]}: {q}" for i, q in enumerate(quotes))
    return (
        f"A {row['source']} item about {target}.\nTitle: {row['title']}\n\n"
        f"Which sentence most directly states a judgment of the target drug on {ASPECT_HINT[aspect]}? "
        "Prefer the paper's own findings or conclusions over background or methods.\n"
        f"{opts}\nAnswer with one letter."
    )


class Locator:
    """Re-rank the embedding locator's top-k sentences with a local-Qwen multiple-choice score."""

    def __init__(self, llm, k=4, w=1.0):
        self.llm, self.k, self.w = llm, k, w

    def scores(self, row, aspect, sents, loc_all):
        import math
        order = sorted(range(len(sents)), key=lambda i: -loc_all[i])[:self.k]
        if len(order) < 2:
            return order, [0.0] * len(order), [math.log(max(loc_all[i], 1e-9)) for i in order]
        llm = self.llm.letter_scores(locate_prompt(row, aspect, [sents[i]["text"] for i in order]),
                                     LETTERS[:len(order)])
        return order, llm, [math.log(max(loc_all[i], 1e-9)) for i in order]

    def choose(self, row, aspect, sents, loc_all, w=None):
        w = self.w if w is None else w
        order, llm, loc = self.scores(row, aspect, sents, loc_all)
        best = max(range(len(order)), key=lambda j: loc[j] + w * llm[j])
        return sents[order[best]]


def judge_prompt(row, aspect, sentence):
    target = PRODUCT_NAMES.get(row["product"], row["product"])
    return (
        f"A {row['source']} item about {target}.\nTitle: {row['title']}\n"
        f"Sentence: \"{sentence}\"\n\n"
        f"Does this sentence itself state a judgment (positive, negative or neutral) of the target drug on "
        f"{ASPECT_HINT[aspect]}? Background, aims and methods without a finding do not count. Answer yes or no."
    )


def judge_score(llm, row, aspect, sentence):
    yes, no = llm.letter_scores(judge_prompt(row, aspect, sentence), ["yes", "no"])
    return yes - no


SIGNAL_CLASSES = ["efficacy", "safety", "regulatory", "competitor_move", "access_pricing", "guideline",
                  "expert_opinion", "none", "trial_update"]
SIGNAL_DESC = {
    "efficacy": "outcome or effectiveness data for the target drug",
    "safety": "side effects, adverse events, warnings",
    "regulatory": "approvals, label changes, regulator actions or filings",
    "competitor_move": "a rival drug or company news framed against the target drug (rival results, rival approvals, business/earnings)",
    "access_pricing": "coverage, reimbursement, price, HTA or cost-effectiveness",
    "guideline": "guideline or treatment pathway changes",
    "expert_opinion": "commentary, explainers with views, reviews or patient/clinician opinions with no new data",
    "none": "nothing new about the target drug (passing mention, drug information page, market report)",
    "trial_update": "trial registration, start, status or protocol news",
}
SIGNAL_LETTERS = "ABCDEFGHI"


def signal_prompt(row):
    target = PRODUCT_NAMES.get(row["product"], row["product"])
    opts = "\n".join(f"{SIGNAL_LETTERS[i]} = {c}: {SIGNAL_DESC[c]}" for i, c in enumerate(SIGNAL_CLASSES))
    return (f"A {row['source']} item about {target}.\nTitle: {row['title']}\nText: {row['text'][:1500]}\n\n"
            f"What is the MAIN kind of signal this item reports about the target drug?\n{opts}\nAnswer with one letter.")


def zero_shot_signal(llm, row):
    scores = llm.letter_scores(signal_prompt(row), list(SIGNAL_LETTERS))
    return SIGNAL_CLASSES[max(range(len(scores)), key=scores.__getitem__)]


def actionable_prompt(row):
    target = PRODUCT_NAMES.get(row["product"], row["product"])
    return (
        f"A {row['source']} item about {target}.\nTitle: {row['title']}\nText: {row['text'][:1500]}\n\n"
        "Would a launch team for this drug plausibly change a plan, message or priority because of this item? "
        "New pivotal data, label changes, new indications, guideline changes, competitor moves, HTA or reimbursement "
        "decisions usually yes. Repeats, routine updates, single case reports, small retrospective or lab studies "
        "usually no. Answer yes or no."
    )


def actionable_score(llm, row):
    yes, no = llm.letter_scores(actionable_prompt(row), ["yes", "no"])
    return yes - no


def presence_prompt(row, aspect):
    target = PRODUCT_NAMES.get(row["product"], row["product"])
    return (
        f"A {row['source']} item about {target}.\nTitle: {row['title']}\nText: {row['text'][:2000]}\n\n"
        f"Does this text make a judgment (positive, negative or neutral) about the target drug's {ASPECT_HINT[aspect]}? "
        "Answer yes or no."
    )


def presence_score(llm, row, aspect):
    yes, no = llm.letter_scores(presence_prompt(row, aspect), ["yes", "no"])
    return yes - no


class PresenceStack:
    """Stack the embedding presence head with a local-Qwen item-level yes/no judgment for one aspect."""

    def __init__(self, llm, aspect):
        self.llm, self.aspect = llm, aspect

    def features(self, row, emb_presence):
        import math
        import numpy as np
        p = min(max(emb_presence, 1e-6), 1 - 1e-6)
        return np.array([math.log(p / (1 - p)), presence_score(self.llm, row, self.aspect)] +
                        [row["source"] == s for s in ("pubmed", "news", "press_release")], dtype=float)

    def fit(self, rows, labels, raw):
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        rows = [r for r in rows if r["item_id"] in raw and self.aspect in raw[r["item_id"]]["aspects"]]
        X = np.array([self.features(r, raw[r["item_id"]]["aspects"][self.aspect]["presence"]) for r in rows])
        y = [labels[r["item_id"]][self.aspect] is not None for r in rows]
        self.model = LogisticRegression(max_iter=2000).fit(X, y)
        return self

    def prob(self, row, emb_presence):
        return float(self.model.predict_proba(self.features(row, emb_presence)[None])[0, 1])
