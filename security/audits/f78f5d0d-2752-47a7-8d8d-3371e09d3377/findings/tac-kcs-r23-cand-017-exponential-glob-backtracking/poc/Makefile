.PHONY: all run clean

all: kcs-glob-backtracking-probe

kcs-glob-backtracking-probe: probe.rs
	rustc -O probe.rs -o kcs-glob-backtracking-probe

run: all
	./kcs-glob-backtracking-probe

clean:
	rm -f kcs-glob-backtracking-probe
