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

### Prerequisites

- Kubernetes cluster (1.28+)
- `kubectl` configured
- Container registry access (GHCR)

### Step 1: Create Namespace and Secrets

```bash
# Create namespace
kubectl apply -f k8s/namespace.yaml

# Create secrets (replace values)
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

### Step 2: Deploy Infrastructure

```bash
kubectl apply -f k8s/postgres/
kubectl apply -f k8s/redis/

# Wait for database to be ready
kubectl wait --namespace=aml --for=condition=ready pod -l app=aml-postgres --timeout=120s
```

### Step 3: Deploy Application

```bash
kubectl apply -f k8s/api/
kubectl apply -f k8s/dashboard/
```

### Step 4: Run Migrations

```bash
kubectl exec -n aml deploy/aml-api -- alembic upgrade head
```

### Step 5: Verify

```bash
kubectl get pods -n aml
kubectl logs -n aml deploy/aml-api
curl http://<cluster-ip>:8000/health
```

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

- **API**: Scale horizontally (increase replicas)
- **Celery workers**: Scale based on transaction volume
- **Celery beat**: Always exactly 1 replica
- **PostgreSQL**: Consider managed service (RDS, Cloud SQL) for production
- **Redis**: Consider managed service (ElastiCache, Memorystore)

### Monitoring

- Application logs → centralized logging (ELK, Loki)
- Metrics → Prometheus + Grafana
- ML model performance → MLflow
- Alert on: high error rates, model drift, queue backlog

### Backup

- PostgreSQL: daily backups with point-in-time recovery
- ML models: versioned in MLflow (artifacts stored separately)
- Configuration: managed via GitOps
