# Deployment Guide

## Local Development (Docker Compose)

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f api
docker compose logs -f celery-worker

# Run migrations
docker compose exec api alembic upgrade head

# Stop all services
docker compose down

# Stop and remove volumes (clean slate)
docker compose down -v
```

### Service Ports (local)

| Service | Port |
|---------|------|
| AML API | 8000 |
| Dashboard | 3000 |
| MLflow | 5000 |
| PostgreSQL | 5433 |
| Redis | 6380 |

## Kubernetes Deployment

### Cluster Capacity Requirements

#### Per-Pod Resource Allocation

| Component | Replicas | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|:--------:|:-----------:|:---------:|:--------------:|:------------:|
| API (FastAPI) | 2 | 250m | 1 core | 512 Mi | 1 Gi |
| Celery Worker | 2 | 500m | 2 cores | 1 Gi | 2 Gi |
| Celery Beat | 1 | 100m | 250m | 128 Mi | 256 Mi |
| Dashboard (nginx) | 1 | 50m | 200m | 64 Mi | 128 Mi |
| PostgreSQL | 1 | 250m | 1 core | 512 Mi | 2 Gi |
| Redis | 1 | 100m | 500m | 128 Mi | 512 Mi |
| MLflow | 1 | 100m | 500m | 256 Mi | 512 Mi |

#### Recommended Cluster Sizes

| Tier | Use Case | Nodes | Total CPU | Total RAM | Storage |
|------|----------|:-----:|:---------:|:---------:|:-------:|
| **Minimum** | Dev/staging, all on 1 node | 1 | 4 vCPU | 8 Gi | 60 Gi |
| **Recommended** | Small production (<10K txn/day) | 2 | 8 vCPU | 16 Gi | 100 Gi |
| **Production** | Medium load (10K-100K txn/day) | 3 | 12 vCPU | 32 Gi | 200 Gi |

#### Storage Breakdown

| Volume | Size | Purpose |
|--------|:----:|---------|
| PostgreSQL data | 20 Gi | Transaction data (~7 years retention) |
| PostgreSQL backup | 20 Gi | Daily pg_dump backups (30-day rotation) |
| MLflow artifacts | 10 Gi | Model versions and training artifacts |
| Model storage (shared) | 5 Gi | Active .joblib model files |
| Redis | 2 Gi | Celery broker + cache |
| **Total** | **57 Gi** | |

#### Cloud Provider Sizing Examples

| Provider | Instance Type | vCPU | RAM | Monthly Cost (est.) |
|----------|--------------|:----:|:---:|:-------------------:|
| AWS EKS (minimum) | 1x `t3.xlarge` | 4 | 16 Gi | ~$120 |
| AWS EKS (recommended) | 2x `t3.large` | 4 | 16 Gi | ~$150 |
| GCP GKE (minimum) | 1x `e2-standard-4` | 4 | 16 Gi | ~$100 |
| GCP GKE (recommended) | 2x `e2-standard-2` | 4 | 16 Gi | ~$130 |
| Azure AKS (minimum) | 1x `Standard_D4s_v3` | 4 | 16 Gi | ~$140 |
| DigitalOcean (minimum) | 1x `s-4vcpu-8gb` | 4 | 8 Gi | ~$48 |

For a microfinance institution in the CEMAC zone processing a few thousand transactions per day, the **minimum tier (1 node, 4 vCPU, 8 Gi)** is sufficient to start.

### Prerequisites

- Kubernetes cluster (1.28+)
- `kubectl` configured
- `helm` 3.x installed
- Container registry access (GHCR)

### Option A: Helm Chart (Recommended)

```bash
# Install with required secrets
helm install aml ./helm/fineract-aml \
  --set secrets.secretKey="$(openssl rand -hex 32)" \
  --set secrets.webhookSecret="$(openssl rand -hex 32)" \
  --set secrets.dbPassword="$(openssl rand -hex 16)" \
  --set config.corsOrigins="https://aml.yourdomain.com"

# The Helm chart automatically:
# - Creates the namespace
# - Deploys all services (API, workers, beat, dashboard, postgres, redis)
# - Runs database migrations (post-install hook)
# - Configures secrets and config maps

# Verify
kubectl get pods -n aml
```

To customize resources, edit `helm/fineract-aml/values.yaml` or override via `--set`:

```bash
# Scale workers for higher throughput
helm upgrade aml ./helm/fineract-aml --set worker.replicaCount=4

