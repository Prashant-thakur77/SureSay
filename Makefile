.PHONY: setup test test-web demo pair eval eval-twice report latency safety deploy teardown smoke lint

PY := .venv/bin/python

setup:            ## Python 3.13 venv with every extra, and the web client's packages
	uv venv -q --python 3.13 .venv
	uv pip install -q --python .venv -e ".[whisper,dev]"
	cd web && npm ci

test:             ## Gate, hub and safety-suite tests (offline)
	cd packages/confirm-gate-mcp && ../../$(PY) -m pytest -q
	$(PY) -m pytest -q

test-web:
	cd web && npm run typecheck && npm test

demo:             ## Hub + web client (+ agent when Bedrock is reachable) on http://127.0.0.1:9000
	bash scripts/demo.sh

pair:             ## A fresh pairing code for the demo user
	$(PY) -m suresay.cli pair

eval:             ## Every claim, once, into eval/results/run1 (needs data/torgo; see eval/README.md)
	$(PY) eval/torgo_prepare.py
	$(PY) eval/tune_abstain.py
	$(PY) eval/run_confirm_eval.py --run run1
	$(PY) eval/run_intent_eval.py --run run1
	$(PY) eval/run_safety_suite.py --run run1
	$(PY) eval/latency.py --run run1

eval-twice: eval  ## The same again into run2, to show the numbers are stable
	$(PY) eval/run_confirm_eval.py --run run2
	$(PY) eval/run_intent_eval.py --run run2
	$(PY) eval/run_safety_suite.py --run run2
	$(PY) eval/latency.py --run run2

report:           ## Regenerate eval/REPORT.md from eval/results
	$(PY) eval/make_report.py

safety:
	$(PY) eval/run_safety_suite.py

deploy:           ## Everything on AWS (us-east-1)
	bash infra/deploy.sh

teardown:
	bash infra/teardown.sh

smoke:            ## End-to-end check of the deployed hub
	$(PY) infra/smoke.py $$(grep HUB_URL infra/.state/outputs.env | cut -d= -f2)

lint:
	.venv/bin/ruff check suresay mcp_server strands_agent eval infra packages/confirm-gate-mcp/src

oss-sync:         ## Publish packages/confirm-gate-mcp to its own repository (history preserved)
	git branch -D oss-split 2>/dev/null || true
	git subtree split --prefix=packages/confirm-gate-mcp -b oss-split
	git push https://github.com/Prashant-thakur77/confirm-gate-mcp.git oss-split:main
