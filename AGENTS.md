# Tutor development

This repository implements a native Hermes vocabulary plugin. Hermes runs
only on the VPS. Read README.md for paths and operational commands.

- Do not modify the shared upstream Hermes checkout or restart the main gateway.
- Keep tutor data, sessions, bot token and schedules separate from AI Buddy.
- Secrets and real vocabulary databases stay on the VPS, outside this repository.
- Use `ssh hermes-vps` for routine operations; root is unnecessary.
- Production source stays on main, matching published origin/main.
- Keep the scope to English vocabulary capture and deterministic review.
- Validate storage and callbacks with tests; use the shared Hermes venv for
  Telegram integration tests and the Hermes plugin validator.
- Never claim a word was saved without a successful storage result.
