"""The deterministic provisioning pipeline: intent -> right-size -> cost ->
budget -> policy -> rendered PR. This is the single source of truth; the LLM's
job is only to produce the Intent + team, never to bypass these steps.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import asdict

from .budget import check as check_budget
from .catalog import CATALOG, Intent, right_size
from .cost import estimate as estimate_cost
from .render import PolicyResult, render, run_policy, build_request


def run(intent: Intent, team: str, approval_label: bool = False,
        open_pr: bool = False, request_id: str | None = None) -> dict:
    request_id = request_id or f"{intent.name}-{uuid.uuid4().hex[:8]}"
    sizing = right_size(intent)
    cost = estimate_cost(sizing, intent.kind)
    budget = check_budget(team, cost.monthly_usd)
    req = build_request(intent, sizing, budget, approval_label)
    policy: PolicyResult = run_policy(req)
    outputs = render(intent, sizing, cost, budget, policy, request_id, open_pr=open_pr)
    return {
        "request_id": request_id,
        "intent": asdict(intent),
        "sizing": asdict(sizing),
        "cost": asdict(cost),
        "budget": asdict(budget),
        "policy": asdict(policy),
        "outputs": outputs,
    }


# --- Offline intent classifier -------------------------------------------
# A keyword heuristic so the whole pipeline is demonstrable without Bedrock.

_KIND_WORDS = {
    "database": ["database", "db", "postgres", "mysql", "rds", "sql"],
    "storage": ["bucket", "s3", "object store", "storage", "blob"],
    "service": ["service", "api", "app", "container", "ecs", "microservice", "worker"],
}


def classify(text: str, team: str) -> tuple[Intent, str]:
    """Best-effort parse of a free-text request into an Intent (offline mode)."""
    t = text.lower()

    # GPU/accelerated intent is detected first: a GPU request is a compute
    # service regardless of any incidental "storage" word, and it must reach the
    # approval guardrail rather than being silently classified as a bucket.
    gpu = any(w in t for w in
              ["gpu", "cuda", "a100", "h100", "accelerat", "training",
               "fine-tune", "fine tune", "finetune"])

    kind = "service"
    if not gpu:
        for k, words in _KIND_WORDS.items():
            if any(w in t for w in words):
                kind = k
                break

    environment = "staging"
    for env in ("prod", "production", "staging", "stage", "dev", "development"):
        if env in t:
            environment = {"production": "prod", "stage": "staging",
                           "development": "dev"}.get(env, env)
            break

    size_gb = 20
    # Terabytes first (e.g. "2TB", "2 tb", "2 terabytes"); a bare number joined
    # to the unit ("2tb") has no word boundary, so match the digits directly.
    m_tb = re.search(r"(\d+)\s*(tb|tib|terabytes?)\b", t)
    m_gb = re.search(r"(\d+)\s*(gb|gib|g\b)", t)
    if m_tb:
        size_gb = int(m_tb.group(1)) * 1000
    elif m_gb:
        size_gb = int(m_gb.group(1))

    # Negation-aware: "not latency critical" / "not latency-sensitive" means NOT sensitive.
    _neg_latency = any(p in t for p in
                       ["not latency", "no latency", "latency tolerant",
                        "latency-tolerant", "not real-time", "not realtime"])
    latency_sensitive = (not _neg_latency) and any(
        w in t for w in ["latency", "low-latency", "real-time", "realtime",
                         "latency-sensitive", "latency sensitive"])
    bursty = any(w in t for w in ["bursty", "burst", "spiky", "daytime", "intermittent"])
    stateless = "stateful" not in t

    name = re.sub(r"[^a-z0-9-]+", "-",
                  (re.search(r"for (?:a |an |the )?([a-z0-9 -]{3,30})", t) or
                   re.match(r"", "")).group(1) if re.search(r"for ", t) else kind
                  ).strip("-")[:30] or kind

    intent = Intent(
        kind=kind, environment=environment, size_gb=size_gb,
        latency_sensitive=latency_sensitive, bursty=bursty,
        stateless=stateless, gpu=gpu, name=name,
    )
    return intent, team


def catalog_summary() -> list[dict]:
    return [{"kind": k, **v} for k, v in CATALOG.items()]
