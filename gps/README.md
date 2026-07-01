# GPS EGTS Service

Go service for receiving EGTS GPS packets and writing them into PostgreSQL/TimescaleDB.

## What it does

- accepts EGTS packets over TCP
- extracts GPS points from tracker messages
- writes history into `gps_timeline`
- updates current state in `gps_current_position`
- registers new devices in `bus_trackers`

## Storage

The service writes to these tables:

- `bus_trackers`
- `gps_timeline`
- `gps_current_position`

`gps_timeline` is a TimescaleDB hypertable with lifecycle policies:

- compression after `30 days`
- retention for `3 months`

## Run locally

```bash
uv run alembic upgrade head
cd gps
go mod tidy
go run ./cmd/receiver -c ./configs/receiver.yaml
```

## Docker

The service is also available through the root `docker-compose.yml` as `gps-egts`.

Ports:

- `9000` - EGTS TCP receiver
- `8001` - healthcheck

Healthcheck endpoint:

```text
GET /healthz
```

## Config

Base config file:

```text
gps/configs/receiver.yaml
```

Environment overrides:

- `GPS_EGTS_HOST`
- `GPS_EGTS_PORT`
- `GPS_DATABASE_DSN`
- `GPS_DATABASE_MAX_CONNECTIONS`
- `GPS_EGTS_DISPATCHER_HOST`
- `GPS_LOG_LEVEL`
- `GPS_HEALTH_HOST`
- `GPS_HEALTH_PORT`

Defaults:

- TCP listen: `0.0.0.0:9000`
- health: `0.0.0.0:8001`

If `GPS_EGTS_DISPATCHER_HOST` is set, the service resolves its current IPv4 address and includes it in EGTS auth responses as dispatcher identity.

## Notes

- `gps_timeline` is optimized for queries by `device_id + navigation_time`
- `gps_current_position` is intended for current map/state queries
- old GPS history is deleted automatically by TimescaleDB retention policy
