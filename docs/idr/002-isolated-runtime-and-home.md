# 002 — Independent runtime and home

Date: 2026-09-26

Status: Accepted.

## Context

A profile sharing another agent's runtime and default configuration creates
coupling during startup, authentication refresh, upgrades, and recovery.
Routine Tutor changes should not affect another agent.

## Decision

Give Tutor a separate framework checkout, virtual environment, real Hermes home,
workspace, model authentication, Telegram bot token, database, gateway, and
review timer. Use a scoped CLI wrapper and native service alias. Disable
automatic profile multiplex migration and preserve existing Tutor
configuration during installation.

## Consequences

Tutor can be updated and rolled back independently. Operations must explicitly
target its own runtime and home. Keeping instances under the same Linux user
provides operational separation rather than a filesystem security boundary.
Host addresses, credentials, and other agents' private layouts are not part of
the repository documentation.
