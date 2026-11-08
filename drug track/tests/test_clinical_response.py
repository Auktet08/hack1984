import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/eval"))
from clinical_response import shortlist
from rank_response import CODES, background_units, propose


class ClinicalResponseTest(unittest.TestCase):
    def test_broad_retrieval_keeps_preceding_attribution(self):
        row = {"product": "B", "text": "The patient started lazertinib. Follow-up imaging showed tumor regression."}
        units = shortlist(row, broad=True)
        outcome = next(unit for unit in units if "regression" in unit[2])
        self.assertEqual(outcome[3], "The patient started lazertinib.")

    def test_ranker_can_abstain_and_reject_preclinical_evidence(self):
        row = {"product": "A", "text": "In vitro, osimertinib reduced tumor cell survival."}
        with patch("rank_response.scores") as scores:
            self.assertIsNone(propose(row, "", Path("."), dict.fromkeys(CODES, 0), clinical_scope=True))
        scores.assert_not_called()
        row["text"] = "Tumor response was assessed after starting osimertinib."
        with patch("rank_response.scores", return_value={" A": -2, " B": -3, " C": -4, " D": -1}):
            self.assertIsNone(propose(row, "", Path("."), dict.fromkeys(CODES, 0)))

    def test_unreported_class_score_is_not_treated_as_evidence(self):
        row = {"product": "A", "text": "The patient had a response on osimertinib."}
        with patch("rank_response.scores", return_value={" A": -0.1}):
            self.assertIsNone(propose(row, "", Path("."), dict.fromkeys(CODES, 0)))

    def test_case_recurrence_blocks_favorable_background(self):
        background = "BACKGROUND: A prior trial found improved survival with osimertinib."
        case = "CASE PRESENTATION: The patient had a local recurrence after treatment with osimertinib."
        row = {"product": "A", "text": background + " " + case}
        units = [(True, 0, background, ""), (True, 1, case, "")]
        self.assertEqual(background_units(row, units), {0})
        self.assertEqual(background_units({**row, "text": background}, units[:1]), set())


if __name__ == "__main__":
    unittest.main()
