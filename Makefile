# The MCP server is a separate repo. Build it once: (cd ../mcp-devplatform-guardrails && npm ci && npm run build)
# or point GUARDRAILS_SERVER at its dist/bin/server.js.
.PHONY: test eval eval-negative eval-live run
test:           ## unit + loop tests against the real server, scripted model (no API key)
	uv run pytest -q
eval:           ## positive control: the reference policy must pass every case
	uv run python -m evals.run --policy reference
eval-negative:  ## negative control: a reckless policy must be caught by the graders
	uv run python -m evals.run --policy reckless
eval-live:      ## real Claude on every case (needs ANTHROPIC_API_KEY; spends tokens)
	uv run python -m evals.run --live
run:            ## interactive: make run TASK="Plan upgrades for sample-node-api"
	uv run python -m agent "$(TASK)"
