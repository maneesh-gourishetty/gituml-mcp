"""
GitUML — Java/Spring Boot UML & Diagram Generator
==================================================
Accepts a GitHub URL or local repo path and generates 4 diagram files
in Mermaid and/or PlantUML format.

Usage:
    # From a GitHub URL
    python main.py --repo https://github.com/spring-projects/spring-petclinic

    # From a local path
    python main.py --repo /path/to/your/spring-boot-project

    # With sequence diagram entry point
    python main.py --repo <url_or_path> \\
                   --entry-class UserController \\
                   --entry-method createUser

    # With method-level flowchart
    python main.py --repo <url_or_path> \\
                   --flow-class OrderService \\
                   --flow-method processOrder

    # Mermaid only, custom output directory
    python main.py --repo <url_or_path> --format mermaid --output-dir ./diagrams

Output (default: ./output/):
    output/class_diagram.md
    output/component_diagram.md
    output/sequence_diagram.md
    output/flowchart.md
"""

import sys
import logging
import argparse
import tempfile
import shutil
from pathlib import Path


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("gituml")


# ─────────────────────────────────────────────────────────────────────────────
# Argument parser
# ─────────────────────────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gituml",
        description="Generate UML diagrams from any Java / Spring Boot repository.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --repo https://github.com/spring-projects/spring-petclinic
  python main.py --repo C:\\projects\\my-spring-app
  python main.py --repo https://github.com/user/repo \\
                 --entry-class UserController --entry-method createUser \\
                 --format mermaid --output-dir ./diagrams
        """,
    )

    # ── Required ──────────────────────────────────────────────────────────────
    parser.add_argument(
        "--repo", "-r",
        required=True,
        metavar="URL_OR_PATH",
        help="GitHub/GitLab URL  OR  absolute/relative local path to the Java repo",
    )

    # ── Output ────────────────────────────────────────────────────────────────
    parser.add_argument(
        "--output-dir", "-o",
        default="output",
        metavar="DIR",
        help="Directory to write diagram files (default: ./output)",
    )
    parser.add_argument(
        "--format",
        choices=["both", "mermaid", "plantuml"],
        default="both",
        help="Output diagram format — mermaid, plantuml, or both (default: both)",
    )

    # ── Sequence diagram entry point ──────────────────────────────────────────
    parser.add_argument(
        "--entry-class", "-ec",
        default=None,
        metavar="CLASS_NAME",
        help="Class to use as entry point for the sequence diagram (e.g. UserController)",
    )
    parser.add_argument(
        "--entry-method", "-em",
        default=None,
        metavar="METHOD_NAME",
        help="Method to trace for the sequence diagram (e.g. createUser)",
    )

    # ── Flowchart target ──────────────────────────────────────────────────────
    parser.add_argument(
        "--flow-class", "-fc",
        default=None,
        metavar="CLASS_NAME",
        help="Class for method-level flowchart (defaults to --entry-class if omitted)",
    )
    parser.add_argument(
        "--flow-method", "-fm",
        default=None,
        metavar="METHOD_NAME",
        help="Method for method-level flowchart (defaults to --entry-method if omitted)",
    )

    # ── Behaviour flags ───────────────────────────────────────────────────────
    parser.add_argument(
        "--include-tests",
        action="store_true",
        default=False,
        help="Include test source directories in parsing (excluded by default)",
    )
    parser.add_argument(
        "--max-classes",
        type=int,
        default=60,
        metavar="N",
        help="Maximum number of classes to include in the class diagram (default: 60)",
    )

    return parser


# ─────────────────────────────────────────────────────────────────────────────
# Repo resolution
# ─────────────────────────────────────────────────────────────────────────────

def is_git_url(value: str) -> bool:
    """Return True if the value looks like a remote Git URL."""
    return value.startswith(("http://", "https://", "git@", "git://"))


def clone_repo(url: str) -> str:
    """
    Shallow-clone a remote Git repository into a temporary directory.
    Returns the path to the cloned directory.
    """
    try:
        import git
    except ImportError:
        logger.error("gitpython is not installed. Run: pip install gitpython")
        sys.exit(1)

    tmp = tempfile.mkdtemp(prefix="gituml_")
    logger.info(f"Cloning {url} → {tmp}")
    logger.info("This may take a moment for large repos...")

    try:
        git.Repo.clone_from(url, tmp, depth=1)
    except git.exc.GitCommandError as exc:
        logger.error(f"Failed to clone repository: {exc}")
        shutil.rmtree(tmp, ignore_errors=True)
        sys.exit(1)

    logger.info("Clone complete")
    return tmp


def resolve_repo(repo_arg: str) -> tuple[str, bool]:
    """
    Returns (local_path, was_cloned).

    If repo_arg is a URL, clones it and returns the temp path.
    If it is a local path, validates it and returns the resolved path.
    """
    if is_git_url(repo_arg):
        return clone_repo(repo_arg), True

    path = Path(repo_arg)
    if not path.exists():
        logger.error(f"Local path does not exist: {repo_arg}")
        sys.exit(1)
    if not path.is_dir():
        logger.error(f"Path is not a directory: {repo_arg}")
        sys.exit(1)

    logger.info(f"Using local repo: {path.resolve()}")
    return str(path.resolve()), False


# ─────────────────────────────────────────────────────────────────────────────
# Output helpers
# ─────────────────────────────────────────────────────────────────────────────

def write_output(output_dir: Path, filename: str, content: str) -> None:
    """Write diagram content to a file, creating the directory if needed."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(content, encoding="utf-8")
    logger.info(f"Written → {path}")


