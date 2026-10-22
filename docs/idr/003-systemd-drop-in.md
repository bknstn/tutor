# 003 — Persistent systemd service settings

Date: 2026-09-26

Status: Accepted.

## Context

Hermes can repair or regenerate the base gateway service unit. Tutor-specific
settings placed only in that unit can disappear during this process.

## Decision

Install `hermes-tutor.service.d/tutor.conf` alongside the base unit. Keep the
private environment file, readiness preflight, and restrictive umask in the
drop-in. Clear the inherited `ExecStartPre` list before setting Tutor's check.

## Consequences

Upstream unit regeneration preserves the Tutor overrides. The installer must
copy the drop-in, and operators must reload user systemd units after updates.
Configuration remains outside the source checkout.
