# Golden-Path FinOps Copilot

A self-service provisioning copilot that sits on the seam of platform
engineering and FinOps. A developer describes a resource in plain language; the
copilot turns it into a **right-sized, budget-checked, policy-gated pull
request**, never a direct apply.

The LLM (Claude on Amazon Bedrock) is a translation and advisory layer only. It
maps fuzzy intent onto a fixed catalog of vetted Terraform modules and argues
the cheapest option that still fits the workload. Every deterministic decision
(module selection, cost, budget, policy) lives in code, and the output is always
a diff a human reviews before anything is created.

## Architecture

![Golden-Path FinOps Copilot architecture: a developer request drives Claude on Amazon Bedrock, which calls deterministic right-sizing, cost, budget, and OPA/Rego tools to open a reviewed pull request; Terraform applies only on a human merge, provisioning the AWS resources on the right.](docs/architecture.png)

Claude on Bedrock is advisory and sits outside the determinism boundary.
Everything that actually decides lives in the "decisions in code" cluster, and
the only output is a reviewed pull request. Terraform applies solely on a human
merge, which is when the AWS resources on the right come into being. Regenerate
with `pip install diagrams` (needs Graphviz) and `python3 docs/architecture.py`.

## The flow

```
"I need a Postgres for staging, ~50GB, bursty, not latency critical"
        │
        ▼
  ┌───────────────┐   the model calls tools; it never writes Terraform
  │ Bedrock loop  │   list_golden_paths → right_size → estimate_cost → check_budget
  └──────┬────────┘
         ▼
  right-size   →  t4g burstable Graviton, gp3, nightly auto-stop  (cheapest that fits)
  estimate     →  ~$X/mo   (Infracost if installed, static price table otherwise)
  budget       →  ok / warn / over   vs the team's Cost Explorer envelope
  policy gate  →  OPA/Rego: tags, encryption, GPU approval, prod hardening
         ▼
  render       →  tfvars + module call + PR body  →  Pull Request (not apply)
```

## Why it holds up

The obvious question is "why an LLM instead of a Backstage form?" The form is
still there underneath, as the module catalog and the tool schemas. The model
just removes the requirement that the developer already knows which of N modules
and which instance family they need. Determinism stays in the modules and the
policy; the model's output is always reviewable as a diff. On Bedrock the model
call authenticates with IAM (SigV4), so there is no API key to store or leak,
which is itself on-brand for a FinOps/guardrails project.

## Run it

```bash
make install

# Deterministic pipeline, no Bedrock call, works in CI with no AWS creds:
make demo
make demo REQ="production postgres, 300GB, low latency" TEAM=data-eng

# The real Bedrock tool-use loop (needs AWS creds + Bedrock model access):
make online

# Chat UI at http://127.0.0.1:8000
make web

# Unit tests + OPA policy tests:
make test
```

More examples: [`examples/requests.md`](examples/requests.md).

## Layout

| Path | What |
|------|------|
| `copilot/agent.py` | Bedrock tool-use loop (`AnthropicBedrockMantle`) |
| `copilot/tools.py` | Tool schemas the model calls + dispatch |
| `copilot/catalog.py` | Golden-path catalog + the right-sizing engine |
| `copilot/cost.py` | Cost estimate (Infracost if present, else static table) |
| `copilot/budget.py` | Budget gate vs `data/cost-centers.yaml` |
| `copilot/render.py` | Policy gate + tfvars/PR rendering |
| `modules/` | Vetted Terraform modules (rds, ecs-service, s3-bucket, ec2, image-builder) |
| `policy/provision.rego` | OPA policy + fireable fixtures (`provision_test.rego`) |
| `web/` | FastAPI chat surface |

## FinOps rules the right-sizer encodes

- Graviton (`t4g`/`m7g`) over x86 at equal specs
- Burstable for bursty, non-latency-critical workloads
- Fargate Spot for non-prod stateless services
- Nightly auto-stop for non-prod
- gp3 over gp2, KMS encryption always on
- Prod gets Multi-AZ, deletion protection, min capacity 2; never auto-stop
- Region-aware cost: estimates scale by a per-region multiplier (`data/prices.yaml`), so `eu-central-1` reads ~10% over `us-east-1`

## Hardened compute golden path (`kind: compute`)

Asking for an EC2 host ("a hardened EC2 bastion for staging in eu-central-1
behind Palo Alto") maps to `modules/ec2`, and the copilot enforces a fixed
posture: **CIS-hardened AMI** baked by the in-repo EC2 Image Builder pipeline
(`modules/image-builder`), **IMDSv2 required**, **no public IP** (private subnet
+ SSM Session Manager, no inbound SSH), encrypted gp3 root, and **all egress
routed through the shared Palo Alto VM-Series firewall** for inspection. Those
are not knobs the requester can turn off: the OPA gate re-checks every one of
them, so a hand-edited request that flips on a public IP or a soft AMI is denied
(see the `compute` fixtures in `provision_test.rego`).

The firewall is *referenced*, not provisioned: the module takes the shared
firewall's ENI as `firewall_route_target` and writes the `0.0.0.0/0` route to
it. Standing up the appliance itself would blow the budget on purpose and trip
the approval gate.

## Configuration

| Env var | Default | Notes |
|---------|---------|-------|
| `AWS_REGION` | `us-east-1` | Bedrock region |
| `BEDROCK_MODEL` | `anthropic.claude-sonnet-5` | `anthropic.` prefix required |
| `GITOPS_REPO` | _(unset)_ | `owner/repo` for `--open-pr` |

## Output is a PR, not an apply

`copilot/render.py` writes tfvars, a module call, and a PR body to `out/`. With
`--open-pr` (and `GITOPS_REPO` + `gh` configured) it opens a real PR. `make
deploy`/`make destroy` are deliberately manual: a human merges the PR, then runs
`terraform apply`. The copilot never touches live infrastructure directly.
