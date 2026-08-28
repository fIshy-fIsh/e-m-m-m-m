# Phase 13A Step 2H — SteamApis WebSocket Client Plan

1. Record the current official SteamApis WebSocket endpoint, authentication, permission, compression, connection-limit, subscription, message, marketplace, and game contracts.
2. Add one bounded `websockets` runtime dependency using the repository's existing dependency style.
3. Implement a secret-redacted, single-session client that sends one fixed Buff163/CS2 subscription and delegates every text frame to the existing Step 2A parser.
4. Add offline connector tests for security, subscription, parser integration, closure, cancellation, and architecture boundaries.
5. Update the README and SteamApis notes with the transport contract, parser limitation, exclusions, and unchanged SteamDT currency blocker.
6. Run focused and full tests, Ruff, Mypy, three established dry-runs, whitespace checks, and exact-scope/security audits.
7. Leave the work unstaged, uncommitted, and unpushed; stop before Step 2I and do not resume Step 2G.
