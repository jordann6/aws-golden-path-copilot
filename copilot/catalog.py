"""Golden-path module catalog and the right-sizing engine.

This is the deterministic core of the FinOps story. The LLM never invents
Terraform; it selects one of these vetted modules and hands us an intent. This
module maps that intent onto a right-sized, cost-aware set of parameters and
records *why* each choice was made, so the rationale can go into the PR body.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

WorkloadKind = Literal["database", "service", "storage", "compute"]
Environment = Literal["dev", "staging", "prod"]

# The catalog: each entry maps to a vetted Terraform module under modules/.
CATALOG = {
    "database": {
        "module": "rds",
        "engine": "postgres",
        "description": "Managed PostgreSQL (RDS) with a golden-path config.",
    },
    "service": {
        "module": "ecs-service",
        "description": "Containerized service on ECS Fargate behind the shared ALB.",
    },
    "storage": {
        "module": "s3-bucket",
        "description": "Encrypted, versioned S3 bucket with public access blocked.",
    },
    "compute": {
        "module": "ec2",
        "description": "Hardened EC2 host: CIS-hardened AMI baked by the in-repo "
                       "EC2 Image Builder pipeline, IMDSv2-only, no public IP, "
                       "SSM access, egress inspected by the shared Palo Alto "
                       "VM-Series firewall.",
    },
}

# Burstable Graviton families, smallest to largest.
_BURSTABLE = ["t4g.micro", "t4g.small", "t4g.medium", "t4g.large"]
# Steady-state Graviton general purpose, smallest to largest.
_STEADY = ["m7g.large", "m7g.xlarge", "m7g.2xlarge"]
# GPU/accelerated families. Always policy-gated (approval label required).
_GPU = ["g5.xlarge"]
# x86 equivalents, used only to quantify the Graviton saving in the rationale.
_X86_EQUIV = {"m7g.large": "m7i.large", "m7g.xlarge": "m7i.xlarge"}


@dataclass
class Sizing:
    """The right-sized parameters plus the rationale trail."""

    module: str
    instance_type: str = ""
    storage_gb: int = 0
    storage_class: str = "gp3"
    min_capacity: int = 1
    max_capacity: int = 1
    use_spot: bool = False
    auto_stop: bool = False
    deletion_protection: bool = False
    multi_az: bool = False
    # Hardened-compute posture (kind == "compute"); golden-path constants.
    public_ip: bool = False
    imdsv2_required: bool = False
    firewall_inspected: bool = False
    hardened_ami: bool = False
    rationale: list[str] = field(default_factory=list)
    cheaper_alternative: str | None = None
    params: dict = field(default_factory=dict)


@dataclass
class Intent:
    """Normalized request the LLM (or the offline classifier) produces."""

    kind: WorkloadKind
    environment: Environment = "staging"
    size_gb: int = 20
    latency_sensitive: bool = False
    bursty: bool = False
    stateless: bool = True
    gpu: bool = False
    region: str = "us-east-1"
    name: str = "workload"


def _pick_instance(intent: Intent) -> tuple[str, list[str]]:
    """Choose an instance family and explain the choice."""
    notes: list[str] = []
    # Bursty and not latency-critical -> burstable Graviton.
    if intent.bursty and not intent.latency_sensitive:
        # size the burstable by requested storage as a rough proxy for load
        idx = 0 if intent.size_gb <= 50 else 1 if intent.size_gb <= 200 else 2
        chosen = _BURSTABLE[min(idx, len(_BURSTABLE) - 1)]
        notes.append(
            f"Workload is bursty and not latency-critical, so a burstable "
            f"Graviton instance ({chosen}) fits the profile at the lowest cost."
        )
        return chosen, notes
    # Steady or latency-sensitive -> general purpose Graviton.
    idx = 0 if intent.size_gb <= 200 else 1 if intent.size_gb <= 500 else 2
    chosen = _STEADY[min(idx, len(_STEADY) - 1)]
    notes.append(
        f"Steady/latency-sensitive workload, so a general-purpose Graviton "
        f"instance ({chosen}) is used rather than a burstable one."
    )
    if chosen in _X86_EQUIV:
        notes.append(
            f"Graviton ({chosen}) is chosen over the x86 equivalent "
            f"({_X86_EQUIV[chosen]}) for ~20% lower on-demand cost at equal specs."
        )
    return chosen, notes


def right_size(intent: Intent) -> Sizing:
    """Turn a normalized intent into right-sized module parameters + rationale."""
    entry = CATALOG[intent.kind]
    s = Sizing(module=entry["module"])

    if intent.kind == "storage":
        s.storage_gb = intent.size_gb
        s.storage_class = "s3_standard"
        s.rationale.append(
            "S3 standard storage class; lifecycle rules can move cold objects "
            "to IA/Glacier once access patterns are known."
        )
        s.params = {"bucket_name": intent.name, "versioning": True}
        return s

    if intent.gpu:
        instance = _GPU[0]
        notes = [
            f"GPU workload, so an accelerated instance ({instance}) is selected "
            f"rather than a general-purpose one. GPU requests are policy-gated and "
            f"need an approval label before they can proceed."
        ]
    else:
        instance, notes = _pick_instance(intent)
    s.instance_type = instance
    s.rationale.extend(notes)

    # Storage: always gp3 over gp2.
    s.storage_gb = intent.size_gb
    s.storage_class = "gp3"
    s.rationale.append("gp3 volumes over gp2 (cheaper per GB, tunable IOPS).")

    # Environment-driven guardrails.
    if intent.environment == "prod":
        s.deletion_protection = True
        s.multi_az = intent.kind == "database"
        s.min_capacity = 2
        s.max_capacity = 6
        s.rationale.append(
            "Production: deletion protection on, Multi-AZ for the database, "
            "and a min capacity of 2 for availability."
        )
    else:
        s.auto_stop = True
        s.rationale.append(
            f"Non-prod ({intent.environment}): nightly auto-stop schedule to "
            f"avoid paying for idle time outside working hours."
        )

    # Spot for non-prod stateless services (never for GPU: interruptions would
    # kill long-running training/inference jobs).
    if (intent.kind == "service" and intent.stateless
            and intent.environment != "prod" and not intent.gpu):
        s.use_spot = True
        s.rationale.append(
            "Non-prod stateless service, so Fargate Spot is used for the bulk "
            "of capacity (interruptible, ~70% cheaper)."
        )

    # Hardened compute posture. These are golden-path constants, not knobs the
    # requester can turn off; the policy gate re-checks them (defence in depth).
    if intent.kind == "compute":
        s.public_ip = False
        s.imdsv2_required = True
        s.firewall_inspected = True
        s.hardened_ami = True
        s.rationale.append(
            "Hardened host: CIS-hardened AMI baked by the in-repo EC2 Image "
            "Builder pipeline (modules/image-builder); IMDSv2 required, root EBS "
            "encrypted (gp3/KMS)."
        )
        s.rationale.append(
            "No public IP; launched in a private subnet with SSM Session Manager "
            "for access (no inbound SSH)."
        )
        s.rationale.append(
            "Egress routed through the shared Palo Alto VM-Series firewall for "
            "inspection (0.0.0.0/0 -> firewall route target)."
        )

    # Offer the next tier down as a cheaper alternative when the request looks
    # over-provisioned for a non-prod environment.
    if intent.environment != "prod" and instance in _STEADY:
        s.cheaper_alternative = (
            f"If this staging workload can tolerate burst credits, "
            f"{_BURSTABLE[-1]} would cost materially less than {instance}."
        )

    s.params = {
        "instance_type": s.instance_type,
        "storage_gb": s.storage_gb,
        "storage_class": s.storage_class,
        "multi_az": s.multi_az,
        "deletion_protection": s.deletion_protection,
        "use_spot": s.use_spot,
        "auto_stop": s.auto_stop,
        "min_capacity": s.min_capacity,
        "max_capacity": s.max_capacity,
    }
    if intent.kind == "database":
        s.params["engine"] = CATALOG["database"]["engine"]
    if intent.kind == "compute":
        s.params.update({
            "public_ip": s.public_ip,
            "imdsv2_required": s.imdsv2_required,
            "firewall_inspected": s.firewall_inspected,
            "hardened_ami": s.hardened_ami,
            # AMI id is published to SSM by the Image Builder pipeline; the ec2
            # module reads it so hosts always launch from the latest golden AMI.
            "ami_ssm_parameter": f"/golden-path/ami/{intent.environment}/al2023-cis",
        })
    return s
