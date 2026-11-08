"""LoRA cross-encoder (MLX, local): yes/no score that a sentence states the item's judgment on one aspect."""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from make_xenc_data import xenc_prompt  # noqa: E402

ROOT = HERE.parents[1]


class CrossEncoder:
    def __init__(self, adapter, model=ROOT / "models/qwen35-2b-mlx-affine4", cache=ROOT / "out/v2/xenc-cache"):
        self.adapter, self.model_path, self.cache = Path(adapter), Path(model), Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.model = None
        weights = self.adapter / "adapters.safetensors" if self.adapter.is_dir() else self.adapter
        self.tag = hashlib.sha256(weights.read_bytes()).hexdigest()[:16]

    def _load(self):
        if self.model is None:
            from mlx_lm import load
            self.model, self.tok = load(str(self.model_path), adapter_path=str(self.adapter.parent)
                                        if self.adapter.is_file() else str(self.adapter))
            self.yes = self.tok.encode("yes", add_special_tokens=False)[0]
            self.no = self.tok.encode("no", add_special_tokens=False)[0]

    def score(self, row, aspect, sentence):
        prompt = xenc_prompt(row, aspect, sentence)
        key = hashlib.sha256((self.tag + prompt).encode()).hexdigest()
        path = self.cache / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text())
        self._load()
        import mlx.core as mx
        tokens = self.tok.apply_chat_template([{"role": "user", "content": prompt}], tokenize=True,
                                              add_generation_prompt=True, enable_thinking=False, return_dict=False)
        logits = self.model(mx.array([tokens]))[0, -1].astype(mx.float32)
        logp = logits - mx.logsumexp(logits)
        value = float(logp[self.yes].item() - logp[self.no].item())
        path.write_text(json.dumps(value))
        return value
