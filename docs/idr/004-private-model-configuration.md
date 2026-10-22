# 004 — Private model configuration

Date documented: 2026-09-27

Status: Accepted. Public documentation revised on 2026-10-22.

## Context

On 2026-09-27, the README began recording the model and reasoning settings of a
running installation. The installer already kept those settings in private
configuration and preserved them on upgrades. Such snapshots can become stale
and are not requirements of the plugin.

## Decision

Keep model selection, reasoning settings, and authentication in the
installation's private Hermes configuration. The installer supplies defaults
only when configuration is missing and preserves an existing configuration.
The 2026-10-22 documentation revision replaces live configuration snapshots
with setup instructions explaining this boundary, without publishing an
instance's subscription or authentication details.

## Consequences

Operators can choose a model supported by their runtime without changing
storage or review logic. Generated card quality depends on that model. A model
change does not alter deterministic review intervals, and private configuration
must not be committed to document an upgrade.
