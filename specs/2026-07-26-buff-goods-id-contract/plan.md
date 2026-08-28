# Phase 12E4B0 — Authoritative BUFF goods_id Contract Propagation

1. Extend the existing BUFF observation and normalized-candidate models with optional, validated `goods_id` provenance and preserve it through normalization.
2. Add strict listing-fixture schema v2 with required `goods_id` while retaining unchanged schema-v1 parsing as `goods_id=None`.
3. Preserve `goods_id` through eligibility and qualification defensive snapshots without changing facts identity, policy, reasons, or statuses.
4. Add project-owned synthetic v2 listing fixtures and make the manual offline qualification command use v2 listings by default while retaining v1 compatibility.
5. Update existing focused tests for domain validation, parser versioning, snapshot propagation, facts identity independence, integration behavior, and output confidentiality.
6. Document the compatibility and provenance boundary without claiming a live BUFF mapping or production readiness.
7. Run all requested focused/full tests, static checks, dry-runs, manual entrypoints, and exact scope/security audits; do not commit or push.
