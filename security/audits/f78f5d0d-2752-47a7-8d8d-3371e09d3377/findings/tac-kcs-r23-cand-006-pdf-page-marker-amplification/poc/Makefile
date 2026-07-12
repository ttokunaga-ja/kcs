.PHONY: run test

run:
	python3 pdf_page_marker_probe.py --markers 64

test:
	python3 pdf_page_marker_probe.py --markers 1 --max-allocate 8
	python3 pdf_page_marker_probe.py --markers 4 --max-allocate 8
	python3 pdf_page_marker_probe.py --markers 16 --max-allocate 32
	python3 pdf_page_marker_probe.py --markers 64 --max-allocate 128
