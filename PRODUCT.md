# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack
Single inline HTML page served by a stdlib Python server (src/pii/app.py); no dependencies, no build.

## Users
Hackathon judges watching a live demo on a projector or screen-share. They have seconds to grasp what the product does.

## Product Purpose
German PII redaction gateway for brokerage messages: a small distilled model (student) or a large one (teacher) masks personal data before text reaches a frontier LLM; the reply is rehydrated. Success = a judge sees, instantly, what the LLM sees versus what the user typed.

## Positioning
A small model on the user's side of the wire replaces PII with typed placeholders ([GIVEN_NAME_1], [IBAN_1]) and restores them afterwards.

## Capabilities and Constraints
Backend returns redacted text, frontier reply, rehydrated reply. Student/teacher toggle. German text. Placeholder format [LABEL_n]. No streaming, no history.

## Product Principles
- Before/after redaction is the hero; everything else supports it.
- Show the data boundary: what stays local vs what the LLM sees.
- Demo-legible at projector distance.
