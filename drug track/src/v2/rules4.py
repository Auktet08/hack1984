"""Level 4: signal rules learned from the silver pool (unlabeled teacher labels), applied over Rules L3.

Designed on the silver pool only; the silver holdout and dev are used for evaluation.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rules.predict import predict as predict_l3  # noqa: E402

PM_COST = re.compile(r"cost|economic|budget impact|\bqaly|pricing|afford", re.I)
PM_OPINION = re.compile(r"rethinking|perspective|commentary|editorial", re.I)
PM_REVIEW = re.compile(r"\breview\b", re.I)
PM_SAFETY_EXTRA = re.compile(r"interstitial lung|\bild\b|cardiotox|cardiac|hepatotox|\brash\b|paronychia|\bqt\b|"
                             r"hypersensitiv|infusion[- ]related|side effects?|keratitis|stomatitis|myositis|"
                             r"neutropeni|thrombocytopeni|venous thrombo|\bvte\b", re.I)
PM_EFFICACY_TITLE = re.compile(r"efficac|survival|outcome|response", re.I)
NEWS_DRUGPAGE = re.compile(r"uses, dosing|side effects|oncolink|drugs\.com|medlineplus|plain language|"
                           r"patient information", re.I)

DEFAULT = {"pm_cost": True, "pm_review_efficacy": True, "pm_safety_extra": True, "news_drugpage": True,
           "pm_efficacy_title": True}


def predict(r, flags=None, model_signal=None):
    """L3, then an optional shipped local-model signal override (pubmed/news items L3 calls efficacy), then L4."""
    flags = {**DEFAULT, **(flags or {})}
    o = predict_l3(r, 3)
    s, ti = r["source"], r["title"]
    if model_signal is not None and s in ("pubmed", "news") and o["signal_type"] == "efficacy":
        o["signal_type"] = model_signal
    if s == "pubmed":
        if flags["pm_review_efficacy"] and o["signal_type"] == "expert_opinion" and PM_REVIEW.search(ti) \
                and not PM_OPINION.search(ti):
            o["signal_type"] = "safety" if (re.search(r"adverse|toxicit|safety", ti, re.I)
                                            and not PM_EFFICACY_TITLE.search(ti)) else "efficacy"
        if flags["pm_efficacy_title"] and o["signal_type"] == "safety" and PM_EFFICACY_TITLE.search(ti):
            o["signal_type"] = "efficacy"  # silver pool: safety+efficacy titles are efficacy 17 vs 4
        if flags["pm_safety_extra"] and o["signal_type"] == "efficacy" and PM_SAFETY_EXTRA.search(ti) \
                and not PM_EFFICACY_TITLE.search(ti):
            o["signal_type"] = "safety"
        if flags["pm_cost"] and PM_COST.search(ti):
            o["signal_type"] = "access_pricing"
    elif s == "news":
        if flags["news_drugpage"] and NEWS_DRUGPAGE.search(ti):
            o.update(signal_type="none", actionable="no")
    return o
