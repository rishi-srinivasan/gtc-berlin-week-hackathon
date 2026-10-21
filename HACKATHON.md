# Hackathon history

PII Gateway started at the **GTC Berlin week hackathon**. The first commit is dated **2026-10-19**; the demo report was
finalised on 2026-10-21.

## What was built in the hackathon

- A German PII redaction pipeline: a small model finds PII, code swaps it for placeholders (`[IBAN_1]`), only masked text
  reaches a frontier LLM, and the reply is rehydrated.
- A 22-class PII schema with synthetic "broker-style" German messages and a 300-message test set.
- A teacher baseline (gpt-oss-120b), traced and scored in Langfuse.
- A Qwen3-1.7B student distilled with [distil labs](https://www.distillabs.ai) from 128 synthetic rows.
- A chat UI demo (`make app`) that shows the masked prompt and the rehydrated reply.

## Results

Short version: the fine-tuned 1.7B student matches the 120B teacher on text overlap (Rouge 85.6% vs 86.6%) and beats it on
exact match (39.3% vs 8.3%), at about 70x smaller. An off-the-shelf German PII model leaked PII in 84.7% of messages; the
teacher leaked in 28.3%.

Full tables, per-class recall and caveats: [results/DEMO_REPORT_FINAL.md](results/DEMO_REPORT_FINAL.md).

## Known limits

- Hackathon-scale data (100 seed examples, 128 training rows). Recall on ID card and account numbers is weak.
- Leak rate is not zero. Do not treat the output as a guarantee.
