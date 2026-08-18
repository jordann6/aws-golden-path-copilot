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

# Convenience rule: overall pass/fail.
allow if count(deny) == 0
