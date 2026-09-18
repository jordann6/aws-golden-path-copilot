"""Waste reclamation: turn cost-dashboard waste findings into a reviewed
cleanup pull request, never a direct apply.

This closes the FinOps loop the rest of the portfolio only informs on. The cost
intelligence dashboard *detects* idle spend (unattached EBS, gp2 volumes, stray
Elastic IPs); this module *acts* on it, under the same determinism boundary as
provisioning. The model (or the CLI) chooses which findings to act on; the
remediation, the dollar figure, and the gate are all computed here in code, and
the output is a pull request a human merges.

Two gates keep it safe:
  1. Unattributed waste (no CostCenter tag) is never auto-remediated. If we
     cannot name the cost centre that owns a resource, a human decides. This is
     the same tagging discipline the guardrails enforce, applied at the point of
     action rather than at provision time.
  2. Destructive actions (delete a volume, release an address) need an approval
     label. Without it they are listed but held, so a run can still ship the
     safe, reversible actions (gp2 -> gp3) while destructive ones wait.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import urllib.request
import uuid
from dataclasses import dataclass, field

from . import config


@dataclass
class WasteFinding:
    resource_type: str  # unattached_ebs | gp2_volume | unassociated_eip
    resource_id: str
    region: str
    monthly_cost_usd: float
    reason: str
    tags: dict = field(default_factory=dict)


@dataclass
class Remediation:
    resource_id: str
    resource_type: str
    action: str
    destructive: bool
    monthly_savings_usd: float
    commands: list[str] = field(default_factory=list)
    blocked: bool = False
    blocked_reason: str = ""


def load_findings(source: str | None = None) -> list[WasteFinding]:
    """Load findings from a local JSON file or a live cost-dashboard endpoint.

    A source starting with http(s) is fetched (point it at the dashboard's
    `/waste` route); anything else is read as a file. Default is the bundled
    fixture, so the whole flow is demonstrable with no dashboard deployed.
    """
    source = source or str(config.DATA_DIR / "waste-findings.json")
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=10) as r:  # noqa: S310 (trusted URL)
            raw = json.loads(r.read().decode())
    else:
        with open(source) as fh:
            raw = json.load(fh)

    findings = []
    for i in raw:
        findings.append(WasteFinding(
            resource_type=i.get("resource_type") or i.get("type", "unknown"),
            resource_id=i.get("resource_id") or i.get("id", "unknown"),
            region=i.get("region", "us-east-1"),
            monthly_cost_usd=float(i.get("monthly_cost_usd") or i.get("monthly_cost", 0)),
            reason=i.get("reason", ""),
            tags=i.get("tags", {}) or {},
        ))
    return findings


def plan(f: WasteFinding) -> Remediation:
    """Map a single finding to a deterministic remediation, applying gate 1."""
    savings = f.monthly_cost_usd

    # Gate 1: unattributed waste is not auto-remediated.
    if not f.tags.get("CostCenter"):
        return Remediation(
            f.resource_id, f.resource_type, "review: no CostCenter tag",
            destructive=False, monthly_savings_usd=savings, commands=[],
            blocked=True,
            blocked_reason="unattributed waste; tag CostCenter before reclaiming",
        )

    r, rid = f.region, f.resource_id
    if f.resource_type == "unattached_ebs":
        return Remediation(
            rid, f.resource_type, f"Delete unattached EBS volume {rid}",
            destructive=True, monthly_savings_usd=savings,
            commands=[f"aws ec2 delete-volume --region {r} --volume-id {rid}"],
        )
    if f.resource_type == "unassociated_eip":
        return Remediation(
            rid, f.resource_type, f"Release unassociated Elastic IP {rid}",
            destructive=True, monthly_savings_usd=savings,
            commands=[f"aws ec2 release-address --region {r} --allocation-id {rid}"],
        )
    if f.resource_type == "gp2_volume":
        return Remediation(
            rid, f.resource_type, f"Migrate {rid} from gp2 to gp3 (no downtime)",
            destructive=False, monthly_savings_usd=savings,
            commands=[f"aws ec2 modify-volume --region {r} --volume-id {rid} --volume-type gp3"],
        )
    return Remediation(
        rid, f.resource_type, f"No remediation mapped for {f.resource_type}",
        destructive=False, monthly_savings_usd=savings, commands=[],
        blocked=True, blocked_reason=f"unknown finding type: {f.resource_type}",
    )


def build(source: str | None = None, approval_label: bool = False) -> list[Remediation]:
    """Plan remediations for every finding, applying gate 2 (destructive hold)."""
    rems = [plan(f) for f in load_findings(source)]
    for r in rems:
        if r.destructive and not r.blocked and not approval_label:
            r.blocked = True
            r.blocked_reason = "destructive action; needs an approval label"
    return rems


def _pr_body(request_id: str, actionable: list[Remediation],
             held: list[Remediation], savings: float, potential: float) -> str:
    lines = [
        f"## Reclaim idle spend ({request_id})",
        "",
        "Cleanup proposed by the golden-path FinOps copilot from cost-dashboard "
        "waste findings. This is a pull request, not an apply: review the script "
        "and merge to act.",
        "",
        f"**Reclaimable now: ~${savings:.2f}/month** across {len(actionable)} "
        f"resource(s). Potential if all holds are approved/tagged: "
        f"~${potential:.2f}/month.",
        "",
        "### Actionable",
    ]
    if actionable:
        for r in actionable:
            flag = " (destructive, approved)" if r.destructive else ""
            lines.append(f"- {r.action} — ~${r.monthly_savings_usd:.2f}/mo{flag}")
    else:
        lines.append("- Nothing actionable without approval or tagging.")
    lines += ["", "### Held"]
    if held:
        for r in held:
            lines.append(f"- {r.resource_id} ({r.resource_type}): {r.blocked_reason} "
                         f"— ~${r.monthly_savings_usd:.2f}/mo")
    else:
        lines.append("- None.")
    lines += [
        "",
        "<details><summary>Remediation script (review before merge)</summary>",
        "",
        "```bash",
        _script(actionable).rstrip(),
        "```",
        "</details>",
        "",
        "_Generated by the golden-path FinOps copilot. Nothing is deleted until a "
        "human merges and runs the script._",
    ]
    return "\n".join(lines)


def _script(actionable: list[Remediation]) -> str:
    body = "\n".join(c for r in actionable for c in r.commands)
    return "#!/usr/bin/env bash\nset -euo pipefail\n" + body + "\n"


def render(rems: list[Remediation], request_id: str | None = None,
           open_pr: bool = False) -> dict:
    """Write a cleanup PR body + a runnable (never auto-run) script to out/."""
    request_id = request_id or f"reclaim-{uuid.uuid4().hex[:8]}"
    config.OUT_DIR.mkdir(exist_ok=True)

    actionable = [r for r in rems if not r.blocked]
    held = [r for r in rems if r.blocked]
    savings = sum(r.monthly_savings_usd for r in actionable)
    potential = sum(r.monthly_savings_usd for r in rems)

    body_path = config.OUT_DIR / f"{request_id}.pr.md"
    body_path.write_text(_pr_body(request_id, actionable, held, savings, potential))
    script_path = config.OUT_DIR / f"{request_id}.sh"
    script_path.write_text(_script(actionable))

    result = {
        "request_id": request_id,
        "pr_body": str(body_path),
        "script": str(script_path),
        "monthly_savings_usd": round(savings, 2),
        "potential_savings_usd": round(potential, 2),
        "actionable": len(actionable),
        "held": len(held),
        "pr_url": None,
    }
    if open_pr and actionable and config.GITOPS_REPO and shutil.which("gh"):
        result["pr_url"] = _open_pr(request_id, body_path, script_path)
    return result


def _open_pr(request_id: str, body_path, script_path) -> str | None:
    branch = f"reclaim/{request_id}"
    try:
        subprocess.run(["git", "checkout", "-b", branch], check=True,
                       capture_output=True, text=True)
        subprocess.run(["git", "add", str(body_path), str(script_path)], check=True)
        subprocess.run(["git", "commit", "-m", f"reclaim: {request_id}"], check=True,
                       capture_output=True, text=True)
        subprocess.run(["git", "push", "-u", "origin", branch], check=True,
                       capture_output=True, text=True)
        proc = subprocess.run(
            ["gh", "pr", "create", "--repo", config.GITOPS_REPO,
             "--title", f"Reclaim idle spend {request_id}", "--body-file", str(body_path)],
            check=True, capture_output=True, text=True,
        )
        return proc.stdout.strip()
    except subprocess.SubprocessError:
        return None
