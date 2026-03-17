from core.models import RepoMetadata, ClassMeta, MethodMeta
from typing import List, Optional, Tuple


class SequenceDiagramBuilder:
    """
    Generates sequence diagrams by tracing method call chains
    from a given entry point (e.g. a controller method).
    Falls back to showing all inter-class calls if no entry point given.
    """

    def __init__(self, metadata: RepoMetadata, entry_class: Optional[str] = None,
                 entry_method: Optional[str] = None, max_depth: int = 5):
        self.metadata = metadata
        self.entry_class = entry_class
        self.entry_method = entry_method
        self.max_depth = max_depth
        self._class_map = {cls.name: cls for cls in metadata.classes}

    def to_mermaid(self) -> str:
        lines = ["```mermaid", "sequenceDiagram"]
        lines.append(f"    %% {self.metadata.repo_name}")

        if self.entry_class and self.entry_method:
            calls = self._trace_calls(self.entry_class, self.entry_method, depth=0)
            if calls:
                participants = self._extract_participants(calls)
                for p in participants:
                    cls = self._class_map.get(p)
                    alias = f"{p} [{cls.spring_layer}]" if cls and cls.spring_layer else p
                    lines.append(f"    participant {p} as {alias}")
                lines.append("")
                for caller, callee, method in calls:
                    lines.append(f"    {caller}->>+{callee}: {method}()")
                    lines.append(f"    {callee}-->>-{caller}: return")
            else:
                lines.extend(self._mermaid_all_calls())
        else:
            lines.extend(self._mermaid_all_calls())

        lines.append("```")
        return "\n".join(lines)

    def to_plantuml(self) -> str:
        lines = [
            "@startuml",
            f"' Sequence: {self.metadata.repo_name}",
            "skinparam monochrome true",
            "autoactivate on",
            "",
        ]

        if self.entry_class and self.entry_method:
            calls = self._trace_calls(self.entry_class, self.entry_method, depth=0)
            if calls:
                participants = self._extract_participants(calls)
                for p in participants:
                    cls = self._class_map.get(p)
                    layer = f" <<{cls.spring_layer}>>" if cls and cls.spring_layer else ""
                    lines.append(f"participant {p}{layer}")
                lines.append("")
                for caller, callee, method in calls:
                    lines.append(f"{caller} -> {callee}: {method}()")
                    lines.append(f"{callee} --> {caller}: return")
            else:
                lines.extend(self._plantuml_all_calls())
        else:
            lines.extend(self._plantuml_all_calls())

        lines.append("@enduml")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Call tracing
    # ------------------------------------------------------------------

    def _trace_calls(self, class_name: str, method_name: str,
                     depth: int, visited: set = None) -> List[Tuple[str, str, str]]:
        if visited is None:
            visited = set()
        if depth >= self.max_depth:
            return []

        key = f"{class_name}.{method_name}"
        if key in visited:
            return []
        visited.add(key)

        cls = self._class_map.get(class_name)
        if not cls:
            return []

        method = next((m for m in cls.methods if m.name == method_name), None)
        if not method:
            return []

        result = []
        for call in method.calls:
            parts = call.rsplit(".", 1)
            if len(parts) == 2:
                callee_name, callee_method = parts
                if callee_name in self._class_map:
                    result.append((class_name, callee_name, callee_method))
                    result.extend(self._trace_calls(callee_name, callee_method,
                                                    depth + 1, visited))
        return result

    # ------------------------------------------------------------------
    # Fallback: all inter-class calls
    # ------------------------------------------------------------------

    def _mermaid_all_calls(self) -> List[str]:
        lines = []
        # Show controllers calling services, services calling repos
        layer_order = ["controller", "service", "repository", "model"]
        by_layer = self.metadata.classes_by_layer()

        seen_participants = set()
        calls = []

        for cls in self.metadata.classes:
            src_layer = cls.spring_layer or "other"
            for dep_name in self.metadata.dependency_graph.get(cls.name, []):
                dep_cls = self._class_map.get(dep_name)
                if dep_cls and dep_cls.spring_layer != src_layer:
                    seen_participants.add(cls.name)
                    seen_participants.add(dep_name)
                    calls.append((cls.name, dep_name))

        for p in sorted(seen_participants):
            cls = self._class_map.get(p)
            alias = f"{p} [{cls.spring_layer}]" if cls and cls.spring_layer else p
            lines.append(f"    participant {p} as {alias}")

        lines.append("")
        for caller, callee in calls[:30]:  # cap at 30 for readability
            lines.append(f"    {caller}->>+{callee}: call()")
            lines.append(f"    {callee}-->>-{caller}: return")

        return lines

    def _plantuml_all_calls(self) -> List[str]:
        lines = []
        seen_participants = set()
        calls = []

        for cls in self.metadata.classes:
            src_layer = cls.spring_layer or "other"
            for dep_name in self.metadata.dependency_graph.get(cls.name, []):
                dep_cls = self._class_map.get(dep_name)
                if dep_cls and dep_cls.spring_layer != src_layer:
                    seen_participants.add(cls.name)
                    seen_participants.add(dep_name)
                    calls.append((cls.name, dep_name))

        for p in sorted(seen_participants):
            cls = self._class_map.get(p)
            layer = f" <<{cls.spring_layer}>>" if cls and cls.spring_layer else ""
            lines.append(f"participant {p}{layer}")

        lines.append("")
        for caller, callee in calls[:30]:
            lines.append(f"{caller} -> {callee}: call()")
            lines.append(f"{callee} --> {caller}: return")

        return lines

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_participants(self, calls: List[Tuple[str, str, str]]) -> List[str]:
        seen = []
        seen_set = set()
        for caller, callee, _ in calls:
            for p in (caller, callee):
                if p not in seen_set:
                    seen.append(p)
                    seen_set.add(p)
        return seen
