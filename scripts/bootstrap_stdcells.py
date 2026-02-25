#!/usr/bin/env python
import argparse
import os

from src.tools.stdcells import bootstrap_stdcells


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap managed stdcell simulation models from pinned upstream sources")
    parser.add_argument("--workspace", required=True, help="Workspace path where _stdcells cache will be created")
    parser.add_argument("--platform", required=True, choices=["asap7", "sky130hd"], help="Target platform")
    parser.add_argument("--image", default="openroad/orfs:latest", help="Deprecated (kept for CLI compatibility; ignored in pinned-only mode)")
    args = parser.parse_args()

    workspace = os.path.abspath(args.workspace)
    os.makedirs(workspace, exist_ok=True)

    result = bootstrap_stdcells(workspace=workspace, platform=args.platform, image=args.image)
    print(f"Bootstrapped stdcells for {result['platform']}")
    print(f"Cache: {result['cache_dir']}")
    print(f"Files: {result['file_count']}")
    print(f"Manifest: {result['manifest']}")


if __name__ == "__main__":
    main()
