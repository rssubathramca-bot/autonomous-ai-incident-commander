# Phase 4: Isolated e-commerce simulation

This environment is synthetic and must not be pointed at production systems.
`docker-compose.simulation.yml` creates an internal-only Docker network. The only host
port is the API gateway, bound to `127.0.0.1:8088`. No real database, payment provider,
order platform, or production endpoint is contacted.

## Start the simulation

```bash
docker compose -f docker-compose.simulation.yml up --build
```

OpenAPI docs: `http://127.0.0.1:8088/docs`

## Healthy → failure → rollback

All mutating simulation routes require the JSON acknowledgement
`{"acknowledge_simulation_only": true}`.

```bash
# Check the HEALTHY baseline: DB_POOL_SIZE=50
curl http://127.0.0.1:8088/simulation/state

# Generate baseline synthetic traffic
curl -X POST http://127.0.0.1:8088/simulation/run \
  -H 'Content-Type: application/json' \
  -d '{"request_volume":40,"acknowledge_simulation_only":true}'

# Inject the controlled failure: DB_POOL_SIZE 50 → 10
curl -X POST http://127.0.0.1:8088/simulation/failure-injection \
  -H 'Content-Type: application/json' \
  -d '{"acknowledge_simulation_only":true}'

# Repeat traffic to observe connection timeouts, errors, and latency increase
curl -X POST http://127.0.0.1:8088/simulation/run \
  -H 'Content-Type: application/json' \
  -d '{"request_volume":40,"acknowledge_simulation_only":true}'

# Roll back only the simulator to DB_POOL_SIZE=50
curl -X POST http://127.0.0.1:8088/simulation/rollback \
  -H 'Content-Type: application/json' \
  -d '{"acknowledge_simulation_only":true}'

# Inspect logs, metrics, and simulated deployment events
curl http://127.0.0.1:8088/simulation/report
```

The database simulation uses an in-memory concurrency limiter; it does not connect to
SQLite, PostgreSQL, or another database. Checkout and order services keep synthetic
records and logs in process memory. Failed checkout requests incur a fixed 600 ms
synthetic retry delay so the latency regression is clear and repeatable in the demo.
