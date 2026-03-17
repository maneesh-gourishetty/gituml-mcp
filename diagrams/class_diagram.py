from core.models import RepoMetadata, ClassMeta


VISIBILITY_SYMBOL = {
    "public":    "+",
    "private":   "-",
    "protected": "#",
    "package":   "~",
}


class ClassDiagramBuilder:
    """
    Generates class diagrams from RepoMetadata.
    Outputs both Mermaid classDiagram and PlantUML @startuml formats.
    Includes inheritance, implementation, fields, methods, and Spring layers.
    """

    def __init__(self, metadata: RepoMetadata, max_classes: int = 60):
        self.metadata = metadata
        # Limit to avoid unreadable mega-diagrams
        self.classes = metadata.classes[:max_classes]

    def to_mermaid(self) -> str:
        lines = ["```mermaid", "classDiagram"]

        # Add note about Spring layers if spring_boot
        if self.metadata.project_type in ("spring_boot", "spring_mvc"):
            lines.append(f"    %% Project: {self.metadata.repo_name} ({self.metadata.project_type})")
            lines.append(f"    %% Layers: {self.metadata.layer_summary}")

        lines.append("")

        # Class definitions
        for cls in self.classes:
            lines.append(self._mermaid_class_block(cls))

        # Relationships
        for cls in self.classes:
            lines.extend(self._mermaid_relationships(cls))

        lines.append("```")
        return "\n".join(lines)

    def to_plantuml(self) -> str:
        lines = [
            "@startuml",
            f"' Project: {self.metadata.repo_name}",
            "skinparam classAttributeIconSize 0",
            "skinparam monochrome true",
            "skinparam shadowing false",
            "",
        ]

        # Group by package
        by_package = self.metadata.classes_by_package()
        rendered_classes = {cls.name for cls in self.classes}

        for package, pkg_classes in by_package.items():
            pkg_classes = [c for c in pkg_classes if c.name in rendered_classes]
            if not pkg_classes:
                continue
            if package:
                lines.append(f"package {package} {{")
            for cls in pkg_classes:
                lines.append(self._plantuml_class_block(cls, indent="  " if package else ""))
            if package:
                lines.append("}")
            lines.append("")

        # Relationships
        for cls in self.classes:
            lines.extend(self._plantuml_relationships(cls))

        lines.append("@enduml")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Mermaid helpers
    # ------------------------------------------------------------------

    def _mermaid_class_block(self, cls: ClassMeta) -> str:
        lines = []

        # Class declaration
        class_keyword = {
            "interface": "class",
            "abstract":  "class",
            "enum":      "class",
        }.get(cls.class_type, "class")

        header = f"    {class_keyword} {cls.name}"
        if cls.class_type == "interface":
            header += " {\n        <<interface>>"
        elif cls.class_type == "abstract":
            header += " {\n        <<abstract>>"
        elif cls.class_type == "enum":
            header += " {\n        <<enumeration>>"
        elif cls.spring_layer:
            header += " {\n        <<" + cls.spring_layer + ">>"
        else:
            header += " {"

        lines.append(header)

        # Fields (private only shown with - prefix, limit to 8)
        for field in cls.fields[:8]:
            sym = VISIBILITY_SYMBOL.get(field.visibility, "~")
            static_prefix = "$" if field.is_static else ""
            lines.append(f"        {sym}{static_prefix}{field.type} {field.name}")

        # Methods (limit to 10 public methods to keep diagrams readable)
        public_methods = [m for m in cls.methods if not m.is_constructor][:10]
        for method in public_methods:
            sym = VISIBILITY_SYMBOL.get(method.visibility, "~")
            params = ", ".join(p.type for p in method.parameters)
            static_marker = "$" if method.is_static else ""
            abstract_marker = "*" if method.is_abstract else ""
            lines.append(f"        {sym}{static_marker}{abstract_marker}{method.name}({params}) {method.return_type}")

        lines.append("    }")
        return "\n".join(lines)

    def _mermaid_relationships(self, cls: ClassMeta) -> list:
        lines = []
        rendered = {c.name for c in self.classes}

        if cls.extends and cls.extends in rendered:
            lines.append(f"    {cls.name} --|> {cls.extends} : extends")

        for iface in cls.implements:
            if iface in rendered:
                lines.append(f"    {cls.name} ..|> {iface} : implements")

        # Dependencies from fields
        for field in cls.fields:
            base_type = field.type.split("<")[0].strip()
            if base_type in rendered and base_type != cls.name:
                lines.append(f"    {cls.name} --> {base_type} : {field.name}")

        return lines

    # ------------------------------------------------------------------
    # PlantUML helpers
    # ------------------------------------------------------------------

    def _plantuml_class_block(self, cls: ClassMeta, indent: str = "") -> str:
        lines = []

        # Stereotypes
        stereotype = ""
        if cls.class_type == "interface":
            keyword = "interface"
        elif cls.class_type == "abstract":
            keyword = "abstract class"
        elif cls.class_type == "enum":
            keyword = "enum"
        else:
            keyword = "class"
            if cls.spring_layer:
                stereotype = f" <<{cls.spring_layer}>>"

        lines.append(f"{indent}{keyword} {cls.name}{stereotype} {{")

        # Fields
        for field in cls.fields[:8]:
            sym = VISIBILITY_SYMBOL.get(field.visibility, "~")
            static_mod = "{static} " if field.is_static else ""
            lines.append(f"{indent}  {sym}{static_mod}{field.type} {field.name}")

        if cls.fields and cls.methods:
            lines.append(f"{indent}  ..")

        # Methods
        for method in [m for m in cls.methods if not m.is_constructor][:10]:
            sym = VISIBILITY_SYMBOL.get(method.visibility, "~")
            params = ", ".join(f"{p.type} {p.name}" for p in method.parameters)
            abstract_mod = "{abstract} " if method.is_abstract else ""
            static_mod = "{static} " if method.is_static else ""
            lines.append(f"{indent}  {sym}{abstract_mod}{static_mod}{method.name}({params}): {method.return_type}")

        lines.append(f"{indent}}}")
        return "\n".join(lines)

    def _plantuml_relationships(self, cls: ClassMeta) -> list:
        lines = []
        rendered = {c.name for c in self.classes}

        if cls.extends and cls.extends in rendered:
            lines.append(f"{cls.name} --|> {cls.extends}")

        for iface in cls.implements:
            if iface in rendered:
                lines.append(f"{cls.name} ..|> {iface}")

        for field in cls.fields:
            base_type = field.type.split("<")[0].strip()
            if base_type in rendered and base_type != cls.name:
                lines.append(f'{cls.name} --> {base_type} : "{field.name}"')

        return lines
