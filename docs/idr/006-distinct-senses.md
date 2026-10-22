# 006 — Distinct senses and duplicate definitions

Date: 2026-10-03

Status: Accepted.

## Context

Allowing several meanings encouraged redundant paraphrases, process/result
variants, and examples presented as separate senses. Text similarity alone
cannot reliably decide whether two meanings are semantically distinct.

## Decision

Start with one common meaning. Let the tutor model add another only for a
different sense or an established domain-specific use, merging paraphrases
before saving. In storage, deterministically collapse repeated English
definitions after case, whitespace, Unicode, and punctuation normalization.
Display only the stored card returned by the tool.

## Consequences

Cards remain concise without imposing a two-meaning quota. Distinct senses can
share a Russian translation and still be retained. Semantic quality remains a
model responsibility; storage enforces exact normalized definition uniqueness
rather than approximate semantic matching.
