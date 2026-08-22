"""Cost estimation.

Prefers the `infracost` binary when it is installed and a rendered plan exists;
otherwise falls back to a deterministic estimate from data/prices.yaml so the
tool works offline and in CI with no AWS credentials.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache

import yaml

from . import config
from .catalog import Sizing


@lru_cache(maxsize=1)
def _prices() -> dict:
    with open(config.PRICES_FILE) as f:
        return yaml.safe_load(f)


@dataclass
class CostEstimate:
    monthly_usd: float
    breakdown: list[str]
    source: str  # "static" or "infracost"
    region: str = ""


def _region_multiplier(region: str) -> tuple[float, str | None]:
    """Return the regional cost multiplier and a note when non-default."""
    p = _prices()
    base = p.get("base_region", "us-east-1")
    mults = p.get("region_multipliers", {})
    if region == base:
        return 1.0, None
    if region not in mults:
        return 1.0, (
            f"region {region} not in the price table; estimated at base-region "
            f"({base}) pricing."
        )
    mult = float(mults[region])
    note = None
    if mult != 1.0:
        note = (
            f"regional pricing: {region} is ~{(mult - 1) * 100:.0f}% over the "
            f"base region ({base}); estimate scaled x{mult:g}."
        )
    return mult, note


def _static_estimate(sizing: Sizing, kind: str, region: str) -> CostEstimate:
    p = _prices()
    hours = p["hours_per_month"]
    mult, region_note = _region_multiplier(region)
    lines: list[str] = []
    total = 0.0

    if kind == "storage":
        gb_rate = p["storage"]["s3_standard"] * mult
        cost = sizing.storage_gb * gb_rate
        total += cost
        lines.append(f"S3 standard {sizing.storage_gb} GB @ ${gb_rate:.4f}/GB-mo = ${cost:.2f}")
        if region_note:
            lines.append(region_note)
        return CostEstimate(round(total, 2), lines, "static", region)

    # Compute
    hourly = p["instances"].get(sizing.instance_type)
    if hourly is None:
        lines.append(f"Unknown instance {sizing.instance_type}; compute not priced.")
    else:
        hourly *= mult
        # A nightly auto-stop schedule (non-prod) roughly halves running hours.
        effective_hours = hours * 0.5 if sizing.auto_stop else hours
        # Spot discount for the bulk of Fargate capacity.
        rate = hourly * 0.3 if sizing.use_spot else hourly
        rate *= p["rds_multiplier"] if kind == "database" else 1.0
        replicas = sizing.min_capacity
        compute = rate * effective_hours * replicas
        total += compute
        tags = []
        if sizing.auto_stop:
            tags.append("auto-stop ~50% hours")
        if sizing.use_spot:
            tags.append("spot ~70% off")
        if kind == "database":
            tags.append(f"RDS x{p['rds_multiplier']}")
        suffix = f" ({', '.join(tags)})" if tags else ""
        lines.append(
            f"{replicas}x {sizing.instance_type} @ ${hourly}/hr{suffix} = ${compute:.2f}/mo"
        )

    # Storage
    if sizing.storage_gb:
        gb_rate = p["storage"].get(sizing.storage_class, p["storage"]["gp3"]) * mult
        storage = sizing.storage_gb * gb_rate
        total += storage
        lines.append(
            f"{sizing.storage_gb} GB {sizing.storage_class} @ ${gb_rate:.4f}/GB-mo = ${storage:.2f}/mo"
        )

    if region_note:
        lines.append(region_note)
    return CostEstimate(round(total, 2), lines, "static", region)


def _infracost_estimate(plan_dir: str, region: str) -> CostEstimate | None:
    """Run infracost against a rendered Terraform dir, if available."""
    if not shutil.which("infracost"):
        return None
    try:
        proc = subprocess.run(
            ["infracost", "breakdown", "--path", plan_dir, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout)
        monthly = float(data["totalMonthlyCost"])
        lines = [f"infracost totalMonthlyCost = ${monthly:.2f}/mo"]
        return CostEstimate(round(monthly, 2), lines, "infracost", region)
    except (subprocess.SubprocessError, KeyError, ValueError):
        return None


def estimate(sizing: Sizing, kind: str, plan_dir: str | None = None,
             region: str | None = None) -> CostEstimate:
    region = region or _prices().get("base_region", "us-east-1")
    if plan_dir:
        live = _infracost_estimate(plan_dir, region)
        if live is not None:
            return live
    return _static_estimate(sizing, kind, region)
