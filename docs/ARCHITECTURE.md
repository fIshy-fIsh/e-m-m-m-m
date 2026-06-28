# Architecture Overview

## Goal
This repository contains the project skeleton for a CS2 BUFF trade-up opportunity scanner. V1 remains notification-only and does not execute purchases or account actions.

## Layers
- **API layer**: FastAPI application and operational endpoints such as `/health`
- **Jobs layer**: scheduler entrypoints and recurring workflows
- **Clients layer**: boundaries for BUFF, metadata, and Discord integrations
- **Services layer**: orchestration logic between clients, repositories, and engines
- **Repositories layer**: persistence access abstractions
- **Models layer**: ORM and domain entities
- **Utils layer**: shared helper utilities

## Infrastructure
- PostgreSQL for durable storage
- Redis for locks, cache, and alert deduplication
- Docker Compose for local multi-service development

## Current Skeleton Scope
The current codebase only provides:
- minimal FastAPI app
- `/health` endpoint
- configuration loading
- database/session placeholders
- placeholder client and scheduler modules

## Deferred to Later Phases
- BUFF endpoint mapping
- BUFF signing/auth details
- metadata normalization
- trade-up engine
- float / EV / probability logic
- Discord alert delivery logic
- APScheduler job graph

## Safety Constraints
- No auto-buy
- No auto-login
- No cookie extraction
- No captcha bypass
- No BUFF risk-control bypass
- No browser-simulated purchasing
- No hard-coded secrets
- Unknown BUFF API details must be tracked in [BUFF_API_NOTES.md](BUFF_API_NOTES.md)
