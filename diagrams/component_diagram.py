from collections import defaultdict
from core.models import RepoMetadata


LAYER_COLORS_PLANTUML = {
    "controller":  "#lightblue",
    "service":     "#lightyellow",
    "repository":  "#lightgreen",
    "model":       "#lightsalmon",
    "config":      "#lightgrey",
    "messaging":   "#plum",
    "scheduler":   "#wheat",
    "other":       "#white",
}

LAYER_STYLE_MERMAID = {
    "controller":  "fill:#AED6F1",
    "service":     "fill:#A9DFBF",
    "repository":  "fill:#F9E79F",
    "model":       "fill:#F1948A",
    "config":      "fill:#D7DBDD",
    "messaging":   "fill:#D2B4DE",
    "scheduler":   "fill:#FAD7A0",
    "other":       "fill:#EAECEE",
}


class ComponentDiagramBuilder:
    """
    Generates high-level architecture / component diagrams.
    Groups classes by Spring layer or package and shows inter-component dependencies.
    Two views:
      1. Layer view  — groups by Spring annotation layer (for Spring Boot repos)
      2. Package view — groups by Java package (for pure Java repos)
    """

    def __init__(self, metadata: RepoMetadata):
        self.metadata = metadata
        self.is_spring = metadata.project_type in ("spring_boot", "spring_mvc")

    def to_mermaid(self) -> str:
        if self.is_spring:
            return self._mermaid_layer_view()
        return self._mermaid_package_view()

    def to_plantuml(self) -> str:
        if self.is_spring:
            return self._plantuml_layer_view()
        return self._plantuml_package_view()

    # ------------------------------------------------------------------
    # Mermaid — layer view
    # ------------------------------------------------------------------

    def _mermaid_layer_view(self) -> str:
        by_layer = self.metadata.classes_by_layer()
        dep_graph = self.metadata.dependency_graph
        lines = ["```mermaid", "graph TD"]
        lines.append(f"    %% Architecture: {self.metadata.repo_name}")
        lines.append("")

        class_to_layer = {
            cls.name: (cls.spring_layer or "other")
            for cls in self.metadata.classes
        }

        # Subgraphs per layer
        for layer, classes in by_layer.items():
            if not classes:
                continue
            lines.append(f"    subgraph {layer.upper()}[{layer.title()} Layer]")
            for cls in classes:
                lines.append(f"        {cls.name}[{cls.name}]")
            lines.append("    end")
            lines.append("")

        # Inter-layer edges (deduplicated)
        edges = set()
        for cls in self.metadata.classes:
            src_layer = cls.spring_layer or "other"
            for dep in dep_graph.get(cls.name, []):
                tgt_layer = class_to_layer.get(dep, "other")
                if src_layer != tgt_layer:
                    edges.add((cls.name, dep))

        for src, tgt in sorted(edges):
            lines.append(f"    {src} --> {tgt}")

        # Styles
        lines.append("")
        for layer, classes in by_layer.items():
            style = LAYER_STYLE_MERMAID.get(layer, "fill:#EAECEE")
            for cls in classes:
                lines.append(f"    style {cls.name} {style}")

        lines.append("```")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Mermaid — package view
    # ------------------------------------------------------------------

    def _mermaid_package_view(self) -> str:
        by_package = self.metadata.classes_by_package()
        dep_graph = self.metadata.dependency_graph
        lines = ["```mermaid", "graph LR"]
        lines.append(f"    %% Package structure: {self.metadata.repo_name}")
        lines.append("")

        class_to_package = {cls.name: cls.package for cls in self.metadata.classes}

        # One node per package
        for pkg in sorted(by_package.keys()):
            safe_id = pkg.replace(".", "_") or "default"
            class_list = ", ".join(c.name for c in by_package[pkg][:5])
            lines.append(f"    {safe_id}[\"{pkg}\\n({class_list})\"]")

        lines.append("")

        # Package-level edges
        pkg_edges = set()
        for cls in self.metadata.classes:
            for dep in dep_graph.get(cls.name, []):
                src_pkg = cls.package
                tgt_pkg = class_to_package.get(dep, "")
                if src_pkg != tgt_pkg and src_pkg and tgt_pkg:
                    pkg_edges.add((
                        src_pkg.replace(".", "_"),
                        tgt_pkg.replace(".", "_")
                    ))

        for src, tgt in sorted(pkg_edges):
            lines.append(f"    {src} --> {tgt}")

        lines.append("```")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # PlantUML — layer view
    # ------------------------------------------------------------------

    def _plantuml_layer_view(self) -> str:
        by_layer = self.metadata.classes_by_layer()
        dep_graph = self.metadata.dependency_graph
        class_to_layer = {
            cls.name: (cls.spring_layer or "other")
            for cls in self.metadata.classes
        }

        lines = [
            "@startuml",
            f"' Architecture: {self.metadata.repo_name}",
            "skinparam componentStyle rectangle",
            "skinparam monochrome false",
            "",
        ]

        for layer, classes in by_layer.items():
            if not classes:
                continue
            color = LAYER_COLORS_PLANTUML.get(layer, "#white")
            lines.append(f"package \"{layer.title()} Layer\" {color} {{")
            for cls in classes:
                lines.append(f"  [{cls.name}]")
            lines.append("}")
            lines.append("")

        # Edges
        edges = set()
        for cls in self.metadata.classes:
            src_layer = cls.spring_layer or "other"
            for dep in dep_graph.get(cls.name, []):
                tgt_layer = class_to_layer.get(dep, "other")
                if src_layer != tgt_layer:
                    edges.add((cls.name, dep))

        for src, tgt in sorted(edges):
            lines.append(f"[{src}] --> [{tgt}]")

        lines.append("")
        lines.append("@enduml")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # PlantUML — package view
    # ------------------------------------------------------------------

    def _plantuml_package_view(self) -> str:
        by_package = self.metadata.classes_by_package()
        dep_graph = self.metadata.dependency_graph
        class_to_package = {cls.name: cls.package for cls in self.metadata.classes}

        lines = [
            "@startuml",
            f"' Package structure: {self.metadata.repo_name}",
            "skinparam monochrome true",
            "",
        ]

        for pkg, classes in sorted(by_package.items()):
            lines.append(f"package {pkg or 'default'} {{")
            for cls in classes:
                lines.append(f"  [{cls.name}]")
            lines.append("}")
            lines.append("")

        pkg_edges = set()
        for cls in self.metadata.classes:
            for dep in dep_graph.get(cls.name, []):
                src_pkg = cls.package
                tgt_pkg = class_to_package.get(dep, "")
                if src_pkg != tgt_pkg and src_pkg and tgt_pkg:
                    pkg_edges.add((src_pkg, tgt_pkg, cls.name, dep))

        for src_pkg, tgt_pkg, src_cls, tgt_cls in sorted(pkg_edges):
            lines.append(f"[{src_cls}] --> [{tgt_cls}]")

        lines.append("")
        lines.append("@enduml")
        return "\n".join(lines)
