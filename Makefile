# SiliconCrew make targets.
#
# fetch-bundles: download the heavy example binaries (GDS/DEF/SPEF/RTLIL/webp)
# that live outside git, from the public templates bucket. Stdlib only, no cloud
# SDK. Source designs + run evidence already ship in the clone; this fills in the
# regenerable OpenROAD output. Idempotent — skips bundles already present.
.PHONY: fetch-bundles
fetch-bundles:
	python -m scripts.fetch_examples $(ARGS)
