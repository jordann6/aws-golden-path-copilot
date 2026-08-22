package provision

# Policy gate for self-service provisioning requests. Evaluated against the
# JSON request the copilot renders (see copilot/render.py -> build_request).
#
# `deny` is a set of human-readable violation strings. An empty set means the
# request passes the gate. Every rule below is independently fireable and has a
# matching fixture in provision_test.rego (guarding against vacuous policy).

import rego.v1

required_tags := {"CostCenter", "Owner", "Environment"}

# --- Tagging ---------------------------------------------------------------

deny contains msg if {
	some tag in required_tags
	not input.tags[tag]
	msg := sprintf("missing required tag: %s", [tag])
}

# --- Encryption ------------------------------------------------------------

deny contains msg if {
	input.kind != "service"
	input.encrypted == false
	msg := "storage must be encrypted at rest"
}

# --- GPU / oversized instances need an approval label ----------------------

deny contains msg if {
	input.gpu == true
	not input.approval_label
	msg := "GPU instances require an approval label"
}

# --- Budget gate -----------------------------------------------------------

deny contains msg if {
	input.budget_verdict == "over"
	not input.approval_label
	msg := "request is over the team budget and needs an approval label"
}

# --- Production hardening ---------------------------------------------------

deny contains msg if {
	input.environment == "prod"
	input.kind == "database"
	input.deletion_protection == false
	msg := "production databases must have deletion protection enabled"
}

# --- Hardened compute (EC2 golden path) ------------------------------------
# A compute request must be a private, IMDSv2-only, firewall-inspected host
# launched from a CIS-hardened AMI. The copilot sets these by construction; the
# gate re-checks them so a hand-edited request cannot smuggle a soft host in.

deny contains msg if {
	input.kind == "compute"
	input.public_ip == true
	msg := "compute instances must not have a public IP (private subnet + SSM only)"
}

deny contains msg if {
	input.kind == "compute"
	input.imdsv2 == false
	msg := "compute instances must require IMDSv2"
}

deny contains msg if {
	input.kind == "compute"
	input.firewall_inspected == false
	msg := "compute egress must be routed through the shared firewall for inspection"
}

deny contains msg if {
	input.kind == "compute"
	input.hardened_ami == false
	msg := "compute must launch from a hardened (CIS) golden AMI"
}

# Convenience rule: overall pass/fail.
allow if count(deny) == 0
