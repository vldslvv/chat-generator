.DEFAULT_GOAL := help

# Resolve paths relative to this Makefile, including when invoked with make -f.
REPO_ROOT := $(shell dirname -- "$(MAKEFILE_LIST)")

# Identify an implementation explicitly for trace and scoped cleanup.
IMPL ?=
TRACE_INTERVAL ?= 5
OFFLINE_CONFIG ?= apps/chat/offline-delivery.json
export IMPL TRACE_INTERVAL OFFLINE_CONFIG
EVAL_AGENT_TIMEOUT ?= 1800
EVAL_COMMAND_TIMEOUT ?= 60
SPEC_BUNDLE ?=
SPECS_MODEL ?= gpt-6-astra
SPECS_REASONING ?= medium
SPECS_TIMEOUT ?= 1800
WORKFLOW_TIMEOUT ?= 1800
WORKFLOW_MODEL ?= gpt-6-astra
WORKFLOW_REASONING ?= medium

.PHONY: help eval eval-workflow eval-specs trace cleanup clean clean-runs clean-tasks

help:
	@echo "make test-offline-delivery  Check queued delivery with both client language assignments"
	@echo "make demo-offline-delivery  Play the offline scenario every 5s; w explains, q exits"
	@echo "make eval-specs    Report on current specs against bundle templates; no repairs"
	@echo "                       SPEC_BUNDLE=specs/todolist (default: all bundles)"
	@echo "                       SPECS_MODEL=gpt-6-astra SPECS_REASONING=medium SPECS_TIMEOUT=1800 (defaults)"
	@echo "make eval         Evaluate HEAD in a clean temporary worktree; retain reports under .agentic-workflow/evals/todolist-worktrees/"
	@echo "make eval-workflow  Review workflow documents once; automatically attempt one repair in working files"
	@echo "                       WORKFLOW_MODEL=gpt-6-astra WORKFLOW_REASONING=medium WORKFLOW_TIMEOUT=1800 (defaults)"
	@echo "                       FIXED means mechanical checks passed without independent re-review; partial edits may remain on failure"
	@echo "make trace        Live agent insights until Ctrl+C (IMPL=path required; optional TRACE_INTERVAL=5; restart to change interval)"
	@echo "make cleanup      Remove numbered execution records; retain project settings"
	@echo "make clean        Remove numbered execution records; retain project settings"
	@echo "make clean-runs   Remove runs/ under IMPL"
	@echo "make clean-tasks  Remove tasks/ under IMPL"

eval:
	@cd "$(REPO_ROOT)" && python3 -B evals/worktree.py --agent-timeout "$(EVAL_AGENT_TIMEOUT)" --command-timeout "$(EVAL_COMMAND_TIMEOUT)"

eval-workflow:
	@cd "$(REPO_ROOT)" && python3 -B evals/workflow.py --timeout "$(WORKFLOW_TIMEOUT)" --model "$(WORKFLOW_MODEL)" --reasoning "$(WORKFLOW_REASONING)"

eval-specs:
	@cd "$(REPO_ROOT)" && python3 -B evals/specs.py $(if $(SPEC_BUNDLE),--bundle "$(SPEC_BUNDLE)") --timeout "$(SPECS_TIMEOUT)" --model "$(SPECS_MODEL)" --reasoning "$(SPECS_REASONING)"

trace:
	@cd "$(REPO_ROOT)" && python3 agentic-workflow/helpers/trace_view.py "$${IMPL:?Set IMPL to an implementation directory}" "--interval=$$TRACE_INTERVAL"

cleanup:
	@cd "$(REPO_ROOT)" && rm -rf -- .agentic-workflow/records/[0-9]*_*

clean: cleanup

clean-runs:
	@cd "$(REPO_ROOT)" && rm -rf -- "$${IMPL:?IMPL must identify an implementation directory}/runs"

clean-tasks:
	@cd "$(REPO_ROOT)" && rm -rf -- "$${IMPL:?IMPL must identify an implementation directory}/tasks"

.PHONY: prepare-offline-delivery test-offline-delivery demo-offline-delivery

prepare-offline-delivery:
	@cd "$(REPO_ROOT)" && python3 tools/offline_delivery/configuration.py

test-offline-delivery: prepare-offline-delivery
	@cd "$(REPO_ROOT)" && uv run --frozen --project tools/offline_delivery pytest tools/offline_delivery -v

demo-offline-delivery: prepare-offline-delivery
	@cd "$(REPO_ROOT)" && python3 tools/offline_delivery/scenario.py
