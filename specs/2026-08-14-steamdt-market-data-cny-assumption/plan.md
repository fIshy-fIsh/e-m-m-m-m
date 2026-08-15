# Phase 13A Step 2L-PIVOT-R1 — Plan

1. Record the official SteamDT aggregate-price facts separately from the user-approved project CNY interpretation and retain the aggregate-versus-listing boundary.
2. Add a thin service that calls the existing single-price candidate client once and returns provider-ordered defensive `SteamDTPlatformPrice` snapshots without raw payloads.
3. Add a disabled-by-default live market smoke using the existing gate, key, and single market-name environment variables, one client, `max_retries=0`, and exactly one single-price request.
4. Add offline service, real-parser/client composition, provider-assumption, smoke lifecycle, redaction, and architecture tests.
5. Document SteamDT as the current primary aggregate market-data and valuation source while retaining SteamApis as optional future listing-level infrastructure.
6. Run all focused and full offline validation, then inspect inherited guards and run the live probe at most once only when all three already permit it.
7. Leave all work unstaged and uncommitted and do not start Step 2M.
