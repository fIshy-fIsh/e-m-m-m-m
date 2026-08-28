# AI Context Documentation System — Entry Point

This directory is the persistent, cross-tool project context for this repository. It is written for AI assistants (Claude Code, ChatGPT, Cursor, VS Code agents, Copilot, etc.), not as a human-facing README.

## Required reading order (every new AI session)

1. [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) — goals, strategy, stack, working rules, prohibitions.
2. [ARCHITECTURE_STATE.md](ARCHITECTURE_STATE.md) — real current module structure and data flow.
3. [DECISION_LOG.md](DECISION_LOG.md) — all major technical decisions and rejected alternatives.
4. [DEVELOPMENT_HANDOFF.md](DEVELOPMENT_HANDOFF.md) — current git state, completed milestones, next actions.

## Rules

- Read all four files **before** proposing any code change.
- The docs are authoritative only as a summary. When they disagree with the code, the code wins; report the drift rather than trusting a stale doc.
- Do not delete historical decisions or failed investigations — append and correct.
- After every significant completed phase, update `DEVELOPMENT_HANDOFF.md` and append to `DECISION_LOG.md`; keep the others current.
- Do not rely on chat history; rely on these files.
