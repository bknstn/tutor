# Development and validation

Tutor is a native Hermes plugin; it does not modify the upstream framework.
Keep changes focused on English vocabulary capture and deterministic review.
Use synthetic cards, test chat IDs, and temporary databases for development.

## Code map

| File | Responsibility |
| --- | --- |
| `hermes_tutor/plugin.yaml` | Plugin metadata and declared tools/hooks |
| `hermes_tutor/__init__.py` | Tool registration, card rendering, authorization, Telegram handlers |
| `hermes_tutor/store.py` | SQLite schema, content validation, normalization, review state and scheduling |
| `hermes_tutor/reviews.py` | Review panel rendering and delivery |
| `hermes_tutor/review_job.py` | Timer entry point; no model calls |
| `hermes_tutor/sessions.py` | Daily conversation reset through the native gateway hook |
| `workspace/SOUL.md` | Card-generation and response instructions |

The model chooses distinct senses. Storage deterministically collapses repeated
English definitions after normalization, but does not infer whether paraphrases
are semantically equivalent. Always display the card returned by storage, and
never confirm a save after a failed storage operation.

## Tests

Run the standard-library tests from the repository root:

```sh
python3 -B -m unittest discover -s tests -v
```

Telegram integration tests require the dependencies installed in the dedicated
Tutor Hermes venv. Native session tests also require Hermes imports. Those tests
skip when the relevant dependencies are unavailable, so a local green result
with skips is not a complete integration check.

On a host using the [documented deployment layout](deployment.md), run:

```sh
/home/hermes/runtimes/hermes-tutor/venv/bin/python -B -m unittest discover -s tests -v
/home/hermes/runtimes/hermes-tutor/venv/bin/python -B -m hermes_cli.main plugins validate hermes_tutor
```

Tests cover concurrent duplicate saves, content validation and migration,
fixed review intervals, callback ownership and message binding, stale and
replayed buttons, failed delivery, single-message review batches, explicit
continuation, persistent progress, daily session resets, and timezone boundaries.
Test databases are temporary and cleaned up by the test suite. The Telegram
delivery tests use mocks rather than a live bot token.

The plugin has been validated against Hermes v0.21.3. Re-run the upstream Hermes
plugin validator and the full suite when changing native registration or
gateway integration. The daily session hook uses internal gateway methods, so
framework upgrades need particular care even when storage tests pass.

## Contributing

Explain the user-visible behavior and validation in each pull request. Keep real
configuration, owner IDs, tokens, database files, and logs out of commits and
issue attachments; see [SECURITY.md](../SECURITY.md). Production deployments
follow published `main`; development branches should not be deployed directly.

Keep the README focused on what the project does and how to use it. Put setup
details in [deployment.md](deployment.md), and significant implementation or
architecture decisions in a new numbered [IDR](idr/README.md) with the date the
decision was applied, its context, and its consequences.
