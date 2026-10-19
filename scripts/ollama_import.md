# Run the distil-trained model in Ollama (local)

**Heads-up:** distil's supported serving path is vLLM, and it delivers a **LoRA adapter** (`model-adapter/`), not a GGUF
(distil-cli-skill `references/deployment.md`). This is an unofficial route: merge the adapter into the base model,
convert to GGUF, import. Check the result against distil's reported metrics with `make eval SYSTEM=student`.

## 1. Download the artifacts (needs `distil auth`)
```bash
distil slm download --destination model <slm-id>
tar -xf model/model.tar -C model            # -> model/model-adapter/
grep student_model_name model/config.yaml   # e.g. Qwen3-1.7B  -> HF base Qwen/Qwen3-1.7B
```

## 2. Merge adapter into the base (Python, once)
```bash
uv run --with peft --with transformers --with torch python - <<'PY'
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
base = "Qwen/Qwen3-1.7B"   # from config.yaml
m = PeftModel.from_pretrained(AutoModelForCausalLM.from_pretrained(base), "model/model-adapter").merge_and_unload()
m.save_pretrained("model/merged"); AutoTokenizer.from_pretrained(base).save_pretrained("model/merged")
PY
```

## 3. Convert to GGUF with llama.cpp
```bash
git clone https://github.com/ggml-org/llama.cpp && pip install -r llama.cpp/requirements.txt
python llama.cpp/convert_hf_to_gguf.py model/merged --outfile model/pii-student-f16.gguf --outtype f16
# optional (needs a llama.cpp build): llama-quantize model/pii-student-f16.gguf model/pii-student.gguf Q4_K_M
```

## 4. Modelfile + import
`Modelfile`:
```dockerfile
FROM ./model/pii-student-f16.gguf
PARAMETER temperature 0
PARAMETER num_ctx 4096
```
```bash
ollama create pii-student -f Modelfile
ollama run pii-student "Anna Berg, IBAN DE89 3704 0044 0532 0130 00"   # sanity check
```
If it ignores the chat format, copy the `TEMPLATE` block from `ollama show --modelfile qwen3:1.7b` into the Modelfile.
(Alternative: `FROM ./model/merged` imports the safetensors directly, per docs.ollama.com/import.)

## 5. Point the repo at it (`.env`)
```
STUDENT_PROVIDER=ollama
STUDENT_MODEL=pii-student
STUDENT_VERSION=v1
```
```bash
uv run python -m pii.student_client --n 20 && make eval SYSTEM=student
```
The request must carry the job's `task_description` as system prompt; `pii.schema.SYSTEM_PROMPT` is exactly that.