# Enable ingress
helm upgrade aml ./helm/fineract-aml \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=aml.yourdomain.com
```

### Option B: Raw Kubernetes Manifests

#### Step 1: Create Namespace and Secrets

```bash
kubectl apply -f k8s/namespace.yaml

kubectl create secret generic aml-secrets \
  --namespace=aml \
  --from-literal=database-url="postgresql+asyncpg://aml:STRONG_PASSWORD@aml-postgres:5432/fineract_aml" \
  --from-literal=redis-url="redis://aml-redis:6379/0" \
  --from-literal=celery-broker-url="redis://aml-redis:6379/1" \
  --from-literal=celery-result-backend="redis://aml-redis:6379/2" \
  --from-literal=webhook-secret="YOUR_WEBHOOK_SECRET" \
  --from-literal=jwt-secret="YOUR_JWT_SECRET" \
  --from-literal=postgres-user="aml" \
  --from-literal=postgres-password="STRONG_PASSWORD"
```

#### Step 2: Deploy Infrastructure

```bash
kubectl apply -f k8s/postgres/
kubectl apply -f k8s/redis/

kubectl wait --namespace=aml --for=condition=ready pod -l app=aml-postgres --timeout=120s
```

#### Step 3: Deploy Application

```bash
kubectl apply -f k8s/api/
kubectl apply -f k8s/dashboard/
```

#### Step 4: Run Migrations

```bash
kubectl exec -n aml deploy/aml-api -- alembic upgrade head
```

#### Step 5: Verify

```bash
kubectl get pods -n aml
kubectl logs -n aml deploy/aml-api
curl http://<cluster-ip>:8000/health
```

### Seed Synthetic Data and Train Models

To bootstrap the system with training data (optional — for testing or pre-production):

```bash
kubectl exec -n aml deploy/aml-api -- python scripts/generate_training_data.py --seed-db --clients 200 --transactions 20000 --fraud-rate 0.03
```

This creates 20K transactions with 6 fraud patterns, labels them, and trains both ML models.

## GitOps with ArgoCD

If you're using ArgoCD for your Fineract deployment, add the AML app:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: fineract-aml
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/ADORSYS-GIS/fineract-aml.git
    targetRevision: main
    path: k8s
  destination:
    server: https://kubernetes.default.svc
    namespace: aml
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

## CI/CD Pipeline

### Build and Push Images

```yaml
# .github/workflows/build.yml
name: Build and Push
on:
  push:
    branches: [main]

jobs:
  build-api:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: ./backend
          push: true
          tags: ghcr.io/adorsys-gis/fineract-aml-api:latest

  build-dashboard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: ./dashboard
          push: true
          tags: ghcr.io/adorsys-gis/fineract-aml-dashboard:latest
```

## Production Considerations

### Security

- [ ] Change all default secrets (`AML_SECRET_KEY`, `AML_FINERACT_WEBHOOK_SECRET`)
- [ ] Enable HTTPS/TLS on all endpoints
- [ ] Configure CORS to allow only the dashboard origin
- [ ] Set up Kubernetes NetworkPolicies between namespaces
- [ ] Enable PostgreSQL SSL connections
- [ ] Rotate JWT secrets periodically

### Scaling

- **API pods**: Stateless — scale horizontally by increasing `api.replicaCount`. Each pod handles ~500 req/s.
- **Celery workers**: Main throughput lever. Each worker runs 4 concurrent tasks (`concurrency=4`), so 2 workers = 8 parallel transaction analyses. Increase `worker.replicaCount` for higher transaction volume.
- **Celery beat**: Always exactly 1 replica (scheduler — must not be duplicated).
- **PostgreSQL**: Bottleneck above ~50K txn/day. Consider managed service (RDS, Cloud SQL) with read replicas for production.
- **Redis**: Consider managed service (ElastiCache, Memorystore) for HA.
- **Model retraining**: CPU-intensive but short-lived (weekly). Workers handle it during off-peak hours automatically.

### Monitoring

- Application logs → centralized logging (ELK, Loki)
- Metrics → Prometheus + Grafana
- ML model performance → MLflow
- Alert on: high error rates, model drift, queue backlog

### Backup

- PostgreSQL: daily backups with point-in-time recovery
- ML models: versioned in MLflow (artifacts stored separately)
- Configuration: managed via GitOps
