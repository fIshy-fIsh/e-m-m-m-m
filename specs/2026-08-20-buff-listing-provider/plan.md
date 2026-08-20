# Phase 13C — Plan

1. Freeze the provider DTO, anonymous client, strict all-item parser, ownership, error, smoke, scope, and exactly-one-commit contracts.
2. Extract the empirically validated anonymous GET into one borrowed-client implementation with no retry, pagination, auth, Cookie, proxy, or fallback.
3. Add an immutable `BuffListing`, an atomic strict response parser, and a borrowed-client provider keyed by explicit goods ID.
4. Extract one shared owned HTTPX smoke runtime and refactor the historical schema smoke to use the provider.
5. Add an independently gated provider smoke that performs one provider call and prints only aggregate/presence flags.
6. Add synthetic fixtures and offline client/provider/smoke tests; preserve SteamDT, SteamApis, Phase 12, solver, valuation, and pipeline behavior.
7. Run all focused/full validation, stage once, create one commit named `add buff listing provider abstraction`, verify a clean tree, and do not push or run a live smoke.
