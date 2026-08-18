"""Bedrock tool definitions + dispatch.

These are the deterministic functions the model calls. The model turns fuzzy
human intent into calls against this fixed surface; it never emits Terraform or
prices of its own. `submit_for_review` is terminal and produces the PR.
"""
from __future__ import annotations

from dataclasses import asdict

from .budget import check as check_budget
from .catalog import Intent, right_size
from .cost import estimate as estimate_cost
from . import pipeline

_INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["database", "service", "storage"]},
        "environment": {"type": "string", "enum": ["dev", "staging", "prod"]},
        "size_gb": {"type": "integer", "description": "Approximate storage size in GB"},
        "latency_sensitive": {"type": "boolean"},
        "bursty": {"type": "boolean", "description": "Traffic is spiky rather than steady"},
        "stateless": {"type": "boolean"},
        "name": {"type": "string", "description": "Short kebab-case name for the workload"},
    },
    "required": ["kind", "environment", "size_gb", "name"],
    "additionalProperties": False,
}

TOOLS = [
    {
        "name": "list_golden_paths",
        "description": "List the approved (golden-path) module catalog. Call this "
                       "first to see which vetted modules exist. The model must map "
                       "the request onto one of these; it never authors new modules.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "right_size",
        "description": "Given a normalized intent, return right-sized module "
                       "parameters (instance family, storage, spot, auto-stop, "
                       "Multi-AZ) plus a rationale for each choice.",
        "input_schema": _INTENT_SCHEMA,
    },
    {
        "name": "estimate_cost",
        "description": "Estimate the monthly USD cost of a right-sized plan. Pass "
                       "the same intent used for right_size.",
        "input_schema": _INTENT_SCHEMA,
    },
    {
        "name": "check_budget",
        "description": "Check a monthly cost estimate against a team's budget "
                       "envelope. Returns ok / warn / over.",
        "input_schema": {
            "type": "object",
            "properties": {
                "team": {"type": "string"},
                "monthly_estimate_usd": {"type": "number"},
            },
            "required": ["team", "monthly_estimate_usd"],
            "additionalProperties": False,
        },
    },
    {
        "name": "submit_for_review",
        "description": "Terminal step. Runs the policy gate and renders a pull "
                       "request (never a direct apply). Call this once the plan is "
                       "right-sized and budget-checked and the user has confirmed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "intent": _INTENT_SCHEMA,
                "team": {"type": "string"},
                "approval_label": {
                    "type": "boolean",
                    "description": "Set only if a human approved an over-budget or "
                                   "GPU request out of band.",
                },
            },
            "required": ["intent", "team"],
            "additionalProperties": False,
        },
    },
]


def _intent_from(d: dict) -> Intent:
    return Intent(
        kind=d["kind"],
        environment=d.get("environment", "staging"),
        size_gb=int(d.get("size_gb", 20)),
        latency_sensitive=bool(d.get("latency_sensitive", False)),
        bursty=bool(d.get("bursty", False)),
        stateless=bool(d.get("stateless", True)),
        name=d.get("name", d["kind"]),
    )


def dispatch(name: str, tool_input: dict) -> dict:
    """Execute a tool call and return a JSON-serializable result."""
    if name == "list_golden_paths":
        return {"catalog": pipeline.catalog_summary()}

    if name == "right_size":
        sizing = right_size(_intent_from(tool_input))
        return asdict(sizing)

    if name == "estimate_cost":
        intent = _intent_from(tool_input)
        sizing = right_size(intent)
        return asdict(estimate_cost(sizing, intent.kind))

    if name == "check_budget":
        res = check_budget(tool_input["team"], float(tool_input["monthly_estimate_usd"]))
        return asdict(res)

    if name == "submit_for_review":
        intent = _intent_from(tool_input["intent"])
        return pipeline.run(
            intent,
            tool_input["team"],
            approval_label=bool(tool_input.get("approval_label", False)),
            open_pr=tool_input.get("open_pr", False),
        )

    return {"error": f"unknown tool: {name}"}
