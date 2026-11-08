"""Cache local Qwen mean-pooled embeddings for items, sentences and clause units (loopback only)."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.request import Request

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "inference"), str(HERE.parent)]
from clauses import split, trim  # noqa: E402
from predict_full import LOCAL_HTTP, load_rows  # noqa: E402

MAX_ITEM_CHARS = 7000


def item_text(row):
    return f'Source: {row["source"]}. Product: {row["product"]}. Title: {row["title"]}\n{row["text"]}'[:MAX_ITEM_CHARS]


def sentences(row):
    return split(row["text"], max_words=100000, separate_clauses=False)


def units(row):
    out = []
    for u in split(row["text"]):
        s, e = trim(row["text"], u["start"], u["end"])
        out.append({**u, "start": s, "end": e, "text": row["text"][s:e]})
    return out


def sentence_text(row, sent):
    return f'Source: {row["source"]}. Title: {row["title"]}\nSentence: {sent["text"]}'


class Embedder:
    def __init__(self, port, cache_dir):
        self.url = f"http://127.0.0.1:{port}/embedding"
        self.cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.store_path = cache_dir / "store.npz"
        self.store = {}
        if self.store_path.exists():
            data = np.load(self.store_path)
            self.store = dict(zip(data["keys"].tolist(), data["vecs"]))

    @staticmethod
    def key(text):
        return hashlib.sha256(text.encode()).hexdigest()[:32]

    def embed(self, texts, batch=32):
        missing = list(dict.fromkeys(t for t in texts if self.key(t) not in self.store))
        for i in range(0, len(missing), batch):
            chunk = missing[i:i + batch]
            req = Request(self.url, json.dumps({"content": chunk}).encode(), {"Content-Type": "application/json"})
            with LOCAL_HTTP.open(req, timeout=600) as response:
                reply = json.load(response)
            for entry in reply:
                vec = np.asarray(entry["embedding"], dtype=np.float32).reshape(-1)
                self.store[self.key(chunk[entry["index"]])] = vec
            if (i // batch) % 20 == 0:
                print(f"  embedded {i + len(chunk)}/{len(missing)}", flush=True)
        return np.stack([self.store[self.key(t)] for t in texts]) if texts else np.zeros((0, 1), np.float32)

    def save(self):
        keys = np.array(list(self.store))
        vecs = np.stack(list(self.store.values()))
        tmp = self.cache_dir / "store.tmp.npz"
        np.savez(tmp, keys=keys, vecs=vecs)
        tmp.replace(self.store_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--port", type=int, default=18090)
    ap.add_argument("--cache", type=Path, default=Path("out/v2/emb"))
    ap.add_argument("--sources", default="pubmed,news,press_release,fda_label")
    ap.add_argument("--no-units", action="store_true")
    args = ap.parse_args()
    sources = set(args.sources.split(","))
    emb = Embedder(args.port, args.cache)
    for path in args.files:
        rows = [r for r in load_rows(path) if r["source"] in sources]
        print(path, len(rows), "items", flush=True)
        emb.embed([item_text(r) for r in rows], batch=4)
        emb.save()
        sent = [sentence_text(r, s) for r in rows for s in sentences(r)]
        print(" sentences", len(sent), flush=True)
        emb.embed(sent)
        emb.save()
        if not args.no_units:
            unit_texts = [u["text"] for r in rows for u in units(r)]
            print(" units", len(unit_texts), flush=True)
            emb.embed(unit_texts, batch=64)
            emb.save()


if __name__ == "__main__":
    main()
