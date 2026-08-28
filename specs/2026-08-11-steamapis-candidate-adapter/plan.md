# Phase 13A Step 2B — Plan

1. **Freeze the adapter contract**
   - Record the exact observation-to-candidate API, source-local identity namespace, field mapping, validation, redaction, and scope boundaries.

2. **Implement the pure adapter**
   - Revalidate one exact `SteamApisListingObservation` through its public constructor.
   - Build one existing `CandidateListing` with explicit project-owned identity, Decimal price, checked legacy float, source timestamp, inspect link, and no raw data.

3. **Lock behavior and isolation with focused tests**
   - Cover successful mapping, deterministic provenance identity, tamper rejection, safe errors, control-flow propagation, and architecture boundaries.

4. **Document the compatibility boundary**
   - Update the SteamApis notes and README without claiming authoritative BUFF identifiers or production readiness.

5. **Validate and audit**
   - Run focused and full tests, Ruff, Mypy, offline dry-runs, whitespace checks, exact-scope review, and safety review.
   - Leave the work uncommitted and unpushed, then stop before Step 2C.
