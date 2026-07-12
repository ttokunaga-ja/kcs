.PHONY: check
check:
	python3 cas_preexisting_corrupt_slot_poc.py | tee .actual-output.txt
	diff -u expected-output.txt .actual-output.txt

.PHONY: clean
clean:
	rm -f .actual-output.txt
