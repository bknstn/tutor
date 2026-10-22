# 001 — Native plugin and deterministic storage

Date: 2026-09-26

Status: Accepted; review delivery refined by [008](008-bounded-review-panels.md).

## Context

Vocabulary capture needs generated explanations, durable cards, and predictable
review scheduling. Reimplementing the agent framework would add unnecessary
maintenance, while model-managed state would make saves and review dates
difficult to verify.

## Decision

Implement Tutor as a native Hermes plugin with a narrow `tutor_vocabulary` tool
and native Telegram handlers. Use SQLite for cards and review state. Restrict
the installation to one owner in a private chat. Let the model generate content,
but let Python validate and persist it, authorize callbacks, and schedule fixed
1-, 3-, or 7-day intervals.

## Consequences

The plugin requires no framework fork. Storage results are the source of truth
for save confirmations, and reviews do not need model calls. SQLite persistence
and callback tests are required. The initial individual-card review interface
is superseded by the bounded panel design in record 008.
