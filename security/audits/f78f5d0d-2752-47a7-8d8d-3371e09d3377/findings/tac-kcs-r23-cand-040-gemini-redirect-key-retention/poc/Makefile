.PHONY: check

SOURCE_ROOT ?= .
UREQ_SRC ?=

check:
	python3 check_redirect_key_retention.py --source-root "$(SOURCE_ROOT)" $(if $(UREQ_SRC),--ureq-src "$(UREQ_SRC)")
