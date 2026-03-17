"""
test_server.py — Smoke tests for GitUML MCP server tools
=========================================================
Imports and calls each server tool directly (no MCP transport needed).
Run from the gituml/ directory:

    python test_server.py

By default tests run against a small public Spring Boot repo.
Set TEST_REPO env var to override with a local path or different URL.

    TEST_REPO=C:/projects/my-app python test_server.py
"""

import os
import sys
import traceback
import tempfile
import textwrap
from pathlib import Path

# ── Allow running from the gituml/ project root ───────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from server import (
    analyze_repo,
    generate_class_diagram,
    generate_component_diagram,
    generate_sequence_diagram,
    generate_flowchart,
    generate_all,
)

# ── Config ────────────────────────────────────────────────────────────────────

# Override with TEST_REPO env var, or edit this default
DEFAULT_REPO = "https://github.com/scanurag/FoodFrenzy"
TEST_REPO    = os.environ.get("TEST_REPO", DEFAULT_REPO)

# Use a temp dir so test output doesn't pollute the project
OUTPUT_DIR = tempfile.mkdtemp(prefix="gituml_test_")

SEPARATOR = "=" * 60


# ── Helpers ───────────────────────────────────────────────────────────────────

def header(title: str) -> None:
    print(f"\n{SEPARATOR}")
    print(f"  TEST: {title}")
    print(SEPARATOR)


def truncate(text: str, lines: int = 15) -> str:
    """Show the first N lines plus a count of remaining lines."""
    all_lines = text.splitlines()
    preview   = "\n".join(all_lines[:lines])
    remaining = len(all_lines) - lines
    if remaining > 0:
        preview += f"\n  … ({remaining} more lines)"
    return preview


def run_test(name: str, fn, *args, **kwargs) -> bool:
    """
    Run a single test function. Returns True on success, False on failure.
    Prints a short preview of the result on success.
    """
    header(name)
    try:
        result = fn(*args, **kwargs)
        if result:
            print(truncate(str(result)))
        else:
            print("  ⚠️  Empty result returned.")
        print(f"\n  ✅  PASSED: {name}")
        return True
    except Exception:
        print(f"\n  ❌  FAILED: {name}")
        traceback.print_exc()
        return False


# ── Test cases ────────────────────────────────────────────────────────────────

def test_analyze_repo() -> bool:
    return run_test(
        "analyze_repo",
        analyze_repo,
        repo=TEST_REPO,
    )


def test_generate_class_diagram_return() -> bool:
    """Return as string (no output_dir)."""
    return run_test(
        "generate_class_diagram — return as string",
        generate_class_diagram,
        repo=TEST_REPO,
        format="mermaid",
        max_classes=20,
    )


def test_generate_class_diagram_write() -> bool:
    """Write to file."""
    return run_test(
        "generate_class_diagram — write to file",
        generate_class_diagram,
        repo=TEST_REPO,
        output_dir=OUTPUT_DIR,
        format="both",
        max_classes=20,
    )


def test_generate_component_diagram() -> bool:
    return run_test(
        "generate_component_diagram",
        generate_component_diagram,
        repo=TEST_REPO,
        format="mermaid",
    )


def test_generate_sequence_diagram() -> bool:
    return run_test(
        "generate_sequence_diagram",
        generate_sequence_diagram,
        repo=TEST_REPO,
        format="mermaid",
    )


def test_generate_flowchart() -> bool:
    return run_test(
        "generate_flowchart",
        generate_flowchart,
        repo=TEST_REPO,
        format="mermaid",
    )


def test_generate_all() -> bool:
    return run_test(
        "generate_all",
        generate_all,
        repo=TEST_REPO,
        output_dir=OUTPUT_DIR,
        format="both",
    )


def test_output_files_exist() -> bool:
    """Verify that generate_all actually wrote the expected files."""
    header("output files exist after generate_all")
    expected = [
        "class_diagram.md",
        "component_diagram.md",
        "sequence_diagram.md",
        "flowchart.md",
    ]
    all_ok = True
    for fname in expected:
        fpath = Path(OUTPUT_DIR) / fname
        exists = fpath.exists() and fpath.stat().st_size > 0
        status = "✅" if exists else "❌"
        print(f"  {status}  {fname}  ({fpath.stat().st_size} bytes)" if exists
              else f"  {status}  {fname}  MISSING")
        if not exists:
            all_ok = False

    if all_ok:
        print(f"\n  ✅  PASSED: all output files present in {OUTPUT_DIR}")
    else:
        print(f"\n  ❌  FAILED: some output files missing")
    return all_ok


# ── Runner ────────────────────────────────────────────────────────────────────

def main() -> None:
    print(SEPARATOR)
    print("  GitUML — Server Smoke Tests")
    print(SEPARATOR)
    print(f"  Repo       : {TEST_REPO}")
    print(f"  Output dir : {OUTPUT_DIR}")
    print(SEPARATOR)

    tests = [
        test_analyze_repo,
        test_generate_class_diagram_return,
        test_generate_class_diagram_write,
        test_generate_component_diagram,
        test_generate_sequence_diagram,
        test_generate_flowchart,
        test_generate_all,
        test_output_files_exist,
    ]

    results = [t() for t in tests]

    passed = sum(results)
    failed = len(results) - passed

    print(f"\n{SEPARATOR}")
    print(f"  Results: {passed}/{len(results)} passed", end="")
    if failed:
        print(f"  |  {failed} FAILED ❌")
    else:
        print("  — all green ✅")
    print(SEPARATOR)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
