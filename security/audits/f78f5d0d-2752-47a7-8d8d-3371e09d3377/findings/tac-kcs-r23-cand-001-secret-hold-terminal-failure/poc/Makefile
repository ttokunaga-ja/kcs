.PHONY: run check clean

run:
	python3 secret_hold_terminal_failure_poc.py

check: run

clean:
	rm -f __pycache__/*.pyc
	rmdir __pycache__ 2>/dev/null || true
