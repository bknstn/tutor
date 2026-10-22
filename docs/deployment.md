# Deployment and operations

This guide describes the layout implemented by the deployment files. Paths
under `/home/hermes` are deployment conventions, not credentials or the address
of a public server. The scripts currently hard-code these paths: adapt
`deploy/prepare.py`, `deploy/check_ready.py`, and the systemd units together if
you use another account or directory layout.

## Prerequisites

- A Linux host with user systemd services and a dedicated, unprivileged `hermes`
  account. Perform the steps below as that account.
- An independently installed [Hermes Agent](https://github.com/NousResearch/hermes-agent)
  runtime at `/home/hermes/runtimes/hermes-tutor`, with its own `venv` and
  Telegram dependencies. This repository does not install the framework.
- A Telegram bot token and the numeric ID of the one owner allowed to use it.
- Model access configured through that Tutor runtime's Hermes setup flow.
- IANA timezone data including `Europe/Warsaw`.

Use an independent runtime, home, bot token, and model authentication for each
agent. Do not copy another instance's authentication files. For unattended
operation, arrange for the account's systemd user manager to remain available
after logout according to your host's administration policy.

## Layout

| Purpose | Path or service |
| --- | --- |
| Hermes runtime and virtual environment | `/home/hermes/runtimes/hermes-tutor` |
| Plugin source checkout | `/home/hermes/workspace/tutor` |
| Private Hermes home, a real directory | `/home/hermes/.hermes-tutor` |
| Conversation workspace | `/home/hermes/workspace/tutor-workspace` |
| Private environment file | `/home/hermes/.hermes-tutor/.env` |
| Private model and gateway configuration | `/home/hermes/.hermes-tutor/config.yaml` |
| Vocabulary and review database | `/home/hermes/.hermes-tutor/plugin-data/hermes-tutor/data.db` |
| Gateway | `hermes-tutor.service` |
| Daily review job | `hermes-tutor-review.service` |
| Daily timer | `hermes-tutor-review.timer` |

## First installation

Clone the plugin source after installing the dedicated Hermes runtime:

```sh
mkdir -p /home/hermes/workspace
git clone https://github.com/bknstn/tutor.git /home/hermes/workspace/tutor
cd /home/hermes/workspace/tutor
```

Create a private environment file using the blank template. Do this once for a
new installation; do not overwrite an existing environment file on upgrades.
The Tutor home must be a real directory rather than a symlink to a shared
profile.

```sh
install -d -m 700 /home/hermes/.hermes-tutor
install -m 600 .env.example /home/hermes/.hermes-tutor/.env
```

Edit that private file on the host and fill in `TUTOR_OWNER_ID` and
`TELEGRAM_BOT_TOKEN`. The owner ID must be numeric. Keep actual values out of
shell command history, issues, and this repository.

Prepare the profile and units using the dedicated runtime:

```sh
TUTOR_PY=/home/hermes/runtimes/hermes-tutor/venv/bin/python
"$TUTOR_PY" -B -m unittest discover -s tests -v
"$TUTOR_PY" deploy/prepare.py
```

The installer creates missing configuration, the allowlist, persona, plugin
symlink, systemd units, and the scoped `~/.local/bin/hermes-tutor` CLI wrapper.
It does not start services. Existing model configuration and a custom persona
are preserved. A missing owner ID causes installation to fail.

Use the scoped wrapper to complete Hermes model setup for this home before
activation. The initial model/provider defaults are in `deploy/prepare.py`;
choose a model available to your installation and keep the resulting
configuration and credentials private. No particular subscription or live
model configuration is required by the plugin itself.

Run preflight and activate the services:

```sh
"$TUTOR_PY" deploy/check_ready.py
systemctl --user daemon-reload
systemctl --user enable --now hermes-tutor.service
systemctl --user enable --now hermes-tutor-review.timer
```

Preflight verifies the bot through Telegram `getMe` and `getWebhookInfo`; it
does not send messages. It rejects an existing webhook because the gateway uses
polling. The owner must open the bot and press **Start** before Telegram permits
scheduled messages. The timer runs at 19:00 Europe/Warsaw and only runs the
review job when the gateway is active.

## Updating the plugin

Publish reviewed source to `main` before updating a running installation. Keep
the production checkout on `main` at the published `origin/main` commit:

```sh
cd /home/hermes/workspace/tutor
git pull --ff-only origin main
test "$(git branch --show-current)" = main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
TUTOR_PY=/home/hermes/runtimes/hermes-tutor/venv/bin/python
"$TUTOR_PY" -B -m unittest discover -s tests -v
"$TUTOR_PY" deploy/prepare.py
"$TUTOR_PY" deploy/check_ready.py
systemctl --user daemon-reload
systemctl --user restart hermes-tutor.service
```

Keep framework upgrades scoped to the Tutor runtime and home. Do not enable
automatic profile multiplex migration or restart other agent services during
routine Tutor updates. Use the explicit `hermes-tutor` wrapper to avoid the
default Hermes CLI targeting another home.

Hermes can regenerate its base gateway unit. The supplied
`hermes-tutor.service.d/tutor.conf` drop-in preserves the environment file,
preflight, and private file permissions across regeneration. The installer
also creates the native gateway service alias expected by the scoped CLI.

## Service management

```sh
systemctl --user status hermes-tutor.service --no-pager
systemctl --user list-timers hermes-tutor-review.timer
journalctl --user -u hermes-tutor.service -n 50 --no-pager

# Stop Tutor and its scheduled reminders.
systemctl --user disable --now hermes-tutor-review.timer hermes-tutor.service
systemctl --user stop hermes-tutor-review.service
```

Treat logs as private and redact them before sharing. A green Telegram preflight
does not verify model access; after activation, send a synthetic test word from
the owner's chat and confirm that its card is saved.

## Backups

Stop the timer, review job, and gateway before making a consistent backup of
the Tutor home, including SQLite. Preserve the private configuration and
authentication files with restricted permissions. Backups belong in private
storage outside the repository. Restore into the same dedicated home, verify
permissions and ownership, and start Tutor again.

## Delivery and recovery

- `/review` restores a delivered active panel from stored progress without
  sending another panel. Failed edits can be retried without grading twice.
- Failed, unbound deliveries release their reservations. An ambiguous Telegram
  timeout can still leave an extra message whose buttons cannot grade cards.
- A crash after reserving a batch can defer its cards until the next day.
  Panels expire after 20 hours and unanswered cards remain due.
- Scheduled retries cannot open a second batch on the same Europe/Warsaw day.
  A larger backlog needs explicit continuation after each batch of up to ten.
- Legacy individual-card callbacks remain supported; current reviews use the
  single-message batch interface.

The review timer and Python date logic both use `Europe/Warsaw`. If you change
the timezone, update `deploy/hermes-tutor-review.timer`,
`hermes_tutor/sessions.py`, and the daily deduplication logic in
`hermes_tutor/store.py` together, then validate the date-boundary tests.
