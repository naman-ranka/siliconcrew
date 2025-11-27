import os
import sys
import importlib.util

def check_path(path, is_dir=True):
    exists = os.path.isdir(path) if is_dir else os.path.isfile(path)
    status = "✅" if exists else "❌"
    print(f"{status} {path}")
    return exists

def check_import(module_name):
    try:
        importlib.import_module(module_name)
        print(f"✅ Import {module_name}")
        return True
    except ImportError as e:
        print(f"❌ Import {module_name}: {e}")
        return False

def main():
    print("Verifying Project Skeleton...")
    
    # 1. Check Directories
    dirs = [
        "src",
        "src/agents",
        "src/tools",
        "src/graph",
        "src/state",
        "workspace",
        "templates",
        "tests"
    ]
    all_dirs_ok = all(check_path(d) for d in dirs)

    # 2. Check Files
    files = [
        "src/__init__.py",
        "src/agents/__init__.py",
        "src/tools/__init__.py",
        "src/graph/__init__.py",
        "src/state/__init__.py",
        "requirements.txt",
        ".gitignore"
    ]
    all_files_ok = all(check_path(f, is_dir=False) for f in files)

    # 3. Check Python Environment
    print(f"ℹ️  Python Version: {sys.version.split()[0]}")
    imports_ok = check_import("langgraph") and check_import("pydantic")

    if all_dirs_ok and all_files_ok and imports_ok:
        print("\n🎉 Phase 1 Verification PASSED!")
        sys.exit(0)
    else:
        print("\n💥 Phase 1 Verification FAILED!")
        sys.exit(1)

if __name__ == "__main__":
    main()
