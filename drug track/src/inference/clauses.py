"""Return evidence units and quotes as slices of the original item text."""
import re

SENTENCE_BREAK = re.compile(r"\[\.\.\.\]|…|\n+|(?<=[.!?])\s+(?=[A-Z])")
CLAUSE_BREAK = re.compile(r"[,;:—](?=\s)|\s+(?=(?:which|whereas|although|because|while|and|or)\b)", re.I)


def split(text, max_words=8, separate_clauses=True):
    units = []

    def add(start, end):
        raw = text[start:end]
        start += len(raw) - len(raw.lstrip())
        end -= len(raw) - len(raw.rstrip())
        if start < end:
            words = list(re.finditer(r"\S+", text[start:end]))
            windows = [(start, end)]
            if len(words) > max_words:
                windows = []
                for i in range(0, len(words), max_words // 2):
                    last = min(i + max_words - 1, len(words) - 1)
                    windows.append((start + words[i].start(), start + words[last].end()))
                    if last == len(words) - 1:
                        break
            for lo, hi in windows:
                units.append({"id": len(units), "start": lo, "end": hi, "text": text[lo:hi]})

    start = 0
    for boundary in [*SENTENCE_BREAK.finditer(text), None]:
        end = boundary.start() if boundary else len(text)
        if separate_clauses:
            for separator in CLAUSE_BREAK.finditer(text, start, end):
                if len(text[start:separator.start()].split()) >= 3 and len(text[separator.end():end].split()) >= 3:
                    add(start, separator.start())
                    start = separator.end()
        add(start, end)
        if boundary:
            start = boundary.end()
    return units


def trim(text, start, end):
    raw = text[start:end]
    return start, start + len(raw.rstrip(" ,;:.!?") or raw)
