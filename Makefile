.PHONY: help install test policy demo web fmt clean deploy destroy

TEAM ?= checkout
REQ  ?= I need a Postgres for a staging service, ~50GB, bursty daytime traffic, not latency critical

help:
	@echo "install   install python deps"
	@echo "test      run unit tests + OPA policy tests"
	@echo "policy    run the OPA policy tests only"
	@echo "demo      run the pipeline offline (no Bedrock)  REQ=... TEAM=..."
	@echo "online    run the Bedrock tool-use loop          REQ=... TEAM=..."
	@echo "web       serve the chat UI at :8000"
	@echo "clean     remove rendered artifacts"

install:
	pip install -r requirements.txt

test: policy
	pytest -q

policy:
	@if command -v opa >/dev/null 2>&1; then \
		opa test policy/ -v ; \
	else \
		echo "opa not installed; skipping rego tests (python fallback still gates)"; \
	fi

demo:
	python -m copilot "$(REQ)" --team $(TEAM) --offline

online:
	python -m copilot "$(REQ)" --team $(TEAM)

web:
	uvicorn web.app:app --reload

fmt:
	@command -v terraform >/dev/null 2>&1 && terraform fmt -recursive modules/ || true

clean:
	rm -f out/*.tfvars.json out/*.tf out/*.pr.md

# deploy/destroy operate on a rendered request dir (out/) once a PR is merged.
# They are intentionally manual: the copilot's output is a PR, not an apply.
deploy:
	@echo "Review the merged PR, then: cd out && terraform init && terraform apply"

destroy:
	@echo "cd out && terraform destroy"
