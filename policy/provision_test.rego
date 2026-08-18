package provision

import rego.v1

# A fully-valid request the gate must pass. Each failing fixture below starts
# from this base and breaks exactly one thing, so every deny rule is proven to
# fire (and this base proves they don't fire spuriously).
base_request := {
	"kind": "database",
	"environment": "prod",
	"module": "rds",
	"instance_type": "m7g.large",
	"encrypted": true,
	"deletion_protection": true,
	"gpu": false,
	"approval_label": false,
	"budget_verdict": "ok",
	"tags": {"CostCenter": "CC-1001", "Owner": "team@example.com", "Environment": "prod"},
}

test_base_passes if {
	count(deny) == 0 with input as base_request
}

test_missing_tag_denied if {
	req := json.remove(base_request, ["tags/Owner"])
	count(deny) > 0 with input as req
}

test_unencrypted_denied if {
	req := object.union(base_request, {"encrypted": false})
	count(deny) > 0 with input as req
}

test_gpu_without_approval_denied if {
	req := object.union(base_request, {"gpu": true})
	count(deny) > 0 with input as req
}

test_gpu_with_approval_allowed if {
	req := object.union(base_request, {"gpu": true, "approval_label": true})
	count(deny) == 0 with input as req
}

test_over_budget_denied if {
	req := object.union(base_request, {"budget_verdict": "over"})
	count(deny) > 0 with input as req
}

test_over_budget_with_approval_allowed if {
	req := object.union(base_request, {"budget_verdict": "over", "approval_label": true})
	count(deny) == 0 with input as req
}

test_prod_db_without_deletion_protection_denied if {
	req := object.union(base_request, {"deletion_protection": false})
	count(deny) > 0 with input as req
}
