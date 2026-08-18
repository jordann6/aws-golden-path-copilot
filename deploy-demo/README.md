# deploy-demo

A throwaway harness that proves a copilot-rendered request actually stands up
real AWS infrastructure and destroys clean. **Not part of the golden path.** In
production the copilot's output is a reviewed pull request whose merge triggers
Terraform through GitOps; nothing here applies automatically.

The harness supplies only the networking the RDS module needs to run in
isolation (a private VPC, two subnets across AZs, a DB subnet group, and a
security group), then calls the **unmodified** vetted `../modules/rds` module
with the copilot's rendered variables, so the receipt reflects real output.

## Run

```sh
# from repo root, render a request
AWS_REGION=us-east-1 python3 -m copilot \
  "Postgres for staging, ~50GB, bursty, not latency critical" --team checkout

# drop the rendered vars in (Terraform auto-loads *.auto.tfvars.json) and apply
cp out/<id>.auto.tfvars.json deploy-demo/
cd deploy-demo
terraform init
terraform apply      # ~5 min: RDS provisioning
terraform destroy    # ~2 min: tears everything down
```

## Receipt (2026-08-18, us-east-1)

One rendered request, `checkout-postgres` for staging, applied and destroyed:

- Instance `checkout-postgres-staging` reached `available` as `db.t4g.micro`,
  Postgres 18.3, 50 GB `gp3`.
- `StorageEncrypted = true`, `MultiAZ = false` (staging), `PubliclyAccessible =
  false`, master password managed in Secrets Manager, all golden-path tags
  present (`CostCenter=CC-1001`, `ManagedBy=golden-path-copilot`).
- `terraform destroy` removed all 6 resources; the RDS-managed secret was
  deleted with the instance. No lingering RDS instance, VPC, or secret.

The instance was live about two minutes, so the run cost a few cents.
