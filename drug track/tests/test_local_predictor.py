import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/inference"))
from predict_full import label_local, merge, parse, predict, split, trim


class LocalPredictorTest(unittest.TestCase):
    def setUp(self):
        self.row = {"item_id": "example", "source": "pubmed", "title": "Synthetic study",
                    "product": "A", "text": "  Osimertinib improved PFS, which was consistent with prior data. "
                    "… The researchers noted a low dropout rate."}
        self.units = split(self.row["text"])
        self.reply = {"signal_type": "efficacy", "actionable": "no", "aspects": [
            {"unit_id": 0, "aspect": "efficacy", "polarity": 2}
        ]}

    def test_offsets_and_boundaries(self):
        self.assertEqual(split(""), [])
        self.assertEqual(self.units[0]["text"], "Osimertinib improved PFS")
        for u in self.units:
            self.assertEqual(u["text"], self.row["text"][u["start"]:u["end"]])
            self.assertNotIn("…", u["text"])
            start, end = trim(self.row["text"], u["start"], u["end"])
            self.assertLess(start, end)
            self.assertTrue(u["start"] <= start < end <= u["end"])

    def test_fenced_reply_and_verbatim_merge(self):
        parsed = parse("\x60\x60\x60json\n" + json.dumps(self.reply) + "\n\x60\x60\x60", self.units)
        base = predict(self.row, 3)
        out = merge(self.row, base, parsed, self.units, {"aspects"})
        self.assertEqual(out["efficacy"], {"span": "Osimertinib improved PFS", "polarity": 1,
                                         "speaker": "researcher"})

    def test_bad_unit_falls_back(self):
        self.reply["aspects"][0]["unit_id"] = len(self.units)
        with self.assertRaises(ValueError):
            parse(json.dumps(self.reply), self.units)

    def test_preserves_rule_aspect(self):
        base = predict(self.row, 3)
        base["efficacy"] = {"span": "improved PFS", "polarity": 2, "speaker": "researcher"}
        self.assertEqual(merge(self.row, dict(base), self.reply, self.units, {"aspects"}), base)

    def test_transcript_uses_supplied_speaker_role(self):
        row = {**self.row, "source": "transcript", "speaker_role": "patient"}
        with patch("predict_full.call", return_value=self.reply):
            label = label_local(row, "http://localhost", "test", Path("."))
            self.assertEqual(label["efficacy"]["speaker"], "patient")
            self.assertIn(label["efficacy"]["span"], row["text"])
            row["speaker_role"] = "unknown"
            label = label_local(row, "http://localhost", "test", Path("."))
            self.assertIsNone(label["efficacy"])

    def test_explicit_convenience_requires_the_target_drug(self):
        row = {**self.row, "source": "transcript", "speaker_role": "patient", "product": "B",
               "text": "The longer Rybrevant infusion made treatment more burdensome for me."}
        blank = {"signal_type": "none", "actionable": "no", "aspects": []}
        with patch("predict_full.call", return_value=blank):
            label = label_local(row, "http://localhost", "test", Path("."))
            self.assertEqual(label["convenience"], {"span": "made treatment more burdensome",
                                                   "polarity": -1, "speaker": "patient"})
            label = label_local({**row, "product": "A"}, "http://localhost", "test", Path("."))
            self.assertIsNone(label["convenience"])
            uncertain = {**row, "text": "It is unclear whether the Rybrevant infusion made treatment easier."}
            label = label_local(uncertain, "http://localhost", "test", Path("."))
            self.assertIsNone(label["convenience"])


if __name__ == "__main__":
    unittest.main()
