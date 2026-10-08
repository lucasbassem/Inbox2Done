# Inbox2Done Kubernetes Runtime

This local kind deployment includes:

- PostgreSQL and Redis StatefulSets with persistent volumes
- a one-shot Alembic migration Job
- two FastAPI replicas behind a ClusterIP Service
- two independently scalable Celery worker replicas
- startup, liveness, and readiness probes
- CPU and memory requests and limits
- non-root application containers
- deploy-time Secret creation from the ignored `.env.docker` file
- a React/Nginx web deployment that proxies the API on the same origin

## Open the application

After deploying, run `kubectl port-forward service/inbox2done-web 8080:80 -n inbox2done`
and open `http://localhost:8080`. Register
`http://localhost:8080/api/auth/google/callback` in Google Cloud.
The API-only port-forward below remains useful for debugging.

## Deploy

```powershell
Unblock-File .\scripts\deploy_kind.ps1
.\scripts\deploy_kind.ps1
```

## Verify and prove worker scaling

```powershell
Unblock-File .\scripts\verify_kubernetes.ps1
.\scripts\verify_kubernetes.ps1
```

## Access the API

Run this in a separate terminal:

```powershell
kubectl port-forward service/inbox2done-api 8000:80 -n inbox2done
```

Then open `http://localhost:8000/docs` or run:

```powershell
Invoke-RestMethod http://localhost:8000/health/ready
```

## Useful operations

```powershell
kubectl get all -n inbox2done
kubectl get pvc -n inbox2done
kubectl logs deployment/inbox2done-api -n inbox2done
kubectl logs deployment/inbox2done-worker -n inbox2done
kubectl logs job/inbox2done-migrate -n inbox2done
kubectl scale deployment/inbox2done-worker --replicas=4 -n inbox2done
kubectl rollout status deployment/inbox2done-worker -n inbox2done
```

## Current scope

This proves a reproducible local Kubernetes runtime. It does not yet claim an
internet-facing production deployment, managed databases, TLS/Ingress, a cloud
secret manager, metrics-based autoscaling, or multi-node failure testing.
