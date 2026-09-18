from copilot import reclaim


def _finding(rtype, cc="cc-1001", cost=10.0, rid="vol-1", region="us-east-1"):
    tags = {"CostCenter": cc} if cc else {}
    return reclaim.WasteFinding(rtype, rid, region, cost, "reason", tags)


def test_untagged_waste_is_held():
    # Gate 1: no CostCenter means a human decides, even for a safe action.
    r = reclaim.plan(_finding("gp2_volume", cc=""))
    assert r.blocked is True
    assert "CostCenter" in r.blocked_reason


def test_gp2_migration_is_non_destructive_and_actionable():
    r = reclaim.plan(_finding("gp2_volume"))
    assert r.destructive is False
    assert r.blocked is False
    assert any("gp3" in c for c in r.commands)


def test_delete_volume_is_destructive():
    r = reclaim.plan(_finding("unattached_ebs"))
    assert r.destructive is True
    assert any("delete-volume" in c for c in r.commands)


def test_destructive_held_without_approval_then_released_with_it():
    # Gate 2: destructive actions wait for an approval label.
    src = None  # uses the bundled fixture
    held = reclaim.build(src, approval_label=False)
    destructive_actionable = [r for r in held if r.destructive and not r.blocked]
    assert destructive_actionable == []

    approved = reclaim.build(src, approval_label=True)
    # The two tagged destructive findings clear; the untagged one stays held.
    assert any(r.destructive and not r.blocked for r in approved)
    assert any(r.blocked and "CostCenter" in r.blocked_reason for r in approved)


def test_render_writes_pr_and_script_and_sums_savings(tmp_path, monkeypatch):
    monkeypatch.setattr(reclaim.config, "OUT_DIR", tmp_path)
    rems = reclaim.build(None, approval_label=True)
    result = reclaim.render(rems)
    assert result["pr_body"].endswith(".pr.md")
    assert result["script"].endswith(".sh")
    assert result["monthly_savings_usd"] > 0
    # The fixture's untagged $12 volume is never counted as reclaimable.
    assert result["held"] >= 1
    body = (tmp_path / f"{result['request_id']}.pr.md").read_text()
    assert "Reclaim idle spend" in body
