# Hermes Tutor

A self-hosted English vocabulary tutor for Telegram, built as a native
[Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin.
Send a word or short phrase, save a vocabulary card, and practise it through
short daily reviews. The default persona explains English vocabulary to a
Russian speaker.

This repository contains the plugin, its tutor persona, tests, and Linux
deployment files. Each installation serves **one configured owner in a private
Telegram chat**; it is not a shared public bot service.

## What it does

- Captures words, phrases, phrasal verbs, and idioms in a local SQLite database.
- Adds British IPA pronunciation, a short English definition, a Russian
  translation, and an English example for each meaning.
- Starts with one common meaning and adds up to two more for distinct senses.
- Recognizes duplicate terms after case, whitespace, and Unicode normalization.
- Reviews up to ten due cards in one Telegram message, with explicit consent
  before another batch.
- Keeps vocabulary and review progress across process restarts and conversation
  resets.

The language model generates card content. Python handles validation,
persistence, review buttons, and scheduling. A card is confirmed as saved only
when storage succeeds.

## Example

Send `rule out` to your own Tutor bot:

```text
rule out
IPA: /ruːl aʊt/

Meaning: exclude a possibility
RU: исключать возможность
Example: We cannot rule out rain.

Saved.
```

This is an illustrative card; model wording can vary. Sending the same term
again returns the stored card with `Already saved.`

## Daily use

1. Open your configured Telegram bot and press **Start**.
2. Send an English word or short phrase, such as `convoluted`, `rule out`, or
   `take for granted`.
3. New cards become due after 24 hours. The supplied timer offers a review at
   **19:00 Europe/Warsaw**, and stays silent when nothing is due.
4. Recall the meaning, press **Показать ответ** (show answer), then rate it:

   | Button | Next review |
   | --- | --- |
   | Again | In 1 day |
   | Good | In 3 days |
   | Easy | In 7 days |

5. After up to ten cards, choose **Продолжить** (continue) for another batch or
   **На сегодня всё** (stop for today).

Use `/review` to start a review on demand or restore an active panel. Repeated
button presses do not grade a card twice. Unanswered cards remain due.

Conversation context starts afresh on the first ordinary message of each
Europe/Warsaw calendar day. `/new` and `/reset` also start a fresh conversation.
Vocabulary cards and review schedules are stored separately and survive these
resets.

## Try the storage and tests locally

The storage layer and core tests use Python's standard library. Use Python
3.11 or newer with IANA timezone data available:

```sh
git clone https://github.com/bknstn/tutor.git
cd tutor
python3 -B -m unittest discover -s tests -v
```

Tests that need Telegram or native Hermes session APIs skip when those
dependencies are unavailable. For the complete suite, use a dedicated Hermes
runtime; see [development and validation](docs/development.md).

Running the bot also requires Hermes Agent, its Telegram dependencies, a bot
token, your numeric Telegram user ID, and model access configured in Hermes.
There is no standalone bot executable in this repository.

## Run your own Tutor

Follow the [deployment guide](docs/deployment.md) for prerequisites, private
configuration, installation, service management, and backups. The supplied
deployment scripts target a Linux host with user systemd services and a
dedicated `hermes` account. Their paths must be adapted for other layouts.

Use [.env.example](.env.example) as a blank configuration template. Keep actual
credentials, user IDs, model configuration, sessions, and vocabulary databases
outside the checkout. See [security and privacy](SECURITY.md) before sharing
configuration or diagnostics.

## Repository guide

| Path | Purpose |
| --- | --- |
| [`hermes_tutor/`](hermes_tutor/) | Native plugin, SQLite storage, review delivery, and daily session hook |
| [`workspace/SOUL.md`](workspace/SOUL.md) | Tutor persona and card-generation rules |
| [`deploy/`](deploy/) | Installer, readiness check, and systemd units |
| [`tests/`](tests/) | Storage, callback, delivery, and session tests |
| [`docs/deployment.md`](docs/deployment.md) | Installation and operations |
| [`docs/development.md`](docs/development.md) | Development, validation, and contribution guidance |
| [`docs/idr/`](docs/idr/) | Numbered implementation and architecture decisions in chronological order |

## Scope and limitations

Tutor focuses on vocabulary capture and deterministic review. It has no web UI,
multi-user accounts, courses, audio generation, or analytics service. Card
quality depends on the configured model; pronunciation is IPA text rather than
audio. Review intervals are fixed, not an adaptive learning algorithm.

The default interface and translations are Russian. The daily timezone is
configured in both the timer and Python logic; changing only the timer does not
change session boundaries or daily review deduplication.

Telegram delivery is not exactly once: an ambiguous network timeout can leave
an extra message with inactive buttons. Review panels expire after 20 hours;
unfinished cards remain due. See the [deployment guide](docs/deployment.md#delivery-and-recovery)
for recovery details.
