"""U1: the startup file contracts. Run from the repo root:
    python3 -m unittest discover -s "drug track/tests" -t "drug track"
"""
import copy
import json
import unittest

from contracts import validate as v


def fixture(name):
    return v.read_docs(v.FIX / name)


def first(name):
    return copy.deepcopy(fixture(name)[0][1])


class FixturesValidate(unittest.TestCase):
    def test_every_fixture_passes_schema_and_semantic_checks(self):
        for path, errs in v.validate_files(v.FIXTURES).items():
            with self.subTest(path=path):
                self.assertEqual(errs, [])

    def test_every_evidence_span_is_exact_at_its_offset(self):
        for _, rec in fixture("triage.sample.jsonl"):
            for key, crit in rec["criteria"].items():
                for ev in crit["evidence"]:
                    hay = rec["texts"][ev["item_id"]] if ev["field"] == "text" else rec["source"]["speaker_name"]
                    with self.subTest(case=rec["case_id"], criterion=key, span=ev["span"]):
                        self.assertEqual(hay[ev["start"]:ev["start"] + len(ev["span"])], ev["span"])

    def test_shifted_offset_is_caught(self):
        rec = first("triage.sample.jsonl")
        rec["criteria"]["adverse_event"]["evidence"][0]["start"] += 1
        errs = v.validate_docs("triage_record", [("t", rec)])
        self.assertTrue(any("not at offset" in e for e in errs), errs)


class TriageRules(unittest.TestCase):
    def test_candidate_with_missing_criterion_fails(self):
        rec = first("triage.sample.jsonl")
        self.assertEqual(rec["status"], "candidate")
        rec["missing"] = ["identifiable_patient"]
        self.assertTrue(v.schema_errors("triage_record", rec))

    def test_incomplete_without_missing_fails(self):
        rec = next(d for _, d in fixture("triage.sample.jsonl") if d["status"] == "incomplete")
        rec = copy.deepcopy(rec)
        rec["missing"] = []
        self.assertTrue(v.schema_errors("triage_record", rec))

    def test_met_criterion_needs_evidence(self):
        rec = first("triage.sample.jsonl")
        rec["criteria"]["suspect_product"]["evidence"] = []
        self.assertTrue(v.schema_errors("triage_record", rec))

    def test_unmet_criterion_needs_a_reason(self):
        rec = next(copy.deepcopy(d) for _, d in fixture("triage.sample.jsonl") if d["status"] == "incomplete")
        rec["criteria"]["identifiable_patient"]["why"] = None
        self.assertTrue(v.schema_errors("triage_record", rec))

    def test_word_reportable_never_appears(self):
        for name in ("triage.sample.jsonl", "triage_audit.sample.jsonl"):
            raw = (v.FIX / name).read_text().lower()
            self.assertNotIn("reportable", raw, name)

    def test_demo_pair_matches_acceptance_examples(self):
        recs = {d["case_id"]: d for _, d in fixture("triage.sample.jsonl")}
        t151 = recs["TRI-ODAC22-T151"]  # AE1
        self.assertEqual(t151["status"], "candidate")
        self.assertEqual(t151["criteria"]["adverse_event"]["evidence"][0]["span"], "diarrhea")
        self.assertEqual(t151["criteria"]["adverse_event"]["evidence"][0]["item_id"], "ODAC22-T151-2")
        self.assertEqual(t151["safety_hint"]["polarity"], 1)
        t054 = recs["TRI-ODAC22-T054"]  # AE2
        self.assertEqual(t054["missing"], ["identifiable_patient"])
        self.assertIn("82 percent of patients", t054["criteria"]["identifiable_patient"]["why"])
        self.assertIn("TRI-ODAC22-T147", recs)  # AE3


class AuditRules(unittest.TestCase):
    def test_bad_decision_fails(self):
        line = first("triage_audit.sample.jsonl")
        line["decision"] = "reportable"
        self.assertTrue(v.schema_errors("triage_audit", line))

    def test_decided_at_needs_offset(self):
        line = first("triage_audit.sample.jsonl")
        line["decided_at"] = "2026-11-07T20:05:00"
        self.assertTrue(v.schema_errors("triage_audit", line))


class GapView(unittest.TestCase):
    def test_flags_match_ae4(self):
        gap = fixture("gap_poziotinib.sample.json")[0][1]
        got = {(f["kind"], f["aspect"], f["side"], tuple(f["columns"]) if f["kind"] == "split" else None)
               for f in gap["flags"]}
        self.assertEqual(got, {
            ("split", "efficacy", None, ("fda", "public_hearing")),
            ("split", "safety", None, ("fda", "applicant")),
            ("thin", "access_cost", "both", None),
            ("thin", "convenience", "public", None),
        })
        self.assertTrue(gap["provenance"]["stand_in"])

    def test_empty_cell_must_have_null_mean(self):
        gap = fixture("gap_poziotinib.sample.json")[0][1]
        cell = next(c for c in gap["cells"] if c["n"] == 0)
        cell["mean"] = 0.0
        self.assertTrue(v.schema_errors("gap_view", gap))


class LabelCost(unittest.TestCase):
    def test_stand_in_must_have_left_device(self):
        cost = first("odac.gemini.cost.sample.json")
        cost["data_left_device"] = False
        self.assertTrue(v.schema_errors("label_cost", cost))

    def test_usd_total_must_match_tokens_times_price(self):
        cost = first("odac.gemini.cost.sample.json")
        cost["usd_total"] *= 2
        self.assertTrue(v.validate_docs("label_cost", [("c", cost)]))


class LabelRows(unittest.TestCase):
    def test_unknown_keys_are_allowed(self):
        row = first("odac_labels.sample.jsonl")
        row["some_new_field"] = 1
        self.assertEqual(v.schema_errors("label_row", row), [])

    @unittest.skipUnless((v.OUT / "labels" / "odac.jsonl").exists(), "out/startup/labels/odac.jsonl not built")
    def test_real_odac_rows_validate(self):
        errs = v.validate_docs("label_row", v.read_docs(v.OUT / "labels" / "odac.jsonl"))
        self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main()
