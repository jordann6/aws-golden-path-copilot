"""Central paths and runtime configuration for the copilot."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
MODULES_DIR = ROOT / "modules"
POLICY_DIR = ROOT / "policy"
OUT_DIR = ROOT / "out"

COST_CENTERS_FILE = DATA_DIR / "cost-centers.yaml"
PRICES_FILE = DATA_DIR / "prices.yaml"

# Bedrock
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
# Default to Sonnet for the production path (cheaper per call, plenty for this
# intent-mapping + right-sizing work). Invoked through a cross-region inference
# profile; override BEDROCK_MODEL to another profile id for other models.
BEDROCK_MODEL = os.environ.get("BEDROCK_MODEL", "us.anthropic.claude-sonnet-4-6")
MAX_TOKENS = int(os.environ.get("COPILOT_MAX_TOKENS", "4096"))

# GitOps output
GITOPS_REPO = os.environ.get("GITOPS_REPO", "")  # owner/repo for `gh pr create`
