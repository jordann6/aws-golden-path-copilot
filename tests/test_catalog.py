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


def test_gpu_intent_picks_accelerated_family_not_spot():
    s = right_size(Intent(kind="service", environment="staging", size_gb=0,
                          gpu=True, stateless=True, name="trainer"))
    # A g/p family instance is what build_request keys the GPU policy rule on.
    assert s.instance_type.startswith("g")
    # GPU jobs must not run on interruptible spot capacity.
    assert s.use_spot is False


def test_storage_kind_picks_s3():
    s = right_size(Intent(kind="storage", environment="dev", size_gb=500, name="assets"))
    assert s.module == "s3-bucket"
    assert s.storage_class == "s3_standard"


def test_compute_is_hardened_and_graviton():
    s = right_size(Intent(kind="compute", environment="staging", size_gb=30,
                          bursty=True, latency_sensitive=False, name="bastion"))
    assert s.module == "ec2"
    assert s.instance_type.startswith("t4g")  # Graviton, right-sized to bursty
    # Golden-path hardening posture is set by construction.
    assert s.public_ip is False
    assert s.imdsv2_required is True
    assert s.firewall_inspected is True
    assert s.hardened_ami is True
    # Hardened hosts are never put on interruptible spot capacity.
    assert s.use_spot is False
    assert s.params["ami_ssm_parameter"].endswith("al2023-cis")


def test_prod_compute_gets_two_hosts():
    s = right_size(Intent(kind="compute", environment="prod", size_gb=100,
                          latency_sensitive=True, name="app-host"))
    assert s.min_capacity == 2
    assert s.auto_stop is False
