"""
GitUML MCP Server
=================
FastMCP server — exposes all GitUML diagram generators as MCP tools that
Claude Desktop (or any MCP-compatible client) can call directly.

Tools exposed:
  1. analyze_repo              — structured repo summary (no diagrams)
  2. generate_all              — all 4 diagrams written to disk (main.py equivalent)
  3. generate_class_diagram    — UML class diagram
  4. generate_component_diagram — architecture / component diagram
  5. generate_sequence_diagram — sequence / call-chain diagram
  6. generate_flowchart        — method-level or high-level flowchart

The server communicates over STDIO (JSON-RPC 2.0).
stdout is reserved for MCP traffic; all logging goes to stderr.

Claude Desktop config (claude_desktop_config.json):
    {
      "mcpServers": {
        "gituml": {
          "command": "python",
          "args": ["C:/path/to/gituml/server.py"]
        }
      }
    }

Run directly to verify the server starts cleanly (it will block on stdin):
    python server.py
"""

import sys
import logging
import tempfile
import shutil
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

# ── Logging — stderr only; stdout is reserved for MCP JSON-RPC ───────────────
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("gituml.server")

# ── FastMCP instance ──────────────────────────────────────────────────────────
mcp = FastMCP(
    name="GitUML",
    instructions=(
        "GitUML generates UML diagrams and flowcharts from Java and Spring Boot "
        "repositories. Provide a GitHub URL or a local absolute path. "
        "Available diagrams: class diagram, sequence diagram, flowchart, "
        "component / architecture diagram. "
        "Output format: mermaid, plantuml, or both. "
        "Use generate_all to produce all 4 diagrams and write them to disk at once. "
        "Use analyze_repo first to understand the repo structure before generating diagrams."
    ),
)


# ══════════════════════════════════════════════════════════════════════════════
# Shared helpers — logic mirrors main.py exactly so both entry points behave
# identically
# ══════════════════════════════════════════════════════════════════════════════

def _is_git_url(value: str) -> bool:
    return value.startswith(("http://", "https://", "git@", "git://"))


def _clone_repo(url: str) -> str:
    """Shallow-clone a remote Git repo and return the local temp path."""
    try:
        import git
    except ImportError:
        raise RuntimeError("gitpython not installed. Run: pip install gitpython")

    tmp = tempfile.mkdtemp(prefix="gituml_")
    logger.info(f"Cloning {url} → {tmp}")
    logger.info("This may take a moment for large repos...")

    try:
        git.Repo.clone_from(url, tmp, depth=1)
    except git.exc.GitCommandError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError(f"Failed to clone repository: {exc}") from exc

    logger.info("Clone complete")
    return tmp


def _resolve_repo(repo: str):
    """
    Returns (local_path, was_cloned).
    Clones if a URL; validates and returns absolute path if local.

    Return type is unannotated to avoid Python 3.14 tuple[] hint issues
    with the FastMCP introspection layer.
    """
    if _is_git_url(repo):
        return _clone_repo(repo), True

    path = Path(repo)
    if not path.exists():
        raise ValueError(f"Local path does not exist: {repo}")
    if not path.is_dir():
        raise ValueError(f"Path is not a directory: {repo}")

    logger.info(f"Using local repo: {path.resolve()}")
    return str(path.resolve()), False


def _cleanup(path: str, is_temp: bool) -> None:
    """Remove temp clone directory if one was created."""
    if is_temp:
        logger.info(f"Cleaning up temp directory: {path}")
        shutil.rmtree(path, ignore_errors=True)


def _parse(repo_path: str, skip_test_dirs: bool = True):
    """Parse the repo and return RepoMetadata."""
    from core.java_parser import JavaParser

    logger.info("Parsing Java files...")
    parser   = JavaParser(skip_test_dirs=skip_test_dirs)
    metadata = parser.parse_repo(repo_path)
    logger.info(metadata.summary())
    return metadata


def _validate_format(fmt: str) -> str:
    """Normalise format string; falls back to 'both' for unrecognised values."""
    fmt = fmt.lower().strip()
    return fmt if fmt in ("mermaid", "plantuml", "both") else "both"


