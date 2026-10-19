# Serve the fine-tuned model with vLLM on Runpod

distil returns a **LoRA adapter** (not merged weights). vLLM loads the base model from Hugging Face and
applies the adapter. Source: distil-cli-skill `references/deployment.md`. **Starting a pod costs money; do it on the day.**

## 1. Get the artifacts (needs `distil auth`)
```bash
distil slm download --destination model <slm-id>      # model.tar + config.yaml
tar -xf model/model.tar -C model                      # -> model/model-adapter/
grep -E 'student_model_name|lora_r' model/config.yaml  # base model + rank
```

## 2. Start a pod (Runpod console, or the runpod MCP/plugin)
- GPU: any 24 GB card is plenty for a 1-4B student (e.g. RTX 4090 / L4 / A5000).
- Template: Runpod's official vLLM or PyTorch template; expose HTTP port **8000**; container disk >= 30 GB.
- Env on the pod: `HF_TOKEN` (needed for gated bases like Llama/Gemma; Qwen is not gated).
- Upload the adapter: `runpodctl send model/model-adapter` (or scp).

## 3. Serve (inside the pod)
Replace `Qwen/Qwen3-1.7B` with the base from `config.yaml`, and `--max-lora-rank` with `lora_r` (default 64).
```bash
pip install -U vllm
vllm serve Qwen/Qwen3-1.7B \
  --served-model-name base \
  --enable-lora --lora-modules model=./model-adapter --max-lora-rank 64 \
  --api-key "$VLLM_API_KEY" \
  --enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3   # Qwen3 family flags
```
Request the adapter by name **`model`** (not `base`).

## 4. Point the repo at it (`.env`, names only here)
| Variable | Value |
|---|---|
| `STUDENT_BASE_URL` | `https://<pod-id>-8000.proxy.runpod.net/v1` |
| `STUDENT_MODEL` | `model` |
| `STUDENT_API_KEY` | the `VLLM_API_KEY` you set |
| `STUDENT_VERSION` | e.g. `v1` (shows up as a Langfuse tag/metadata) |

## 5. Smoke test, then evaluate
```bash
uv run python -m pii.student_client --n 5      # traced with tag student
make eval SYSTEM=student
```
The system prompt sent must equal the job's `task_description` (it is `pii.schema.SYSTEM_PROMPT`). If quality looks
worse than distil's reported metrics, check the prompt first, then that the request names `model`.
Stop or terminate the pod when finished.
