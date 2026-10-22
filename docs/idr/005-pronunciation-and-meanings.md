# 005 — IPA and structured meanings

Date: 2026-10-01

Status: Accepted; sense selection refined by [006](006-distinct-senses.md).

## Context

A single definition does not cover words with distinct senses, and text-only
definitions do not show pronunciation. Existing cards and review progress must
remain usable when richer content is introduced.

## Decision

Store British IPA pronunciation and one to three structured meanings, each
containing an English definition, Russian translation, and English example.
Label pronunciation variants when they depend on sense or part of speech.
Validate content sizes for Telegram display. Migrate legacy cards and support
enrichment on resubmission without resetting IDs or review history.

## Consequences

The tool schema, persona, storage, and card renderer share the richer format.
Legacy cards remain readable before enrichment. IPA is a textual transcription;
this change does not introduce audio generation.
