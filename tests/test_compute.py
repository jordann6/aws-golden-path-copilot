"""Hardened-compute + multi-region tests: classification, the policy gate
re-checking the hardening posture, and region-aware cost."""
from copilot import pipeline
from copilot.catalog import Intent, right_size
from copilot.cost import estimate
from copilot.render import build_request, run_policy


def test_classifier_maps_hardened_ec2_to_compute():
    intent, _ = pipeline.classify(
        "a hardened EC2 bastion for staging behind Palo Alto, 30GB", "checkout"
    )
    assert intent.kind == "compute"
    assert intent.environment == "staging"


def test_classifier_parses_region():
    intent, _ = pipeline.classify(
        "a hardened EC2 host in eu-central-1 for staging", "checkout"
    )
    assert intent.region == "eu-central-1"


def test_classifier_defaults_region_to_us_east_1():
    intent, _ = pipeline.classify("a hardened EC2 host for staging", "checkout")
    assert intent.region == "us-east-1"


def test_compute_request_passes_the_gate():
    intent, team = pipeline.classify(
        "hardened EC2 bastion for staging, 30GB", "checkout"
    )
    result = pipeline.run(intent, team)
    assert result["sizing"]["module"] == "ec2"
    assert result["policy"]["passed"] is True


def test_gate_blocks_a_tampered_soft_host():
    # A hand-edited request that turns off the hardening must be denied by every
    # relevant rule (defence in depth over the copilot's own construction).
    intent = Intent(kind="compute", environment="staging", size_gb=30, name="evil")
    sizing = right_size(intent)
    from copilot.budget import check as check_budget
    from copilot.cost import estimate as est
    budget = check_budget("checkout", est(sizing, "compute").monthly_usd)
    req = build_request(intent, sizing, budget)
    req.update({"public_ip": True, "imdsv2": False,
                "firewall_inspected": False, "hardened_ami": False})
    policy = run_policy(req)
    assert policy.passed is False
    joined = " ".join(policy.violations)
    assert "public IP" in joined
    assert "IMDSv2" in joined
    assert "firewall" in joined
    assert "hardened" in joined


def test_region_pricing_scales_cost():
    intent = Intent(kind="compute", environment="staging", size_gb=30, name="host")
    sizing = right_size(intent)
    base = estimate(sizing, "compute", region="us-east-1")
    pricey = estimate(sizing, "compute", region="sa-east-1")  # 1.28x multiplier
    assert pricey.monthly_usd > base.monthly_usd
    assert pricey.region == "sa-east-1"
    assert any("regional pricing" in line for line in pricey.breakdown)


def test_unknown_region_falls_back_to_base_and_flags_it():
    intent = Intent(kind="compute", environment="staging", size_gb=30, name="host")
    sizing = right_size(intent)
    est_out = estimate(sizing, "compute", region="us-gov-west-1")
    assert any("not in the price table" in line for line in est_out.breakdown)
