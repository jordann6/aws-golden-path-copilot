"""Amazon Bedrock client.

Uses the Messages-API Bedrock (Mantle) client so credentials come from the AWS
chain (IAM role / profile / env) with no Anthropic API key. Region and model id
come from config. Bedrock model ids carry the `anthropic.` prefix.
"""
from __future__ import annotations

from . import config


def get_client():
    """Return an AnthropicBedrockMantle client, or raise a clear error."""
    try:
        from anthropic import AnthropicBedrockMantle
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "anthropic SDK not installed. `pip install -r requirements.txt`"
        ) from e
    return AnthropicBedrockMantle(aws_region=config.AWS_REGION)


def model_id() -> str:
    m = config.BEDROCK_MODEL
    # Guard against a first-party id being passed for Bedrock.
    if not m.startswith("anthropic."):
        m = f"anthropic.{m}"
    return m
