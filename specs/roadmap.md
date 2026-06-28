# CS2 BUFF Trade-up Opportunity Scanner — Roadmap

## Phase 1 — Specification and Project Skeleton
### Goal
Define project scope, architecture, domain language, acceptance criteria, and repository foundations required for implementation.

### Scope
- create foundational specs documents
- define mission, stack, roadmap, and implementation specification
- establish repository and planning workflow

### Deliverables
- `specs/mission.md`
- `specs/tech-stack.md`
- `specs/roadmap.md`
- feature-specific planning directory under `specs/YYYY-MM-DD-feature-name/`
- `docs/SPEC.md`

### Acceptance Criteria
- scope and non-goals are documented clearly
- V1 modules and data model are specified enough for implementation
- implementation can proceed without re-deciding core architecture

### Status
- [ ] Not started

---

## Phase 2 — Foundation and Environment
### Goal
Stand up the Python service skeleton and local development environment.

### Scope
- application bootstrap with FastAPI
- settings management
- SQLAlchemy and Alembic setup
- PostgreSQL and Redis wiring
- Docker Compose local environment
- lint, type-check, and test tooling

### Acceptance Criteria
- app boots locally
- database migrations run successfully
- Redis connectivity is available
- lint/type/test baseline passes

### Status
- [ ] Not started

---

## Phase 3 — Market Ingestion
### Goal
Ingest BUFF market listing data for trade-up candidate materials.

### Scope
- BUFF API/client abstraction
- listing fetch workflows
- persistence of goods_id, price, float, and listing metadata
- scan run tracking and deduplication
- retry and rate-limit aware ingestion

### Acceptance Criteria
- scheduled scans persist usable listing snapshots
- duplicate listings are handled predictably
- failures are observable and retried safely

### Status
- [ ] Not started

---

## Phase 4 — CS2 Metadata Enrichment
### Goal
Map ingested market listings onto normalized CS2 metadata needed for trade-up calculations.

### Scope
- collection and rarity mapping
- min_float and max_float normalization
- output pool derivation inputs
- metadata versioning or provenance tracking

### Acceptance Criteria
- each eligible input item can be enriched with metadata required by the engine
- unmatched items are recorded and diagnosable

### Status
- [ ] Not started

---

## Phase 5 — Trade-up Engine
### Goal
Compute trade-up outcomes and economics from normalized inputs.

### Scope
- output pool generation
- output probability calculation
- output float calculation
- EV and ROI calculation
- worst-case loss and profit probability calculation

### Acceptance Criteria
- engine results are reproducible from stored inputs
- test fixtures cover representative trade-up scenarios
- formulas are documented and validated

### Status
- [ ] Not started

---

## Phase 6 — Risk Filtering and Opportunity Selection
### Goal
Filter noisy results and retain only actionable opportunities.

### Scope
- configurable EV thresholds
- ROI thresholds
- downside and spread filters
- liquidity/listing quality heuristics
- duplicate opportunity suppression

### Acceptance Criteria
- low-quality opportunities are filtered according to explicit rules
- candidate opportunities are queryable and explainable

### Status
- [ ] Not started

---

## Phase 7 — Alerting and Operations
### Goal
Run continuous scans and notify selected opportunities to Discord.

### Scope
- APScheduler recurring jobs
- Discord Webhook integration
- alert formatting
- deduplication and cooldown logic
- health checks and operational visibility

### Acceptance Criteria
- scanner runs 24h in unattended mode
- valid opportunities produce Discord alerts
- repeated alerts are suppressed according to policy

### Status
- [ ] Not started

---

## Phase 8 — Hardening and Release
### Goal
Prepare MVP for stable ongoing operation.

### Scope
- integration tests
- failure-mode handling
- deployment checklist
- documentation polish

### Acceptance Criteria
- end-to-end happy path is verified
- major failure modes are handled acceptably
- MVP can be deployed with documented configuration

### Status
- [ ] Not started

---

## V1 Non-Goals (apply across all phases)
- no automatic buying
- no automatic login
- no cookie extraction
- no captcha bypass
- no BUFF risk-control bypass
- no browser-simulated purchasing
- no non-official evasion techniques