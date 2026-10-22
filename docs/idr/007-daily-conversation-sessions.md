# 007 — Daily conversation sessions

Date: 2026-10-18

Status: Accepted.

## Context

Long-lived conversations can accumulate stale context. Restarting the gateway
every night would disrupt active work and couple conversation management to
service operations.

## Decision

Use the native `pre_gateway_dispatch` hook to reset conversation context on the
owner's first ordinary message of a new Europe/Warsaw calendar day. Finish an
active turn first; reset on the next idle message. Commands and review buttons
do not trigger the reset. Clear cached conversation state before publishing
the new session, and skip dispatch if reset fails.

## Consequences

Same-day context and manual `/new` or `/reset` behavior remain available.
Vocabulary and review state survive because they live outside conversation
history. No nightly restart is needed. The hook relies on internal Hermes
gateway methods, which require integration checks during framework upgrades.
