# Hermes Tutor MVP

Self-hosted English vocabulary tutor for Telegram.
Send a word or phrase, receive its IPA pronunciation and common meanings, each
with an English definition, Russian translation and example, then review it.
Cards start with one common meaning; a second or third is added only for a
different sense or an established domain-specific use. Paraphrases, synonyms,
broader/narrower descriptions, and process/result variants are merged before
saving. Different examples alone do not create another sense. Reimbursement
and curriculum each get one meaning; treat keeps its distinct senses.
Storage also collapses repeated English definitions regardless of case,
spacing, Unicode variants, or punctuation, and returns the stored card for
display. Semantic distinctions are checked by the tutor model, not by text
similarity. IPA uses standard British pronunciation, with labeled
variants where pronunciation differs by sense. A native plugin for the existing
upstream Hermes codebase, with no framework modifications.

## Usage

Open the bot and press **Start**. Send `convoluted`, `rule out`, or `take for
granted`. Duplicate terms (case, whitespace and Unicode normalized) return
the saved card and `Already saved.` New cards become due after 24 hours.
Legacy cards can be enriched on resubmission without resetting review history.

At 19:00 Europe/Warsaw, **one message** offers up to **10 due cards**, one at a
time with a progress counter. Recall the meaning, press **Показать ответ**, then
**Again**, **Good**, or **Easy**; the same message updates to the next card.
Python schedules the next review 1, 3, or 7 days later. After the batch, remaining
words require explicit consent via **Продолжить · до 10 карточек**; **На сегодня
всё** stops. Continuations reuse the same message, and the scheduled job never
automatically drains the backlog. Even 100 due words produce one scheduled
message. Scheduled retries cannot start another batch on the same Warsaw day.
`/review` starts a batch on demand or restores an active panel without sending
another one. All progress and continuation decisions survive gateway restarts.
Repeated clicks count only once; superseded buttons cannot update a newer
review. Unanswered cards remain due and may be offered the next day.
The daily job stays silent when nothing is due.

The first ordinary message on a new calendar day in **Europe/Warsaw** starts a
fresh conversation session. Context is kept throughout the same day; no nightly
service restart or extra reset notification is needed. An active turn is allowed
to finish, and the next idle user message performs the reset. Commands and review
buttons do not trigger it. Vocabulary cards, review buttons and scheduling live
outside conversation history and survive the reset. `/new` and `/reset` still
start a fresh session manually; Hermes auto-compression remains enabled for long
conversations within a day.

## Current model (verified 2026-10-03)

The existing Tutor profile uses `gpt-6-sol` with `agent.reasoning_effort: medium`
through its own `openai-codex` OAuth session (Codex subscription). No OpenAI API
key is configured for Tutor. Model and reasoning settings live in its private
VPS `config.yaml`; the installer preserves existing configuration.

## VPS layout

Connect using `ssh hermes-vps` as the existing unprivileged `hermes` user.

| Purpose | Path / service |
| --- | --- |
| Tutor framework and Python | `/home/hermes/runtimes/hermes-tutor` |
| Buddy framework and Python | `/home/hermes/runtimes/hermes-buddy` |
| Tutor source on main | `/home/hermes/workspace/tutor` |
| Tutor home (real directory) | `/home/hermes/.hermes-tutor` |
| Buddy home (real directory) | `/home/hermes/.hermes-buddy` |
| Tutor workspace | `/home/hermes/workspace/tutor-workspace` |
| Private bot configuration | `/home/hermes/.hermes-tutor/.env` (0600) |
| Vocabulary DB | `/home/hermes/.hermes-tutor/plugin-data/hermes-tutor/data.db` |
| Gateway | `hermes-tutor.service` |
| Daily reviews | `hermes-tutor-review.timer` / `.service` |

The tutor has its own code checkout, Python interpreter, venv, Node dependencies,
OAuth session, bot token, data, persona, gateway and review timer. Its startup
does not read Buddy's configuration or credentials. Both use the same upstream
Hermes release initially, but may be updated and rolled back independently.
Only the configured owner's private Telegram chat is allowed. This is operational
isolation under the same Linux user, not a filesystem security boundary.

Legacy `/home/hermes/.hermes` points only to `.hermes-buddy`, and Buddy's
`hermes-agent` link points to its own runtime. They preserve existing Buddy
integrations and the default `hermes` CLI; the tutor does not use either link.
Buddy's service is `hermes-buddy.service`, with `hermes-gateway.service` as a
compatibility alias. The tutor also has a native hashed gateway service alias
so its scoped Hermes CLI can find the correct service. Use the explicit
`hermes-buddy` and `hermes-tutor` CLI wrappers to avoid targeting the wrong agent.

## Deployment

Publish reviewed changes to GitHub main first. VPS production source must
remain on main, with HEAD equal to origin/main.

```sh
cd /home/hermes/workspace/tutor
git pull --ff-only origin main
test "$(git branch --show-current)" = main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
PY=/home/hermes/runtimes/hermes-tutor/venv/bin/python
$PY -m unittest discover -s tests -v
$PY deploy/prepare.py
$PY deploy/check_ready.py
systemctl --user daemon-reload
systemctl --user enable --now hermes-tutor.service
systemctl --user enable --now hermes-tutor-review.timer
```

`prepare.py` creates the profile, persona, allowlist, plugin symlink and units;
it does not start services. It preserves existing config and custom persona.
For a new install, set TUTOR_OWNER_ID and TELEGRAM_BOT_TOKEN in the tutor .env
before activation and authorize its own model credentials. Never reuse the
Buddy bot token or copy its OAuth refresh token. The readiness check only calls
getMe/getWebhookInfo and does not require Buddy's files. The installer also
creates the scoped CLI wrapper and native systemd alias. Hermes may regenerate
its base unit during startup; `hermes-tutor.service.d/tutor.conf` preserves
the environment file, preflight and private file permissions across that repair.
The user must press Start before Telegram allows daily messages.
After source updates, restart only the tutor service. For framework updates,
operate on the tutor runtime and tutor home explicitly. Preserve separate
gateways and leave automatic profile multiplex migration disabled.

```sh
systemctl --user status hermes-tutor.service --no-pager
systemctl --user list-timers hermes-tutor-review.timer
journalctl --user -u hermes-tutor.service -n 50 --no-pager
# Stop the tutor and reminders, leaving AI Buddy running:
systemctl --user disable --now hermes-tutor-review.timer hermes-tutor.service
```

Back up the tutor home on the VPS, including SQLite, with both tutor services
stopped. Never commit databases, logs, sessions, backups or secrets.

## Validation and MVP limits

Run `python3 -m unittest discover -s tests -v`. The core uses only Python's
standard library; Telegram and native session integration tests require the
tutor Hermes venv and skip otherwise. Tests cover concurrent duplicates, due
selection, intervals, persistence, unauthorized/replayed/stale buttons, delivery
retries, bounded single-message batches with 100 due words, explicit continuation,
Warsaw day boundaries and conversation-cache clearing.
The plugin validator passes on Hermes v0.21.3, commit 345cd2b057.

Delivery is not exactly-once: ambiguous network timeouts may leave an orphan
message with inactive buttons before a retry sends a replacement. Undelivered
failed batches release their reservations; a crash after reserving may defer a
batch until the next day. Panels expire after 20 hours; unfinished cards remain
due. Old individual-card buttons remain supported during the transition.
This is a single-owner MVP: no web UI, courses, accounts,
audio or analytics service.
