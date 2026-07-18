#!/usr/bin/env python
"""Fail loudly unless a stdcell bootstrap produced a complete cache.

Used by the Dockerfile bake step (and usable after any manual bootstrap).
``bootstrap_stdcells`` raises only when the cache is FULLY empty — partial
download failures are recorded in the manifest but do not fail the run — so
an image build must check the manifest explicitly or a thin bake would look
fixed while silently reintroducing the runtime fetch on every cold start.
"""
import argparse
import json
import os
import sys

# Expected pinned-model floors per platform (actual: asap7=7, sky130hd=622).
MIN_MODELS = {"asap7": 5, "sky130hd": 500}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify stdcell caches are complete")
    parser.add_argument("--workspace", required=True, help="Workspace root holding _stdcells/")
    args = parser.parse_args()

    ok = True
    for platform, minimum in MIN_MODELS.items():
        manifest_path = os.path.join(
            args.workspace, "_stdcells", platform, "sim", "manifest.json"
        )
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except (OSError, ValueError) as exc:
            print(f"FAIL {platform}: manifest unreadable: {exc}")
            ok = False
            continue
        failed = manifest.get("sources", {}).get("pinned_source", {}).get("failed", [])
        count = len(manifest.get("files", []))
        if failed:
            print(f"FAIL {platform}: {len(failed)} pinned download failure(s): {failed[:3]}")
            ok = False
        elif count < minimum:
            print(f"FAIL {platform}: only {count} models (expected >= {minimum})")
            ok = False
        else:
            print(f"OK {platform}: {count} models, no download failures")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
