# Security and privacy

## Private configuration and data

Each installation needs its own Telegram bot token, numeric owner ID, model
credentials, Hermes home, and vocabulary database. Keep these outside the Git
checkout. The blank [.env.example](.env.example) contains variable names only.

Do not commit or attach filled environment files, model authentication files,
session transcripts, real vocabulary databases, logs, or backups. Review terminal
output and screenshots before sharing them: they can contain chat identifiers,
vocabulary, usernames, file paths, or credentials. Commit author names and email
addresses are also public Git metadata; configure a public identity and a GitHub
noreply email before contributing if you want to keep your personal email private.

The supplied installer restricts the Tutor home to mode `0700`, its environment
file to `0600`, and service-created files through `UMask=0077`. A separate runtime
and home keep instances operationally independent. Instances running as the
same Linux user do not have a filesystem security boundary between them.

## Access and external services

Tutor is designed for one owner's private Telegram chat. The installer configures
the Hermes allowlist, and review handlers verify the owner, private chat,
message binding, and callback state before changing progress. Do not enable
unrestricted gateway access for a public deployment.

SQLite data is local to the host, but Tutor is not an offline application.
Telegram processes bot messages, and the configured model provider receives the
content Hermes sends for card generation. Configure and assess those services
for your own installation. Review scheduling and grading do not require model
calls.

## Reporting a problem

For reproducible bugs, open an issue with synthetic examples and redacted
diagnostics. Do not publish live tokens, personal data, database copies, or
exploit details in issues or pull requests. For a sensitive vulnerability, use
[GitHub's private vulnerability reporting](https://github.com/bknstn/tutor/security/advisories/new),
which is enabled for this repository.

If a credential is exposed, revoke or rotate it first. Removing it from the
latest file does not remove it from Git history, pull requests, cached pages,
existing clones, or forks. Coordinate any history rewrite with repository
maintainers before changing published commits.
