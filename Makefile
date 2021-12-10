# COCOTB variables
export COCOTB_REDUCED_LOG_FMT=1
export PYTHONPATH := test:$(PYTHONPATH)
export LIBPYTHON_LOC=$(shell cocotb-config --libpython)

all: test_caravel_bus

test_caravel_bus:
	rm -rf sim_build/ results.xml
	mkdir sim_build/
	iverilog -o sim_build/sim.vvp -s generator -s dump -g2012 src/generator.v test/dump_generator.v
	PYTHONOPTIMIZE=${NOASSERT} MODULE=test_caravel_bus vvp -M $$(cocotb-config --prefix)/cocotb/libs -m libcocotbvpi_icarus sim_build/sim.vvp
	! grep failure results.xml

show_%: %.vcd %.gtkw
	gtkwave $^

lint:
	verible-verilog-lint src/*v --rules_config verible.rules

clean:
	rm -rf *vcd sim_build test/__pycache__ results.xml

.PHONY: clean
