# Implementation decision records (IDR)

These records capture implementation and architecture decisions separately from
the project README. Dates follow when the changes were applied or documented
in repository history. The initial records were reconstructed from that
history; they are not a transcript of private deployment activity.

| ID | Date | Decision |
| --- | --- | --- |
| [001](001-native-plugin-and-storage.md) | 2026-09-26 | Native plugin, local persistence, and deterministic reviews |
| [002](002-isolated-runtime-and-home.md) | 2026-09-26 | Independent Tutor runtime and home |
| [003](003-systemd-drop-in.md) | 2026-09-26 | Preserve service settings with a systemd drop-in |
| [004](004-private-model-configuration.md) | 2026-09-27 | Document model configuration separately from plugin behavior |
| [005](005-pronunciation-and-meanings.md) | 2026-10-01 | IPA and structured meanings with compatible data migration |
| [006](006-distinct-senses.md) | 2026-10-03 | Merge duplicate senses before saving and rendering |
| [007](007-daily-conversation-sessions.md) | 2026-10-18 | Fresh conversation context each local calendar day |
| [008](008-bounded-review-panels.md) | 2026-10-18 | Bounded single-message reviews with explicit continuation |

Add the next zero-padded number for a new decision. Include the application
date, status, context, decision, and consequences. Preserve historical context
when a later record supersedes a decision, and link the newer record. Never
include credentials, personal deployment identifiers, or real user data.
