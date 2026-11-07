# Mac toolchain check: Qwen3.5-2B

**For:** whoever has the MacBook Pro. **Takes:** about 20–30 minutes, mostly downloads (about 8 GB).
**Needs:** the Mac on Wi-Fi, Homebrew, Python 3.9 or newer, about 15 GB free disk.

**Why:** we want to run a small local model, Qwen3.5-2B, on this Mac for the hackathon. Before building on it we need to know four things: that it loads, that it can be forced to answer in JSON, that it can be fine-tuned, and how fast it is.

**No hackathon data is involved.** Every test below uses made-up sentences, so nothing private is on this machine yet.

**If a step fails, don't debug it.** Copy the error into the Results table and move on to the next step.

---

## Step 0: what machine is this?

```bash
sysctl -n machdep.cpu.brand_string
echo "RAM: $(( $(sysctl -n hw.memsize) / 1073741824 )) GB"
df -h ~ | tail -1
sw_vers -productVersion
python3 -c "import platform, sys; print(platform.machine(), sys.version.split()[0])"
```

The last line must say `arm64`. If it says `x86_64`, Python is running under Rosetta and MLX won't install. Use a native Python, for example `brew install python`, then `/opt/homebrew/bin/python3`.

## Step 1: install (in a throwaway folder)

```bash
mkdir -p ~/hack1984-check && cd ~/hack1984-check
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip mlx-lm
brew install llama.cpp
pip show mlx-lm | grep Version
llama-server --version
```

## Step 2: run the model with MLX, thinking off

The first run downloads the model (about 5 GB).

```bash
mlx_lm.generate --model Qwen/Qwen3.5-2B --max-tokens 200 \
  --chat-template-config '{"enable_thinking": false}' \
  --prompt 'Return JSON with keys "aspect" and "polarity" for this sentence: "Osimertinib significantly improved progression-free survival." aspect is efficacy or safety; polarity is an integer from -2 to 2.'
```

Note three things:
- Does it answer?
- Does the answer contain `<think>`? It shouldn't.
- What do the two speed lines at the end say (`Prompt: … tokens-per-sec` and `Generation: … tokens-per-sec`)?

If it fails with something like "model type qwen3_5 not supported", install the newest mlx-lm from GitHub and run step 2 again:

```bash
pip install -U git+https://github.com/ml-explore/mlx-lm
```

**Long-prompt speed.** Our real prompts are about 2,000 tokens, so prompt speed matters most:

```bash
mlx_lm.generate --model Qwen/Qwen3.5-2B --max-tokens 50 \
  --chat-template-config '{"enable_thinking": false}' \
  --prompt "$(python3 -c "print('The trial met its primary endpoint. ' * 250 + 'Summarize the text in one sentence.')")"
```

Write down both speed lines.

## Step 3: 10-step fine-tune on fake data

```bash
mkdir -p lora_data
python3 - <<'EOF'
import json
ex = [{"messages": [
        {"role": "user", "content": f"Label sentence {i}: the drug was well tolerated."},
        {"role": "assistant", "content": '{"aspect": "safety", "polarity": 1}'}]}
      for i in range(12)]
open("lora_data/train.jsonl", "w").write("\n".join(json.dumps(e) for e in ex[:8]) + "\n")
open("lora_data/valid.jsonl", "w").write("\n".join(json.dumps(e) for e in ex[8:]) + "\n")
EOF
mlx_lm.lora --model Qwen/Qwen3.5-2B --train --data lora_data \
  --iters 10 --batch-size 2 --num-layers 8 --adapter-path lora_adapter
```

Note four things:
- Did it finish?
- What does the `Trainable parameters` line say?
- What are the loss values?
- What is the peak memory figure?

Then check that the trained adapter loads:

```bash
mlx_lm.generate --model Qwen/Qwen3.5-2B --adapter-path lora_adapter --max-tokens 30 \
  --chat-template-config '{"enable_thinking": false}' \
  --prompt "Label sentence 99: the drug was well tolerated."
```

## Step 4: llama.cpp with JSON-only output

In **terminal 1** (the first run downloads about 2.5 GB, then leave it running):

```bash
llama-server -hf unsloth/Qwen3.5-2B-GGUF:Q8_0 --jinja --port 8080 -c 8192
```

In **terminal 2**:

```bash
curl -s localhost:8080/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "messages": [{"role": "user", "content": "Sentence: \"Osimertinib significantly improved progression-free survival.\" Give the aspect and polarity."}],
  "chat_template_kwargs": {"enable_thinking": false},
  "response_format": {"type": "json_schema", "json_schema": {"name": "label", "schema": {
    "type": "object",
    "properties": {"aspect": {"type": "string", "enum": ["efficacy", "safety", "none"]},
                   "polarity": {"type": "integer", "enum": [-2, -1, 0, 1, 2]}},
    "required": ["aspect", "polarity"]}}},
  "max_tokens": 60}' | python3 -m json.tool
```

Note two things:
- The `content` text. Is it valid JSON with only `aspect` and `polarity`?
- The `timings` block (`prompt_per_second`, `predicted_per_second`).

Stop the server with Ctrl-C when done.

## Step 5: only if step 2, 3 or 4 failed

Repeat the failed step with the fallback model:
- **MLX:** `Qwen/Qwen2.5-3B-Instruct`. Drop the `--chat-template-config` flag; this model has no thinking mode.
- **llama.cpp:** `bartowski/Qwen2.5-3B-Instruct-GGUF:Q8_0`. Drop the `chat_template_kwargs` line.

## Two questions

1. Can the Mac stay plugged in and awake tonight for a long job (a fine-tune, then labeling about 2,000 short documents, several hours)? While it runs, `caffeinate -dims` in a terminal keeps it awake.
2. Is anything else going to need the Mac today, and when?

---

## Results (fill in and send back, or paste the raw output)

| Step | Worked? | Numbers / notes / error |
|---|---|---|
| 0. Machine | | chip, RAM, free disk, macOS, arm64? |
| 1. Versions | | mlx-lm version, llama.cpp version |
| 2. MLX short prompt | | `<think>` present? prompt tok/s, generation tok/s |
| 2. MLX long prompt | | prompt tok/s, generation tok/s |
| 3. Fine-tune | | trainable params, loss values, peak memory |
| 3. Adapter loads | | |
| 4. llama.cpp JSON | | valid JSON? prompt_per_second, predicted_per_second |
| 5. Fallback (if used) | | which model, what worked |
| Overnight OK? | | |
