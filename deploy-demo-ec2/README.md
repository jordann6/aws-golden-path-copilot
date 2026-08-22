# deploy-demo-ec2

A throwaway harness that proves a copilot-rendered **hardened-compute** request
stands up a real, correctly-postured EC2 host and destroys clean. **Not part of
the golden path.** In production the copilot's output is a reviewed pull request
whose merge triggers Terraform through GitOps; nothing here applies
automatically.

The harness supplies only what the `../modules/ec2` module needs to run in
isolation (a VPC, a private subnet, a private route table, and a stand-in ENI
for the shared Palo Alto VM-Series firewall), then calls the **unmodified**
`../modules/ec2` and `../modules/image-builder` with the copilot's rendered
variables.

**Real vs. represented:** the Image Builder pipeline is applied for real.
Actually baking an AMI takes ~30 min and real money for no extra demo value, so
the golden-AMI SSM parameter the host reads is seeded with the current AL2023
arm64 AMI, standing in for a completed pipeline build. The firewall is a stand-in
ENI: the egress route wires up against the real module, but no appliance sits
behind it (so the route reads `blackhole`); in production that ENI is the live
firewall and traffic is inspected.

## Run

```sh
# from repo root, render a hardened-EC2 request
python3 -m copilot \
  "a hardened EC2 bastion for staging behind Palo Alto, ~30GB, bursty, not latency critical" \
  --team checkout --offline

# drop the rendered vars in (Terraform auto-loads *.auto.tfvars.json) and apply
cp out/<id>.auto.tfvars.json deploy-demo-ec2/
cd deploy-demo-ec2
terraform init
terraform apply      # ~1 min: host reaches running
terraform destroy    # ~1.5 min: tears everything down
```

## Receipt (2026-08-21, us-east-1)

One rendered request, `staging-behind-palo-alto` for staging, applied and
destroyed. 23 resources across the two modules + the throwaway network.

Host `i-0c8d244ad9df8a369` reached `running` as `t4g.micro` (Graviton), from the
seeded golden AMI, with the golden-path posture verified live via the EC2 API:

- **IMDSv2 required** (`HttpTokens=required`, hop limit 1)
- **No public IP** (`PublicIpAddress=None`); launched in the private subnet
- **Encrypted root volume** (`Encrypted=true`, `gp3`, 30 GB)
- Detailed monitoring enabled
- All golden-path tags present (`CostCenter=CC-1001`,
  `Owner=checkout-platform@example.com`, `Environment=staging`,
  `ManagedBy=golden-path-copilot`)
- Private subnet default route `0.0.0.0/0` -> the firewall ENI
  (`eni-02032f9d9aa9c5f66`); `blackhole` because the stand-in ENI has no
  appliance behind it (route wiring proven)

The Image Builder pipeline applied for real and was `ENABLED` with a weekly
rebuild schedule; the recipe carried two components (AWS-managed `update-linux`
patch baseline + the module's custom CIS hardening component).

`terraform destroy` removed all 23 resources. Post-destroy sweep: instance
`terminated`, VPC gone, both `/golden-path/ami/staging/*` SSM parameters deleted,
no Image Builder pipeline left. The host was live about two to three minutes, so
the run cost a few cents.
