"""Restore Hugging Face tensor conventions after mlx_lm.fuse on Qwen3.5."""
import argparse
import json
import shutil
from pathlib import Path

from safetensors import safe_open
from safetensors.torch import save_file

NORM_SUFFIXES = (
    ".input_layernorm.weight", ".post_attention_layernorm.weight", "model.norm.weight",
    ".q_norm.weight", ".k_norm.weight",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fused", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    config = json.loads((args.fused / "config.json").read_text())
    if config.get("model_type") != "qwen3_5" or config.get("quantization"):
        parser.error("Expected an already dequantized Qwen3.5 MLX fusion")
    source = args.fused / "model.safetensors"
    tensors = {}
    norms = convolutions = 0
    with safe_open(source, framework="pt", device="cpu") as weights:
        for name in weights.keys():
            if not name.startswith("language_model.model."):
                raise ValueError(f"Unexpected MLX tensor name: {name}")
            value = weights.get_tensor(name)
            if name.endswith(".conv1d.weight"):
                if value.ndim != 3 or value.shape[-1] != 1 or value.shape[1] <= 1:
                    raise ValueError(f"Unexpected MLX convolution layout: {name} {value.shape}")
                value = value.transpose(1, 2).contiguous()
                convolutions += 1
            if name.endswith(NORM_SUFFIXES):
                # MLX stores gamma directly. The GGUF converter adds one to HF gamma.
                value = value.float() - 1
                norms += 1
            target = "model.language_model." + name.removeprefix("language_model.model.")
            tensors[target] = value
        if not norms or not convolutions:
            raise ValueError("Missing expected Qwen3.5 normalization or convolution tensors")
        args.output.mkdir(parents=True)
        for path in args.fused.iterdir():
            if path.is_file() and not path.name.endswith((".safetensors", ".safetensors.index.json")):
                shutil.copy2(path, args.output / path.name)
        save_file(tensors, args.output / "model.safetensors", metadata={"format": "pt"})
    print(f"Restored {norms} norms and {convolutions} convolution layouts")


if __name__ == "__main__":
    main()
