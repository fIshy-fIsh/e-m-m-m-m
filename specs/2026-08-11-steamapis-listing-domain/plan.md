# Phase 13A Step 2A — SteamApis Offer Domain + Strict Parser Plan

1. Freeze the documented SteamApis message, offer, timestamp, source-filter, and project-owned identity contract before application code.
2. Add one standard-library-only `steamapis_listing.py` module with immutable repr-hidden public models, strict invariants, an opaque SHA-256 source identity helper, and a duplicate-key-rejecting JSON parser.
3. Distinguish `SUBSCRIBED`, `OFFER`, `IGNORED`, and `ERROR` outcomes without retaining raw payloads or server error text; fail closed with fixed redacted typed errors for malformed supported messages.
4. Add focused synthetic tests for valid Added/Updated offers, stable identity, exact Decimal and UTC handling, explicit ignored outcomes, malformed data, duplicate keys, redaction, and no-network/no-import boundaries.
5. Document the official URLs and user-confirmed contract, the blocked re-verification attempt, undocumented identifiers/removal behavior, internal digest semantics, and the absence of any client or runtime integration.
6. Run focused and full quality checks, all three existing offline dry-runs, whitespace/scope audits, and leave the seven approved paths uncommitted and unpushed.
