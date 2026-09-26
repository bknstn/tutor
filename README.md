# Hermes Tutor MVP

Personal English vocabulary tutor: [@buddytutor_bot](https://t.me/buddytutor_bot).
Send a word or phrase, receive an English definition, Russian translation and
one example, then review it. A native plugin for the existing upstream Hermes
codebase, with no framework modifications.

## Usage

Open the bot and press **Start**. Send `convoluted`, `rule out`, or `take for
granted`. Duplicate terms (case, whitespace and Unicode normalized) return
`Already saved.` New cards become due after 24 hours.

At 19:00 Europe/Warsaw, up to five due cards arrive. Recall the meaning, press
**Показать ответ**, then **Again**, **Good**, or **Easy**. Python schedules the
next review 1, 3, or 7 days later. `/review` requests a batch on demand.
Repeated clicks count only once; superseded buttons cannot update a newer
review. Unanswered cards remain due and may be offered the next day.
The daily job stays silent when nothing is due.

## VPS layout

Connect using `ssh hermes-vps` as the existing unprivileged `hermes` user.

| Purpose | Path / service |
| --- | --- |
| Shared framework and Python | `/home/hermes/.hermes/hermes-agent` |
| Tutor source on main | `/home/hermes/workspace/tutor` |
| Tutor home alias | `/home/hermes/.hermes-tutor` |
| Actual native profile | `/home/hermes/.hermes/profiles/tutor` |
| Tutor workspace | `/home/hermes/workspace/tutor-workspace` |
| Private bot configuration | `/home/hermes/.hermes-tutor/.env` (0600) |
| Vocabulary DB | `/home/hermes/.hermes-tutor/plugin-data/hermes-tutor/data.db` |
| Gateway | `hermes-tutor.service` |
| Daily reviews | `hermes-tutor-review.timer` / `.service` |

The tutor has its own token, data, sessions, persona, service and timer. It uses
the existing model configuration and Hermes's supported global OAuth fallback;
refresh tokens are not copied. Only the configured owner's private Telegram
chat is allowed. This is process/data isolation under the same Linux user,
not a security boundary against the main Hermes account.

## Deployment

Publish reviewed changes to GitHub main first. VPS production source must
remain on main, with HEAD equal to origin/main.

```sh
cd /home/hermes/workspace/tutor
git pull --ff-only origin main
test "$(git branch --show-current)" = main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
PY=/home/hermes/.hermes/hermes-agent/venv/bin/python
$PY -m unittest discover -s tests -v
$PY deploy/prepare.py
$PY deploy/check_ready.py
systemctl --user daemon-reload
systemctl --user enable --now hermes-tutor.service
systemctl --user enable --now hermes-tutor-review.timer
```

`prepare.py` creates the profile, persona, allowlist, plugin symlink and units;
it does not start services. It preserves existing config and custom persona.
Set a separate TELEGRAM_BOT_TOKEN in the tutor .env before activation. Never
reuse the main bot token. The readiness check only calls getMe/getWebhookInfo.
The user must press Start before Telegram allows daily messages.
After source updates, restart only the tutor service. Preserve separate
gateways during framework updates; avoid automatic profile multiplex migration.

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
standard library; two Telegram tests require the shared Hermes venv and skip
otherwise. Tests cover concurrent duplicates, due selection, intervals,
persistence, unauthorized/replayed/stale buttons and delivery retries.
The plugin validator passes on Hermes v0.21.3, commit 345cd2b057.

Delivery is not exactly-once: ambiguous network timeouts may leave an orphan
message with inactive buttons before a retry sends a replacement. Reservations
suppress repeated sends for 20 hours; a crash after reserving may defer a card
until the next day. This is a single-owner MVP: no web UI, courses, accounts,
audio or analytics service.