def build_content(title: str, mermaid: str, plantuml: str, fmt: str) -> str:
    """
    Combine Mermaid and/or PlantUML sections into a single Markdown document.

    Args:
        title:   Human-readable diagram title.
        mermaid: Mermaid diagram source.
        plantuml: PlantUML diagram source.
        fmt:     One of "mermaid", "plantuml", "both".

    Returns:
        Markdown string with the selected sections separated by horizontal rules.
    """
    parts = []
    if fmt in ("both", "mermaid"):
        parts.append(f"# {title} — Mermaid\n\n{mermaid}")
    if fmt in ("both", "plantuml"):
        parts.append(f"# {title} — PlantUML\n\n```plantuml\n{plantuml}\n```")
    return "\n\n---\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    arg_parser = build_arg_parser()
    args = arg_parser.parse_args()

    fmt        = args.format
    output_dir = Path(args.output_dir)
    flow_class  = args.flow_class  or args.entry_class
    flow_method = args.flow_method or args.entry_method

    # ── 1. Resolve repo ───────────────────────────────────────────────────────
    repo_path, was_cloned = resolve_repo(args.repo)

    try:
        # ── 2. Parse Java files ───────────────────────────────────────────────
        from core.java_parser import JavaParser

        logger.info("Parsing Java files...")
        java_parser = JavaParser(skip_test_dirs=not args.include_tests)
        metadata    = java_parser.parse_repo(repo_path)
        logger.info(metadata.summary())

        if not metadata.classes:
            logger.error("No Java classes found. Is this a Java project?")
            sys.exit(1)

        # ── 3. Generate diagrams ──────────────────────────────────────────────
        from diagrams.class_diagram     import ClassDiagramBuilder
        from diagrams.component_diagram import ComponentDiagramBuilder
        from diagrams.sequence_diagram  import SequenceDiagramBuilder
        from diagrams.flowchart         import FlowchartBuilder

        logger.info("Generating class diagram...")
        cb = ClassDiagramBuilder(metadata, max_classes=args.max_classes)
        write_output(
            output_dir, "class_diagram.md",
            build_content("Class Diagram", cb.to_mermaid(), cb.to_plantuml(), fmt),
        )

        logger.info("Generating component diagram...")
        comp = ComponentDiagramBuilder(metadata)
        write_output(
            output_dir, "component_diagram.md",
            build_content("Component Diagram", comp.to_mermaid(), comp.to_plantuml(), fmt),
        )

        logger.info("Generating sequence diagram...")
        seq = SequenceDiagramBuilder(
            metadata,
            entry_class=args.entry_class,
            entry_method=args.entry_method,
        )
        write_output(
            output_dir, "sequence_diagram.md",
            build_content("Sequence Diagram", seq.to_mermaid(), seq.to_plantuml(), fmt),
        )

        logger.info("Generating flowchart...")
        flow = FlowchartBuilder(
            metadata,
            target_class=flow_class,
            target_method=flow_method,
        )
        write_output(
            output_dir, "flowchart.md",
            build_content("Flowchart", flow.to_mermaid(), flow.to_plantuml(), fmt),
        )

        # ── 4. Summary ────────────────────────────────────────────────────────
        separator = "=" * 60
        print(f"\n{separator}")
        print("  GitUML — Done!")
        print(separator)
        print(f"  Repo       : {metadata.repo_name}")
        print(f"  Source     : {args.repo}")
        print(f"  Type       : {metadata.project_type}")
        print(f"  Build      : {metadata.build_system}")
        print(f"  Classes    : {len(metadata.classes)}")
        print(f"  Packages   : {len(metadata.packages)}")
        print(f"  Layers     : {metadata.layer_summary}")
        print(f"  Format     : {fmt}")
        print(separator)
        print("  Output:")
        for fname in [
            "class_diagram.md",
            "component_diagram.md",
            "sequence_diagram.md",
            "flowchart.md",
        ]:
            print(f"    {output_dir / fname}")
        print(separator)

    finally:
        if was_cloned:
            logger.info(f"Cleaning up temp directory: {repo_path}")
            shutil.rmtree(repo_path, ignore_errors=True)


if __name__ == "__main__":
    main()
