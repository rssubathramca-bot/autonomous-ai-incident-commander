# Phase 3: Deterministic incident engine

The incident engine uses ordinary Python and SQLAlchemy operations. It does not call an
LLM and does not infer evidence.

## Routes

- `POST /incidents` — create an incident associated with an existing service
- `GET /incidents/{id}` — return the incident, service, timeline, and associated records
- `PATCH /incidents/{id}/status` — apply a validated status transition
- `POST /incidents/{id}/severity` — assign severity from explicit operational signals
- `GET /incidents/{id}/evidence` and `GET /incidents/{id}/metrics`
- `POST /incidents/{id}/logs`, `/deployments`, `/metrics`, and `/evidence`

## Deterministic severity rules

Severity is assigned by the highest matching signal threshold, in priority order:

| Severity | Error rate | Latency | Database pool waiters |
| --- | ---: | ---: | ---: |
| SEV-1 | >= 50% | >= 5000 ms | >= 50 |
| SEV-2 | >= 20% | >= 2000 ms | >= 20 |
| SEV-3 | >= 5% | >= 1000 ms | >= 5 |
| SEV-4 | Below all thresholds | Below all thresholds | Below all thresholds |

Incident creation may also accept an explicit SEV-1 through SEV-4 assignment.

## Status transitions

- `open` → `investigating` or `closed`
- `investigating` → `mitigated` or `resolved`
- `mitigated` → `investigating` or `resolved`
- `resolved` → `investigating` or `closed`
- `closed` → no further status

Invalid transitions return HTTP 409. A transition to `resolved` records a resolution
timestamp; reopening clears it. Status, severity, and resource-ingestion changes are
recorded as incident timeline events.