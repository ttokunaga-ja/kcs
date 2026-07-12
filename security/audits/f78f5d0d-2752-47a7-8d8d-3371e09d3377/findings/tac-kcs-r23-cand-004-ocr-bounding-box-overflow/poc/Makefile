RUSTC ?= rustc

.PHONY: all run clean

all: target/ocr_bbox_checked target/ocr_bbox_wrapping

target:
	@mkdir -p target

target/ocr_bbox_checked: ocr_bbox_overflow_probe.rs | target
	@$(RUSTC) -C overflow-checks=yes -o $@ $<

target/ocr_bbox_wrapping: ocr_bbox_overflow_probe.rs | target
	@$(RUSTC) -O -C overflow-checks=no -o $@ $<

run: all
	@echo "[checked build]"
	@./target/ocr_bbox_checked
	@echo "[wrapping build]"
	@./target/ocr_bbox_wrapping

clean:
	@rm -rf target
