# Phase 13D-0 — Plan

1. Freeze the audit conclusion that no verified live `market_hash_name ↔ goods_id` mapping exists.
2. Add one immutable canonical resolved-identity DTO and one asynchronous resolver protocol with `None` as the normal unresolved result.
3. Add contract-only offline tests using synthetic scalar values and no mapping fixture or concrete resolver.
4. Document that the current anonymous listing provider consumes a pre-known goods ID and cannot resolve market names.
5. Run focused/full offline validation and audit exactly seven unstaged paths; do not wire, commit, push, or perform live I/O.
