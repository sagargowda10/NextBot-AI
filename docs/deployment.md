# Deployment

## Local
| Command | What runs |
|---|---|
| `docker compose -f docker-compose.dev.yml up --build` | backend (SQLite, in-memory bus/cache) + frontend |
| `docker compose up --build` | + PostgreSQL/pgvector, Redis, MongoDB, Kafka (KRaft, topics + DLQs via `kafka-init`), Prometheus, Grafana |
| `docker compose --profile search up --build` | + OpenSearch (set `SEARCH_BACKEND=opensearch`, `OPENSEARCH_URL=http://opensearch:9200`) |
| `scripts/dev.sh` | no Docker: venv + uvicorn + `next dev` |

Health: `GET /health` (liveness), `GET /health/ready` (DB, cache, traces, plugin summary, bus). Metrics: `GET /metrics`.
Grafana (http://localhost:3001) auto-provisions the *NextBot AI — Platform Overview* dashboard.

## CI/CD (`.github/workflows/ci.yml`)
`backend` (ruff, mypy, unit, integration incl. Testcontainers, `alembic upgrade head`) · `frontend` (typecheck, lint, build) ·
`e2e` (compose dev stack + Playwright) · `images` (build & push to GHCR on `main`).

## Kubernetes (`infrastructure/kubernetes`)
`kubectl apply -k infrastructure/kubernetes` after creating the secret from `secret.template.yaml`.
Includes namespace, ConfigMap, backend Deployment (2+ replicas, probes, resource limits, non-root, read-only FS) + Service + HPA,
migration Job (`alembic upgrade head`), frontend Deployment + Service, ALB Ingress (`shop.` / `api.` hosts).
Run the migration Job before each backend rollout; set `SEED_ON_STARTUP=false` and `ENVIRONMENT=production` (the app then
never calls `create_all`).

## AWS reference
| Need | Service |
|---|---|
| Containers | EKS (or ECS Fargate with the same images) |
| PostgreSQL + pgvector | RDS for PostgreSQL 16 (`CREATE EXTENSION vector`) |
| Redis | ElastiCache for Redis (TLS → `rediss://`) |
| Kafka | Amazon MSK (create the 12 topics with `create-topics.sh`) |
| MongoDB | MongoDB Atlas or DocumentDB |
| Secrets | Secrets Manager + External Secrets Operator |
| Ingress/TLS | AWS Load Balancer Controller + ACM |
| Observability | Amazon Managed Prometheus/Grafana or self-hosted; OTLP → ADOT collector |

Scaling notes: the API is stateless (memory in Redis), so replicas scale horizontally. The outbox relay is safe to run on every
replica (at-least-once + idempotent consumers); for very high volume move it to a dedicated deployment or use
`SELECT … FOR UPDATE SKIP LOCKED` batching. In-process metrics are per pod — use Prometheus aggregation.
