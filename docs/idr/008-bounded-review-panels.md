# 008 — Bounded reviews in one Telegram message

Date: 2026-10-18

Status: Accepted; supersedes the initial individual-card delivery interface.

## Context

A large due backlog should not flood a chat or require reviewing everything at
once. Progress and consent must survive restarts, retries, and repeated clicks.

## Decision

Offer up to ten due cards through one editable Telegram message. Track batch
progress and callback revisions in SQLite. Require explicit continuation for
another batch and provide a stop action. Deduplicate scheduled batches by the
Europe/Warsaw date. Bind callbacks to the owner, message, token, and revision;
make repeat grading ineffective. `/review` restores a delivered active panel.

## Consequences

Even a large backlog produces one scheduled panel. Continuations reuse that
message, and unfinished cards remain due. State survives restarts. Failed
unbound deliveries release reservations, but ambiguous network timeouts can
leave an extra message with inactive buttons. Panels expire after 20 hours;
delivery is not exactly once. Legacy individual-card callbacks remain supported.
