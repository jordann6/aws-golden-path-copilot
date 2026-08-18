from copilot.catalog import Intent, right_size


def test_bursty_nonprod_gets_burstable_graviton_and_autostop():
    s = right_size(Intent(kind="database", environment="staging", size_gb=50,
                          bursty=True, latency_sensitive=False, name="orders"))
    assert s.instance_type.startswith("t4g")
    assert s.auto_stop is True
    assert s.storage_class == "gp3"


def test_prod_db_gets_hardening():
    s = right_size(Intent(kind="database", environment="prod", size_gb=200,
                          latency_sensitive=True, name="orders"))
    assert s.deletion_protection is True
    assert s.multi_az is True
    assert s.min_capacity == 2
    assert s.auto_stop is False


def test_nonprod_stateless_service_uses_spot():
    s = right_size(Intent(kind="service", environment="dev", size_gb=0,
                          stateless=True, name="api"))
    assert s.use_spot is True


def test_prod_service_no_spot():
    s = right_size(Intent(kind="service", environment="prod", size_gb=0,
                          stateless=True, name="api"))
    assert s.use_spot is False


def test_storage_kind_picks_s3():
    s = right_size(Intent(kind="storage", environment="dev", size_gb=500, name="assets"))
    assert s.module == "s3-bucket"
    assert s.storage_class == "s3_standard"
