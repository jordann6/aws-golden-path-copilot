"""Amazon Bedrock client.

Uses the standard Anthropic Bedrock client so credentials come from the AWS
chain (IAM role / profile / env) with no Anthropic API key. Region and model id
come from config. Bedrock ids carry the `anthropic.` prefix; the newer models
are invoked through a cross-region inference profile (e.g.
`us.anthropic.claude-sonnet-4-6`), which the client accepts as the model id.
"""
from __future__ import annotations

from . import config


def get_client():
    """Return an AnthropicBedrock client, or raise a clear error."""
    try:
        from anthropic import AnthropicBedrock
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "anthropic SDK not installed. `pip install -r requirements.txt`"
        ) from e
    return AnthropicBedrock(aws_region=config.AWS_REGION)


def model_id() -> str:
    m = config.BEDROCK_MODEL
    # Accept either a base id (`anthropic.claude-...`) or a region-prefixed
    # inference profile (`us.anthropic.claude-...`). Only bare model names get
    # the `anthropic.` prefix added.
    if "anthropic." not in m:
        m = f"anthropic.{m}"
    return m
