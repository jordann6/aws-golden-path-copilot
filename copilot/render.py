"""Render a provisioning request into GitOps output and run the policy gate.

Output is a pull request, never a direct apply. When `gh` is configured and
--open-pr is passed we open a real PR against GITOPS_REPO; otherwise we write
the same artifacts to out/ so the flow is demonstrable with no GitHub access.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field

from . import config
from .budget import BudgetResult
from .catalog import Intent, Sizing
from .cost import CostEstimate


@dataclass
class PolicyResult:
    passed: bool
    violations: list[str] = field(default_factory=list)
    engine: str = ""


def build_request(intent: Intent, sizing: Sizing, budget: BudgetResult,
                  approval_label: bool = False) -> dict:
    """The canonical JSON the OPA policy evaluates."""
    gpu = sizing.instance_type.startswith("g") or sizing.instance_type.startswith("p")
    req = {
        "kind": intent.kind,
        "environment": intent.environment,
        "module": sizing.module,
        "instance_type": sizing.instance_type,
        "storage_class": sizing.storage_class,
        "region": intent.region,
        "encrypted": True,  # golden-path modules always encrypt
        "deletion_protection": sizing.deletion_protection,
        "gpu": gpu,
        "approval_label": approval_label,
        "budget_verdict": budget.verdict,
        "tags": {
            "CostCenter": budget.cost_center,
            "Owner": budget.owner,
            "Environment": intent.environment,
        },
    }
    if intent.kind == "compute":
        # Hardened-host posture the policy gate re-verifies (defence in depth).
        req["public_ip"] = sizing.public_ip
        req["imdsv2"] = sizing.imdsv2_required
        req["firewall_inspected"] = sizing.firewall_inspected
        req["hardened_ami"] = sizing.hardened_ami
    return req


def _python_policy_fallback(req: dict) -> PolicyResult:
    """Mirror of provision.rego for when no policy binary is installed."""
    v: list[str] = []
    for tag in ("CostCenter", "Owner", "Environment"):
        if not req["tags"].get(tag):
            v.append(f"missing required tag: {tag}")
    if req["kind"] != "service" and not req["encrypted"]:
        v.append("storage must be encrypted at rest")
    if req["gpu"] and not req["approval_label"]:
        v.append("GPU instances require an approval label")
    if req["budget_verdict"] == "over" and not req["approval_label"]:
        v.append("request is over the team budget and needs an approval label")
    if (req["environment"] == "prod" and req["kind"] == "database"
            and not req["deletion_protection"]):
        v.append("production databases must have deletion protection enabled")
    if req["kind"] == "compute":
        if req.get("public_ip"):
            v.append("compute instances must not have a public IP (private subnet + SSM only)")
        if not req.get("imdsv2"):
            v.append("compute instances must require IMDSv2")
        if not req.get("firewall_inspected"):
            v.append("compute egress must be routed through the shared firewall for inspection")
        if not req.get("hardened_ami"):
            v.append("compute must launch from a hardened (CIS) golden AMI")
    return PolicyResult(passed=not v, violations=v, engine="python-fallback")


def run_policy(req: dict) -> PolicyResult:
    """Evaluate the request against provision.rego via opa, else fallback."""
    if shutil.which("opa"):
        try:
            proc = subprocess.run(
                ["opa", "eval", "-I", "-d", str(config.POLICY_DIR / "provision.rego"),
                 "-f", "json", "data.provision.deny"],
                input=json.dumps(req), capture_output=True, text=True, timeout=60,
            )
            if proc.returncode == 0:
                out = json.loads(proc.stdout)
                exprs = out.get("result", [{}])[0].get("expressions", [{}])
                violations = exprs[0].get("value", []) if exprs else []
                return PolicyResult(
                    passed=len(violations) == 0,
                    violations=sorted(violations),
                    engine="opa",
                )
        except (subprocess.SubprocessError, ValueError, KeyError, IndexError):
            pass
    return _python_policy_fallback(req)


def _pr_body(intent: Intent, sizing: Sizing, cost: CostEstimate,
             budget: BudgetResult, policy: PolicyResult, req: dict) -> str:
    tick = "PASS" if policy.passed else "BLOCKED"
    lines = [
        f"## Provision `{sizing.module}` for `{intent.name}` ({intent.environment})",
        "",
        f"Requested by the {budget.team} team via the golden-path copilot.",
        "",
        "### Right-sizing rationale",
    ]
    lines += [f"- {r}" for r in sizing.rationale]
    if sizing.cheaper_alternative:
        lines += ["", f"> Cheaper alternative: {sizing.cheaper_alternative}"]
    lines += [
        "",
        f"### Estimated cost ({cost.source})",
        f"**~${cost.monthly_usd:.2f}/month**",
        "",
    ]
    lines += [f"- {b}" for b in cost.breakdown]
    lines += [
        "",
        "### Budget check",
        f"- {budget.message}",
        "",
        f"### Policy gate: {tick} ({policy.engine})",
    ]
    if policy.violations:
        lines += [f"- {v}" for v in policy.violations]
    else:
        lines.append("- No policy violations.")
    lines += [
        "",
        "<details><summary>Rendered request (policy input)</summary>",
        "",
        "```json",
        json.dumps(req, indent=2),
        "```",
        "</details>",
        "",
        "_Generated by the golden-path FinOps copilot. Review the plan before merge._",
    ]
    return "\n".join(lines)


def render(intent: Intent, sizing: Sizing, cost: CostEstimate, budget: BudgetResult,
           policy: PolicyResult, request_id: str, open_pr: bool = False) -> dict:
    """Write tfvars + a module call + PR body. Optionally open a real PR."""
    config.OUT_DIR.mkdir(exist_ok=True)
    req = build_request(intent, sizing, budget)

    tfvars = {
        "name": intent.name,
        "environment": intent.environment,
        "region": intent.region,
        **sizing.params,
        "tags": {
            "CostCenter": budget.cost_center,
            "Owner": budget.owner,
            "Environment": intent.environment,
            "ManagedBy": "golden-path-copilot",
        },
    }
    tfvars_path = config.OUT_DIR / f"{request_id}.auto.tfvars.json"
    tfvars_path.write_text(json.dumps(tfvars, indent=2))

    module_tf = (
        f'module "{intent.name}" {{\n'
        f'  source = "../modules/{sizing.module}"\n'
        f'  # variables supplied via {tfvars_path.name}\n'
        f"}}\n"
    )
    tf_path = config.OUT_DIR / f"{request_id}.tf"
    tf_path.write_text(module_tf)

    body = _pr_body(intent, sizing, cost, budget, policy, req)
    body_path = config.OUT_DIR / f"{request_id}.pr.md"
    body_path.write_text(body)

    result = {
        "tfvars": str(tfvars_path),
        "module_tf": str(tf_path),
        "pr_body": str(body_path),
        "pr_url": None,
    }

    if open_pr and policy.passed and config.GITOPS_REPO and shutil.which("gh"):
        result["pr_url"] = _open_pr(request_id, body_path)
    return result


def _open_pr(request_id: str, body_path) -> str | None:
    branch = f"provision/{request_id}"
    try:
        subprocess.run(["git", "checkout", "-b", branch], check=True,
                       capture_output=True, text=True)
        subprocess.run(["git", "add", str(config.OUT_DIR)], check=True)
        subprocess.run(["git", "commit", "-m", f"provision: {request_id}"], check=True,
                       capture_output=True, text=True)
        subprocess.run(["git", "push", "-u", "origin", branch], check=True,
                       capture_output=True, text=True)
        proc = subprocess.run(
            ["gh", "pr", "create", "--repo", config.GITOPS_REPO,
             "--title", f"Provision {request_id}", "--body-file", str(body_path)],
            check=True, capture_output=True, text=True,
        )
        return proc.stdout.strip()
    except subprocess.SubprocessError:
        return None
