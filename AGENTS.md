# Tutor development

This repository implements a native Hermes vocabulary plugin. Hermes runs
only on the VPS. Read README.md for paths and operational commands.

- Each agent has its own upstream checkout and venv under /home/hermes/runtimes.
  Do not modify or restart Buddy while doing routine Tutor work. A user-authorized
  cross-instance migration is an explicit exception.
- Keep tutor data, sessions, bot token and schedules separate from AI Buddy.
- Secrets and real vocabulary databases stay on the VPS, outside this repository.
- Use `ssh hermes-vps` for routine operations; root is unnecessary.
- Production source stays on main, matching published origin/main.
- Keep the scope to English vocabulary capture and deterministic review.
- Validate storage and callbacks with tests; use the tutor Hermes venv for
  Telegram integration tests and the Hermes plugin validator.
- Never claim a word was saved without a successful storage result.
