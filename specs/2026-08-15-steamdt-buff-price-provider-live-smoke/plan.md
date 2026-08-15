# Phase 13A Step 2M-A4 — Plan

1. Freeze the dedicated provider-smoke environment, output, request-count, lifecycle, and failure contracts before production implementation.
2. Add one standalone script that owns a one-attempt SteamDT HTTP runtime, constructs the real `SteamDTBuffPriceProvider`, and calls `get_price()` once for one inherited market name.
3. Add offline guard, fake-client, local-transport, redaction, process-control, lifecycle, and architecture tests without replacing the real aggregate/provider/policy path.
4. Add the disabled gate to `.env.example` and document the exact BUFF gross-sell path and limitations in the SteamDT notes.
5. Run focused and full offline validation, record observed results, and audit the exact seven-path scope and empty index.
6. Report inherited gate/key/name presence without values; do not execute the real smoke, commit, push, or begin Step 2M-A5.
