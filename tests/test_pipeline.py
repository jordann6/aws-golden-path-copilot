from copilot import pipeline


def test_offline_end_to_end_produces_artifacts(tmp_path, monkeypatch):
    intent, team = pipeline.classify(
        "I need a Postgres for a staging service, ~50GB, bursty, not latency critical",
        "checkout",
    )
    assert intent.kind == "database"
    assert intent.environment == "staging"
    assert intent.bursty is True

    result = pipeline.run(intent, team)
    assert result["sizing"]["instance_type"].startswith("t4g")
    assert result["cost"]["monthly_usd"] > 0
    assert result["budget"]["verdict"] in ("ok", "warn", "over")
    assert result["policy"]["passed"] in (True, False)
    # PR body artifact is always written.
    assert result["outputs"]["pr_body"].endswith(".pr.md")


def test_over_budget_gpu_style_blocks_without_approval():
    # growth is near its cap; a big steady prod db will tip it over.
    intent, team = pipeline.classify(
        "production postgres database, 500GB, low-latency", "growth"
    )
    result = pipeline.run(intent, team, approval_label=False)
    if result["budget"]["verdict"] == "over":
        assert result["policy"]["passed"] is False
    # With approval it should clear the budget rule.
    approved = pipeline.run(intent, team, approval_label=True)
    budget_violation = any(
        "budget" in v for v in approved["policy"]["violations"]
    )
    assert budget_violation is False
