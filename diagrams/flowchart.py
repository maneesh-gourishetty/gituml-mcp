from core.models import RepoMetadata, ClassMeta, MethodMeta
from typing import Optional


class FlowchartBuilder:
    """
    Generates flowcharts for individual methods by analysing control flow:
    if/else branches, loops (for/while/do), try/catch, and early returns.
    Also generates a repo-level call flow overview.
    """

    def __init__(self, metadata: RepoMetadata,
                 target_class: Optional[str] = None,
                 target_method: Optional[str] = None):
        self.metadata = metadata
        self.target_class = target_class
        self.target_method = target_method
        self._class_map = {cls.name: cls for cls in metadata.classes}

    def to_mermaid(self) -> str:
        if self.target_class and self.target_method:
            return self._method_flowchart_mermaid()
        return self._overview_flowchart_mermaid()

    def to_plantuml(self) -> str:
        if self.target_class and self.target_method:
            return self._method_flowchart_plantuml()
        return self._overview_flowchart_plantuml()

    # ------------------------------------------------------------------
    # Method-level flowchart — Mermaid
    # ------------------------------------------------------------------

    def _method_flowchart_mermaid(self) -> str:
        cls = self._class_map.get(self.target_class)
        if not cls:
            return f"```mermaid\ngraph TD\n    ERR[Class {self.target_class} not found]\n```"

        method = next((m for m in cls.methods if m.name == self.target_method), None)
        if not method:
            return f"```mermaid\ngraph TD\n    ERR[Method {self.target_method} not found]\n```"

        lines = ["```mermaid", f"flowchart TD"]
        lines.append(f"    %% {cls.name}.{method.name}()")
        lines.append("")
        lines.append(f"    START([Start: {method.name}])")

        node_id = 0

        def nid():
            nonlocal node_id
            node_id += 1
            return f"N{node_id}"

        prev = "START"

        # Parameters
        if method.parameters:
            param_str = ", ".join(f"{p.type} {p.name}" for p in method.parameters)
            n = nid()
            lines.append(f"    {n}[/Input: {param_str}/]")
            lines.append(f"    {prev} --> {n}")
            prev = n

        # Control flow nodes
        if method.has_try_catch:
            n = nid()
            success_n = nid()
            catch_n = nid()
            lines.append(f"    {n}{{Try block}}")
            lines.append(f"    {prev} --> {n}")
            lines.append(f"    {success_n}[Success path]")
            lines.append(f"    {catch_n}[Handle Exception]")
            lines.append(f"    {n} -->|Success| {success_n}")
            lines.append(f"    {n} -->|Exception| {catch_n}")
            prev = success_n

        if method.has_if:
            n = nid()
            lines.append(f"    {n}{{Condition?}}")
            lines.append(f"    {prev} --> {n}")
            yes_n = nid()
            no_n = nid()
            lines.append(f"    {yes_n}[True branch]")
            lines.append(f"    {no_n}[False branch]")
            lines.append(f"    {n} -->|Yes| {yes_n}")
            lines.append(f"    {n} -->|No| {no_n}")
            merge_n = nid()
            lines.append(f"    {merge_n}[ ]")
            lines.append(f"    {yes_n} --> {merge_n}")
            lines.append(f"    {no_n} --> {merge_n}")
            prev = merge_n

        if method.has_loop:
            n = nid()
            lines.append(f"    {n}{{Loop condition}}")
            lines.append(f"    {prev} --> {n}")
            body_n = nid()
            lines.append(f"    {body_n}[Loop body]")
            lines.append(f"    {n} -->|true| {body_n}")
            lines.append(f"    {body_n} --> {n}")
            exit_n = nid()
            lines.append(f"    {exit_n}[ ]")
            lines.append(f"    {n} -->|false| {exit_n}")
            prev = exit_n

        # Method calls
        for call in method.calls[:5]:
            n = nid()
            lines.append(f"    {n}[Call: {call}]")
            lines.append(f"    {prev} --> {n}")
            prev = n

        # Return
        ret_n = nid()
        lines.append(f"    {ret_n}([Return: {method.return_type}])")
        lines.append(f"    {prev} --> {ret_n}")

        lines.append("```")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Overview flowchart — Mermaid (Spring layer call flow)
    # ------------------------------------------------------------------

    def _overview_flowchart_mermaid(self) -> str:
        lines = ["```mermaid", "flowchart TD"]
        lines.append(f"    %% Call flow overview: {self.metadata.repo_name}")
        lines.append("")

        by_layer = self.metadata.classes_by_layer()

        # Standard Spring flow
        if self.metadata.project_type in ("spring_boot", "spring_mvc"):
            lines.append("    CLIENT([HTTP Client])")
            lines.append("")

            layer_order = ["controller", "service", "repository", "model",
                           "messaging", "config", "scheduler", "other"]

            prev_layer_nodes = ["CLIENT"]
            for layer in layer_order:
                classes = by_layer.get(layer, [])
                if not classes:
                    continue

                layer_nodes = []
                for cls in classes[:6]:  # cap per layer
                    safe = cls.name.replace(" ", "_")
                    label = f"{cls.name}"
                    if any(a.name in ("RestController", "Controller") for a in cls.annotations):
                        lines.append(f"    {safe}[\"{label}\\n@{layer}\"]")
                    else:
                        lines.append(f"    {safe}({label})")
                    layer_nodes.append(safe)

                # Connect previous layer to this layer
                for prev in prev_layer_nodes:
                    for curr in layer_nodes[:2]:
                        lines.append(f"    {prev} --> {curr}")

                prev_layer_nodes = layer_nodes
                lines.append("")

            # DB node
            if by_layer.get("repository"):
                lines.append("    DB[(Database)]")
                for repo_cls in by_layer["repository"][:3]:
                    lines.append(f"    {repo_cls.name} --> DB")

        else:
            # Pure Java: package-level flow
            by_package = self.metadata.classes_by_package()
            prev_nodes = []
            for pkg, classes in list(by_package.items())[:8]:
                pkg_safe = pkg.replace(".", "_")
                class_list = "\\n".join(c.name for c in classes[:3])
                lines.append(f"    {pkg_safe}[\"{pkg}\\n{class_list}\"]")
                for prev in prev_nodes[-2:]:
                    lines.append(f"    {prev} --> {pkg_safe}")
                prev_nodes.append(pkg_safe)

        lines.append("```")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # PlantUML versions
    # ------------------------------------------------------------------

    def _method_flowchart_plantuml(self) -> str:
        cls = self._class_map.get(self.target_class)
        method = next((m for m in cls.methods if m.name == self.target_method), None) if cls else None

        lines = [
            "@startuml",
            f"' Flowchart: {self.target_class}.{self.target_method}",
            "start",
            "",
        ]

        if not cls or not method:
            lines.append(f":{self.target_class}.{self.target_method} - not found;")
        else:
            if method.parameters:
                param_str = ", ".join(f"{p.type} {p.name}" for p in method.parameters)
                lines.append(f":Input: {param_str};")

            if method.has_try_catch:
                lines.append("group try")

            if method.has_if:
                lines.append("if (Condition?) then (yes)")
                lines.append("  :True branch;")
                lines.append("else (no)")
                lines.append("  :False branch;")
                lines.append("endif")

            if method.has_loop:
                lines.append("while (Loop condition?)")
                lines.append("  :Loop body;")
                lines.append("endwhile")

            for call in method.calls[:5]:
                lines.append(f":{call};")

            if method.has_try_catch:
                lines.append("end group")

            lines.append(f":Return {method.return_type};")

        lines.append("")
        lines.append("stop")
        lines.append("@enduml")
        return "\n".join(lines)

    def _overview_flowchart_plantuml(self) -> str:
        lines = [
            "@startuml",
            f"' Call flow: {self.metadata.repo_name}",
            "start",
            "",
        ]

        by_layer = self.metadata.classes_by_layer()
        layer_order = ["controller", "service", "repository", "model",
                       "messaging", "config", "other"]

        for layer in layer_order:
            classes = by_layer.get(layer, [])
            if not classes:
                continue
            class_names = ", ".join(c.name for c in classes[:4])
            lines.append(f":[ {layer.upper()} ]\\n{class_names};")

        lines.append("")
        lines.append("stop")
        lines.append("@enduml")
        return "\n".join(lines)
