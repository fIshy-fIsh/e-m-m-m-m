# CS2 BUFF Trade-up Opportunity Scanner — Tech Stack

## Runtime and Language
- **Python 3.12**
  - Primary implementation language for backend services, domain engine, schedulers, and integrations.

## Application Layer
- **FastAPI**
  - Exposes internal/admin APIs for health checks, run inspection, opportunity querying, and operational controls.
- **Pydantic**
  - Validates API payloads, settings, external responses, and domain DTOs.

## Data Layer
- **PostgreSQL**
  - System of record for listings, item metadata mappings, scan runs, computed opportunities, alerts, and audit trails.
- **SQLAlchemy 2.0**
  - ORM and query layer for relational domain modeling and persistence.
- **Alembic**
  - Database schema migration management.
- **Redis**
  - Short-lived caching, duplicate-alert suppression, rate-limit coordination, and lightweight run-state locks.

## Integration Layer
- **httpx**
  - HTTP client for BUFF data retrieval, Discord webhook delivery, and any external metadata endpoints.

## Scheduling
- **APScheduler**
  - Runs periodic scan, enrich, compute, and alert workflows for 24h unattended operation.

## Quality and Tooling
- **pytest**
  - Unit, integration, and selected end-to-end test coverage.
- **ruff**
  - Linting and formatting policy enforcement.
- **mypy**
  - Static type checking for domain correctness and safer refactors.

## Packaging and Local Ops
- **Docker Compose**
  - Local multi-service environment for app, PostgreSQL, Redis, and supporting infrastructure.

## Architecture Conventions
- Prefer a modular monolith for V1 with clear boundaries:
  - `api/` for FastAPI routes and schemas
  - `clients/` for BUFF and Discord integrations
  - `models/` or `db/` for ORM entities and repositories
  - `services/` for orchestration logic
  - `engine/` for trade-up calculations and filters
  - `scheduler/` for APScheduler jobs
  - `core/` for settings, logging, and shared utilities

## Non-Functional Expectations
- Idempotent scheduled jobs where possible
- Config-driven thresholds and secrets
- Structured logging for unattended debugging
- Retry with backoff for transient upstream failures
- No implementation of automation that violates the V1 non-goals in [mission.md](mission.md)

## V1 Delivery Constraint
The first version must remain notification-only. The stack should support future expansion, but current interfaces must not assume auto-purchase, browser-driven actions, or risk-control bypass capabilities.