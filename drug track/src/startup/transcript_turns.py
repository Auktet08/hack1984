#!/usr/bin/env python3
"""Split the FDA poziotinib ODAC transcript (22 Sep 2022, morning session) into speaker turns (STARTUP.md S3).

    python3 "drug track/src/startup/transcript_turns.py"

Reads research/raw/odac-2022-09-22-poziotinib/transcript.txt (pdftotext output) and writes
out/startup/poziotinib_odac_turns.jsonl, one row per turn in the track's item shape plus speaker fields.
Turns longer than --max-words are cut at sentence ends into parts, so each labeled unit stays local.

The PDF's split words ("cli nical") are kept as they are: spans must be verbatim from this cleaned text,
not from the PDF.
"""
import argparse, json, re
from pathlib import Path

PKG = Path(__file__).resolve().parents[2]
SRC = PKG / "research/raw/odac-2022-09-22-poziotinib/transcript.txt"
OUT = PKG / "out/startup/poziotinib_odac_turns.jsonl"
URL = "https://www.fda.gov/advisory-committees/human-drug-advisory-committees/oncologic-drugs-advisory-committee"

# Roles from the meeting roster (pages 2-9) and, for open-public-hearing speakers, their self-introductions.
# group: committee | fda | applicant | public. speaker: the track schema's speaker value for their opinions.
ROLES = {
    **{n: ("committee", "hcp", "ODAC member, oncologist") for n in
       ["GARCIA", "KUNZ", "LIEU", "MADAN", "ROSKO", "SUNG", "HALMOS", "SCILLA", "THOMAS", "WALDMAN"]},
    "HARRINGTON": ("committee", "researcher", "ODAC temporary member, biostatistician"),
    "MITCHELL": ("committee", "patient", "ODAC consumer representative, cancer patient"),
    "PANTELAS": ("committee", "patient", "ODAC patient representative"),
    "KRAUS": ("committee", "company", "acting industry representative (Pfizer), non-voting"),
    **{n: ("fda", "regulator", "FDA") for n in
       ["CHEN", "PAZDUR", "BEAVER", "SINGH", "DREZNER", "MALINOU", "ZIRKELBACH"]},
    "LEBEL": ("applicant", "company", "Spectrum Pharmaceuticals"),
    "BHAT": ("applicant", "company", "Spectrum Pharmaceuticals"),
    "HEYMACH": ("applicant", "researcher", "investigator presenting for Spectrum (MD Anderson)"),
    "SOCINSKI": ("applicant", "hcp", "oncologist presenting for Spectrum"),
    "GRAY": ("applicant", "hcp", "oncologist answering for Spectrum (Moffitt)"),
    **{n: ("public", "patient", "open public hearing: patient, caregiver or advocate") for n in
       ["JOHNSON", "FILIPIAK", "URBANO", "BRAND", "LENIZ", "MODICA"]},
    "SABARI": ("public", "hcp", "open public hearing: thoracic oncologist (NYU)"),
    "BOCKER": ("public", "researcher", "open public hearing: cancer drug discovery scientist"),
}
PAGE_HEADER = re.compile(r"^(FDA ODAC\s+September|A Matter of Record|\(301\) 890-4188|\s*\d+\s*$)")
TAG = re.compile(r"\b(DR|MR|MS|MRS)\. ([A-Z][A-Z'-]+):\s+")
SECTIONS = [("Introduction of Committee", "introductions"), ("Conflict of Interest Statement", "conflicts"),
            ("FDA Introductory Comments", "fda_intro"), ("Applicant Presentation", "applicant"),
            ("FDA Presentation", "fda_presentation"), ("Clarifying Questions to Presenters", "clarifying"),
            ("Open Public Hearing", "open_public_hearing"),
            ("Questions to the Committee and Discu", "discussion")]


def clean_lines(path):
    """Drop page headers and the trailing line numbers; return (page, text) per transcript line."""
    out, page = [], 1
    for raw in open(path, encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        if re.match(r"^\d+\s*$", line.strip()) and not line.startswith(" "):
            page = int(line.strip())
        if PAGE_HEADER.match(line):
            continue
        line = re.sub(r"\s+\d{1,2}\s*$", "", line)  # line number at the right margin
        out.append((page, line.strip()))
    return out


def sentence_parts(text, max_words):
    """Cut a long turn at sentence ends into parts of at most ~max_words words."""
    sents = re.findall(r"[^.!?]+[.!?]+[\"')\]]*\s*|[^.!?]+$", text)
    parts, cur = [], ""
    for s in sents:
        if cur and len((cur + s).split()) > max_words:
            parts.append(cur.strip())
            cur = ""
        cur += s
    if cur.strip():
        parts.append(cur.strip())
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--max-words", type=int, default=200)
    a = ap.parse_args()

    lines = clean_lines(a.src)
    start = next(i for i, (_, l) in enumerate(lines) if "P R O C E E D I N G S" in l)
    section, turns, cur = "call_to_order", [], None
    for page, line in lines[start + 1:]:
        for marker, name in SECTIONS:
            if line.startswith(marker):
                section = name
                line = ""  # section titles are not speech
        if not line:
            continue
        pieces = TAG.split(line)  # [before, title, NAME, rest, title, NAME, rest...]
        if cur is not None and pieces[0].strip():
            cur["text"] += " " + pieces[0].strip()
        for j in range(1, len(pieces), 3):
            cur = {"name": f"{pieces[j]}. {pieces[j + 1]}", "surname": pieces[j + 1], "page": page,
                   "section": section, "text": pieces[j + 2].strip()}
            turns.append(cur)

    unknown = sorted({t["surname"] for t in turns if t["surname"] not in ROLES})
    n = 0
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w") as fo:
        for ti, t in enumerate(turns, 1):
            group, speaker, desc = ROLES.get(t["surname"], ("unknown", "unknown", "not on roster"))
            text = re.sub(r"\s+", " ", t["text"]).strip()
            parts = sentence_parts(text, a.max_words)
            for pi, part in enumerate(parts, 1):
                n += 1
                fo.write(json.dumps({
                    "item_id": f"ODAC22-T{ti:03d}" + (f"-{pi}" if len(parts) > 1 else ""),
                    "source": "transcript", "product": "poziotinib", "published": "2022-09-22", "url": URL,
                    "title": f"{t['name']} ({desc}) speaking at the FDA ODAC meeting on poziotinib",
                    "text": part, "speaker_name": t["name"], "speaker_group": group,
                    "speaker_role": speaker, "section": t["section"], "page": t["page"],
                    "turn": ti, "part": pi, "words": len(part.split()),
                }, ensure_ascii=False) + "\n")
    print(f"{len(turns)} turns -> {n} rows in {a.out}")
    if unknown:
        print("speakers not in ROLES:", ", ".join(unknown))


if __name__ == "__main__":
    main()
