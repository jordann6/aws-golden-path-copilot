"""The Bedrock tool-use loop.

The model is a translation and advisory layer only: it maps a fuzzy request onto
the golden-path catalog, argues the right-sized (cheapest-that-fits) parameters,
checks the budget, and submits for review. All determinism lives in the tools.
"""
from __future__ import annotations

import json

from . import tools
from .bedrock_client import get_client, model_id
from .config import MAX_TOKENS

SYSTEM_PROMPT = """\
You are a platform-engineering provisioning copilot. A developer describes a \
resource they need in plain language; you turn it into a right-sized, \
budget-checked, policy-gated pull request.

Rules:
- You never write Terraform or invent instance types or prices. You only call \
the provided tools, which wrap vetted golden-path modules and real cost/budget \
data.
- Always start by calling list_golden_paths, then right_size, then \
estimate_cost, then check_budget.
- Bias every choice toward the cheapest option that still fits the stated \
workload: Graviton over x86, burstable for bursty non-critical workloads, spot \
for non-prod stateless services, auto-stop for non-prod, gp3 over gp2. The \
right_size tool already encodes this; surface its rationale to the user.
- Before calling submit_for_review, present the plan to the user in a few lines: \
the chosen module, the monthly cost, the budget verdict, and the key \
right-sizing decisions. Then submit.
- If the request is over budget or asks for a GPU, say so plainly and explain \
that it needs an approval label; do not set approval_label yourself.
- Keep responses concise and concrete.
"""


def run(user_text: str, team: str, auto_submit: bool = True,
        max_iterations: int = 8) -> dict:
    """Run one request end to end. Returns the transcript and any submit result."""
    client = get_client()
    messages = [{
        "role": "user",
        "content": f"[team={team}] {user_text}",
    }]
    submit_result = None
    final_text = ""

    for _ in range(max_iterations):
        resp = client.messages.create(
            model=model_id(),
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=tools.TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            final_text = "".join(
                b.text for b in resp.content if getattr(b, "type", "") == "text"
            )
            break

        tool_results = []
        for block in resp.content:
            if getattr(block, "type", "") != "tool_use":
                continue
            # Inject the team so the model can't misattribute spend.
            payload = dict(block.input)
            if block.name in ("check_budget", "submit_for_review"):
                payload.setdefault("team", team)
            result = tools.dispatch(block.name, payload)
            if block.name == "submit_for_review":
                submit_result = result
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })
        messages.append({"role": "user", "content": tool_results})

    return {"final_text": final_text, "submit_result": submit_result}
