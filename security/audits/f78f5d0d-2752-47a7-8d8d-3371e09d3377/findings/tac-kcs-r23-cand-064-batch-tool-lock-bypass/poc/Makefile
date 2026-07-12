.PHONY: run

KCS_REPO ?= .
EXPECT ?= vulnerable

run:
	python3 batch_tool_lock_probe.py --repo "$(KCS_REPO)" --expect "$(EXPECT)"
