KCS_REPO ?=

.PHONY: all
all:
	@if [ -z "$(KCS_REPO)" ]; then 		echo "Set KCS_REPO to a checkout containing the target revision" >&2; 		exit 2; 	fi
	KCS_REPO="$(KCS_REPO)" python3 check_destination_confusion.py