def write_output(output_dir: Path, filename: str, content: str) -> None:
    """Write diagram content to a Markdown file, creating the directory if needed."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(content, encoding="utf-8")
    logger.info(f"Written → {path}")


def build_content(title: str, mermaid: str, plantuml: str, fmt: str) -> str:
    """
    Combine Mermaid and/or PlantUML sections into a single Markdown document.
    """
    parts = []
    if fmt in ("both", "mermaid"):
        parts.append(f"# {title} — Mermaid\n\n{mermaid}")
    if fmt in ("both", "plantuml"):
        parts.append(f"# {title} — PlantUML\n\n```plantuml\n{plantuml}\n```")
    return "\n\n---\n\n".join(parts)


def _build_summary(metadata, repo: str, output_dir: Path, fmt: str) -> str:
    """
    Build the completion summary block, log it to stderr, and return it as a
    string so MCP tools can return it to Claude.
    """
    separator = "=" * 60
    lines = [
        "",
        separator,
        "  GitUML — Done!",
        separator,
        f"  Repo       : {metadata.repo_name}",
        f"  Source     : {repo}",
        f"  Type       : {metadata.project_type}",
        f"  Build      : {metadata.build_system}",
        f"  Classes    : {len(metadata.classes)}",
        f"  Packages   : {len(metadata.packages)}",
        f"  Layers     : {metadata.layer_summary}",
        f"  Format     : {fmt}",
        separator,
        "  Output:",
    ]
    for fname in ["class_diagram.md", "component_diagram.md",
                  "sequence_diagram.md", "flowchart.md"]:
        lines.append(f"    {output_dir / fname}")
    lines.append(separator)

    summary = "\n".join(lines)
    print(summary, file=sys.stderr)
    return summary


# ══════════════════════════════════════════════════════════════════════════════
# Tool 1 — analyze_repo
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def analyze_repo(repo: str) -> str:
    """
    Analyse a Java/Spring Boot repository and return a structured summary.

    Detects project type (pure_java, spring_boot, spring_mvc), build system
    (maven, gradle), lists all packages, classes, and Spring layer breakdown.
    Use this first before generating diagrams to understand the repo structure.

    Args:
        repo: GitHub/GitLab URL (e.g. https://github.com/user/repo)
              OR absolute local path (e.g. C:/projects/my-app)

    Returns:
        Structured text summary of the repository.
    """
    repo_path, is_temp = _resolve_repo(repo)
    try:
        metadata = _parse(repo_path)
        by_layer = metadata.classes_by_layer()

        lines = [
            f"# Repository Analysis: {metadata.repo_name}",
            "",
            f"**Project type:** {metadata.project_type}",
            f"**Build system:** {metadata.build_system}",
            f"**Total classes:** {len(metadata.classes)}",
            f"**Packages ({len(metadata.packages)}):**",
        ]
        for pkg in metadata.packages:
            lines.append(f"  - {pkg}")

        lines.append("\n**Layer breakdown:**")
        for layer, classes in sorted(by_layer.items()):
            class_names = ", ".join(c.name for c in classes[:6])
            more = f" (+{len(classes) - 6} more)" if len(classes) > 6 else ""
            lines.append(f"  - **{layer}** ({len(classes)}): {class_names}{more}")

        lines.append("\n**Dependency summary (top 10):**")
        for cls_name, deps in list(metadata.dependency_graph.items())[:10]:
            if deps:
                lines.append(f"  - {cls_name} → {', '.join(deps)}")

        return "\n".join(lines)
    finally:
        _cleanup(repo_path, is_temp)


# ══════════════════════════════════════════════════════════════════════════════
# Tool 2 — generate_all
#
# ⚠️  Python 3.14 + FastMCP silently drops tools that have Optional[str] params.
#     Using str = "" defaults instead; convert empty strings to None internally.
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def generate_all(
    repo: str,
    output_dir: str = "output",
    format: str = "both",
    entry_class: str = "",
    entry_method: str = "",
    flow_class: str = "",
    flow_method: str = "",
    include_tests: bool = False,
    max_classes: int = 60,
) -> str:
    """
    Generate all 4 UML diagrams and write them to disk.

    Equivalent to running: python main.py --repo <repo> --output-dir <output_dir>

    Produces:
        output_dir/class_diagram.md
        output_dir/component_diagram.md
        output_dir/sequence_diagram.md
        output_dir/flowchart.md

    Args:
        repo:          GitHub/GitLab URL or local path to the Java repository.
        output_dir:    Directory to write diagram files (default: ./output).
        format:        Output format — "mermaid", "plantuml", or "both" (default: "both").
        entry_class:   Class for sequence diagram entry point (e.g. "UserController").
                       Leave empty to show all inter-layer interactions.
        entry_method:  Method to trace for sequence diagram (e.g. "createUser").
                       Leave empty for a full interaction view.
        flow_class:    Class for method-level flowchart (defaults to entry_class).
                       Leave empty for the high-level architecture flowchart.
        flow_method:   Method for method-level flowchart (defaults to entry_method).
                       Leave empty for the high-level architecture flowchart.
        include_tests: Include test directories in parsing (default: False).
        max_classes:   Max classes in class diagram (default: 60).

    Returns:
        Summary string — repo name, type, build system, class count, output paths.
    """
    fmt = _validate_format(format)
    out = Path(output_dir)

    # Convert empty strings to None (mirrors argparse None defaults in main.py)
    _entry_class  = entry_class  or None
    _entry_method = entry_method or None
    _flow_class   = flow_class   or entry_class  or None
    _flow_method  = flow_method  or entry_method or None

    repo_path, was_cloned = _resolve_repo(repo)
    try:
        metadata = _parse(repo_path, skip_test_dirs=not include_tests)

        if not metadata.classes:
            return "❌ No Java classes found. Is this a Java project?"

        from diagrams.class_diagram     import ClassDiagramBuilder
        from diagrams.component_diagram import ComponentDiagramBuilder
        from diagrams.sequence_diagram  import SequenceDiagramBuilder
        from diagrams.flowchart         import FlowchartBuilder

        logger.info("Generating class diagram...")
        cb = ClassDiagramBuilder(metadata, max_classes=max_classes)
        write_output(out, "class_diagram.md",
                     build_content("Class Diagram", cb.to_mermaid(), cb.to_plantuml(), fmt))

        logger.info("Generating component diagram...")
        comp = ComponentDiagramBuilder(metadata)
        write_output(out, "component_diagram.md",
                     build_content("Component Diagram", comp.to_mermaid(), comp.to_plantuml(), fmt))

        logger.info("Generating sequence diagram...")
        seq = SequenceDiagramBuilder(metadata,
                                     entry_class=_entry_class,
                                     entry_method=_entry_method)
        write_output(out, "sequence_diagram.md",
                     build_content("Sequence Diagram", seq.to_mermaid(), seq.to_plantuml(), fmt))

        logger.info("Generating flowchart...")
        flow = FlowchartBuilder(metadata,
                                target_class=_flow_class,
                                target_method=_flow_method)
        write_output(out, "flowchart.md",
                     build_content("Flowchart", flow.to_mermaid(), flow.to_plantuml(), fmt))

        return _build_summary(metadata, repo, out, fmt)

    finally:
        _cleanup(repo_path, was_cloned)


# ══════════════════════════════════════════════════════════════════════════════
# Tool 3 — generate_class_diagram
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def generate_class_diagram(
    repo: str,
    output_dir: str = "",
    format: str = "both",
    package_filter: Optional[str] = None,
    max_classes: int = 60,
) -> str:
    """
    Generate a UML class diagram for a Java/Spring Boot repository.

    If output_dir is provided, writes class_diagram.md to that directory.
    Otherwise returns the diagram content as a string.

    Args:
        repo:           GitHub URL or local path to the Java repository.
        output_dir:     Directory to write class_diagram.md (leave empty to return as string).
        format:         Output format — "mermaid", "plantuml", or "both" (default: "both").
        package_filter: Optional package prefix to filter classes (e.g. "com.example.service").
        max_classes:    Maximum number of classes to include (default: 60).

    Returns:
        Diagram content, or a confirmation message if output_dir was given.
    """
    fmt = _validate_format(format)
    repo_path, is_temp = _resolve_repo(repo)
    try:
        metadata = _parse(repo_path)

        if package_filter:
            metadata.classes = [
                c for c in metadata.classes
                if c.package.startswith(package_filter)
            ]
            if not metadata.classes:
                return (
                    f"No classes found in package '{package_filter}'. "
                    f"Available packages: {', '.join(metadata.packages)}"
                )

        from diagrams.class_diagram import ClassDiagramBuilder
        cb      = ClassDiagramBuilder(metadata, max_classes=max_classes)
        content = build_content("Class Diagram", cb.to_mermaid(), cb.to_plantuml(), fmt)

        if output_dir:
            write_output(Path(output_dir), "class_diagram.md", content)
            return f"✅ Written → {output_dir}/class_diagram.md"

        return content
    finally:
        _cleanup(repo_path, is_temp)


# ══════════════════════════════════════════════════════════════════════════════
# Tool 4 — generate_component_diagram
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def generate_component_diagram(
    repo: str,
    output_dir: str = "",
    format: str = "both",
) -> str:
    """
    Generate a high-level component/architecture diagram for a Java repository.

    If output_dir is provided, writes component_diagram.md to that directory.
    Otherwise returns the diagram content as a string.

    Args:
        repo:       GitHub URL or local path to the Java repository.
        output_dir: Directory to write component_diagram.md (leave empty to return as string).
        format:     Output format — "mermaid", "plantuml", or "both" (default: "both").

    Returns:
        Diagram content, or a confirmation message if output_dir was given.
    """
    fmt = _validate_format(format)
    repo_path, is_temp = _resolve_repo(repo)
    try:
        metadata = _parse(repo_path)

        from diagrams.component_diagram import ComponentDiagramBuilder
        comp    = ComponentDiagramBuilder(metadata)
        content = build_content("Component Diagram", comp.to_mermaid(), comp.to_plantuml(), fmt)

        if output_dir:
            write_output(Path(output_dir), "component_diagram.md", content)
            return f"✅ Written → {output_dir}/component_diagram.md"

        return content
    finally:
        _cleanup(repo_path, is_temp)


# ══════════════════════════════════════════════════════════════════════════════
# Tool 5 — generate_sequence_diagram
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def generate_sequence_diagram(
    repo: str,
    output_dir: str = "",
    format: str = "both",
    entry_class: Optional[str] = None,
    entry_method: Optional[str] = None,
) -> str:
    """
    Generate a UML sequence diagram for a Java/Spring Boot repository.

    If output_dir is provided, writes sequence_diagram.md to that directory.
    Otherwise returns the diagram content as a string.

    Args:
        repo:         GitHub URL or local path to the Java repository.
        output_dir:   Directory to write sequence_diagram.md (leave empty to return as string).
        format:       Output format — "mermaid", "plantuml", or "both" (default: "both").
        entry_class:  Class to start tracing from (e.g. "UserController").
                      Omit to generate a full inter-layer interaction view.
        entry_method: Method to trace (e.g. "createUser").
                      Omit for a broad inter-layer view.

    Returns:
        Diagram content, or a confirmation message if output_dir was given.
    """
    fmt = _validate_format(format)
    repo_path, is_temp = _resolve_repo(repo)
    try:
        metadata = _parse(repo_path)

        from diagrams.sequence_diagram import SequenceDiagramBuilder
        seq     = SequenceDiagramBuilder(metadata,
                                         entry_class=entry_class,
                                         entry_method=entry_method)
        content = build_content("Sequence Diagram", seq.to_mermaid(), seq.to_plantuml(), fmt)

        if output_dir:
            write_output(Path(output_dir), "sequence_diagram.md", content)
            return f"✅ Written → {output_dir}/sequence_diagram.md"

        return content
    finally:
        _cleanup(repo_path, is_temp)


# ══════════════════════════════════════════════════════════════════════════════
# Tool 6 — generate_flowchart
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def generate_flowchart(
    repo: str,
    output_dir: str = "",
    format: str = "both",
    target_class: Optional[str] = None,
    target_method: Optional[str] = None,
) -> str:
    """
    Generate a flowchart for a Java/Spring Boot repository.

    If output_dir is provided, writes flowchart.md to that directory.
    Otherwise returns the diagram content as a string.

    Args:
        repo:          GitHub URL or local path to the Java repository.
        output_dir:    Directory to write flowchart.md (leave empty to return as string).
        format:        Output format — "mermaid", "plantuml", or "both" (default: "both").
        target_class:  Class containing the method to flowchart (e.g. "OrderService").
                       Omit for a high-level architecture flowchart.
        target_method: Method name to generate flowchart for (e.g. "processOrder").
                       Omit for a high-level architecture flowchart.

    Returns:
        Diagram content, or a confirmation message if output_dir was given.
    """
    fmt = _validate_format(format)
    repo_path, is_temp = _resolve_repo(repo)
    try:
        metadata = _parse(repo_path)

        from diagrams.flowchart import FlowchartBuilder
        flow    = FlowchartBuilder(metadata,
                                   target_class=target_class,
                                   target_method=target_method)
        content = build_content("Flowchart", flow.to_mermaid(), flow.to_plantuml(), fmt)

        if output_dir:
            write_output(Path(output_dir), "flowchart.md", content)
            return f"✅ Written → {output_dir}/flowchart.md"

        return content
    finally:
        _cleanup(repo_path, is_temp)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("GitUML MCP Server starting (STDIO mode)...")
    mcp.run()
