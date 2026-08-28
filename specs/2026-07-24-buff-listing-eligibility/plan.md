# Phase 12E2B — BUFF Listing Eligibility Filter Core Plan

1. Define an isolated immutable eligibility contract for explicit classification facts, policy, stable reason codes, decisions, and safe validation errors.
2. Revalidate and defensively copy all public inputs while preserving candidate values and deriving `is_eligible` only from the canonical reason tuple.
3. Evaluate all six listing-level rules in deterministic order without short-circuiting or invoking downstream services.
4. Add focused tests for type boundaries, individual and combined rules, decision invariants, redaction, tamper defense, and architecture isolation.
5. Document the distinction between format-valid candidates and solver-entry eligibility, including defaults and current integration exclusions.
6. Run the complete offline validation matrix and audit the exact seven-file scope without staging, committing, pushing, or starting another phase.
