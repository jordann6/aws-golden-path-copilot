# Example requests

Run any of these with `--offline` (deterministic, no Bedrock) or without it
(drives the Bedrock tool-use loop).

```bash
# Bursty staging database -> burstable Graviton + auto-stop
python -m copilot "I need a Postgres for a staging service, ~50GB, bursty daytime traffic, not latency critical" --team checkout --offline

# Production database -> Multi-AZ, deletion protection, no auto-stop
python -m copilot "production postgres, 300GB, low latency" --team data-eng --offline

# Non-prod stateless service -> Fargate Spot
python -m copilot "a dev worker service for image resizing, stateless" --team growth --offline

# Object storage -> encrypted, versioned S3
python -m copilot "an S3 bucket for staging report exports, 200GB" --team data-eng --offline

# Hardened EC2 host -> CIS AMI (Image Builder), IMDSv2, no public IP, egress via Palo Alto
python -m copilot "a hardened EC2 bastion for staging behind Palo Alto, ~30GB, bursty" --team checkout --offline

# Region-aware pricing -> same host in eu-central-1 reads ~10% higher
python -m copilot "a hardened EC2 host for staging in eu-central-1, 30GB, bursty" --team checkout --offline

# Over-budget request -> policy BLOCKED until --approve
python -m copilot "production postgres database, 500GB, low-latency" --team growth --offline
python -m copilot "production postgres database, 500GB, low-latency" --team growth --offline --approve
```
