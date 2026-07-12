PYTHON ?= python3
KCS_BIN ?= kcs

.PHONY: dry-run run

dry-run:
	$(PYTHON) -m py_compile unrecognized_binary_visibility_poc.py

run:
	$(PYTHON) unrecognized_binary_visibility_poc.py --kcs-bin "$(KCS_BIN)"
