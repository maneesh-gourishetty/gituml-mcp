import os
import logging
from pathlib import Path
from typing import List, Optional, Dict
import javalang
import javalang.tree as jt

from core.models import (
    AnnotationMeta, FieldMeta, ParameterMeta,
    MethodMeta, ClassMeta, RepoMetadata
)

logger = logging.getLogger(__name__)

# Spring Boot annotation → architecture layer mapping
SPRING_LAYER_MAP: Dict[str, str] = {
    # Controllers
    "RestController":       "controller",
    "Controller":           "controller",
    "RequestMapping":       "controller",
    # Services
    "Service":              "service",
    "Component":            "service",
    "EventListener":        "service",
    # Repositories
    "Repository":           "repository",
    # Messaging
    "KafkaListener":        "messaging",
    "RabbitListener":       "messaging",
    "JmsListener":          "messaging",
    # Models / Entities
    "Entity":               "model",
    "Table":                "model",
    "Document":             "model",    # MongoDB
    "Data":                 "model",    # Lombok @Data
    # Config
    "Configuration":        "config",
    "EnableAutoConfiguration": "config",
    "SpringBootApplication": "config",
    "Bean":                 "config",
    "Scheduled":            "scheduler",
}

VISIBILITY_MAP = {
    "public":    "public",
    "private":   "private",
    "protected": "protected",
    None:        "package",
}


class JavaParser:
    """
    Parses all .java files in a directory tree into ClassMeta objects
    using javalang. Handles classes, interfaces, enums, and abstract classes.
    Detects Spring Boot layers via annotation mapping.
    """

    def __init__(self, skip_test_dirs: bool = True):
        self.skip_test_dirs = skip_test_dirs

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_repo(self, local_path: str) -> RepoMetadata:
        """Parse an entire repo directory into RepoMetadata."""
        path = Path(local_path)
        repo_name = path.name

        java_files = self._collect_java_files(path)
        logger.info(f"Found {len(java_files)} .java files in {repo_name}")

        classes: List[ClassMeta] = []
        for filepath in java_files:
            parsed = self._parse_file(filepath)
            classes.extend(parsed)

        project_type = self._detect_project_type(path, classes)
        build_system = self._detect_build_system(path)
        packages = sorted(set(c.package for c in classes if c.package))
        dependency_graph = self._build_dependency_graph(classes)
        layer_summary = self._build_layer_summary(classes)

        return RepoMetadata(
            repo_name=repo_name,
            local_path=str(path),
            project_type=project_type,
            build_system=build_system,
            classes=classes,
            packages=packages,
            dependency_graph=dependency_graph,
            layer_summary=layer_summary,
        )

    def parse_file(self, filepath: str) -> List[ClassMeta]:
        """Parse a single .java file into one or more ClassMeta objects."""
        return self._parse_file(Path(filepath))

    # ------------------------------------------------------------------
    # File collection
    # ------------------------------------------------------------------

    def _collect_java_files(self, root: Path) -> List[Path]:
        files = []
        skip_dirs = {"test", "tests", "it", "target", "build", ".git", ".idea", "node_modules"}
        for java_file in root.rglob("*.java"):
            parts = set(java_file.parts)
            if self.skip_test_dirs and parts & skip_dirs:
                continue
            files.append(java_file)
        return sorted(files)

    # ------------------------------------------------------------------
    # File parsing
    # ------------------------------------------------------------------

    def _parse_file(self, filepath: Path) -> List[ClassMeta]:
        try:
            source = filepath.read_text(encoding="utf-8", errors="ignore")
            tree = javalang.parse.parse(source)
        except javalang.parser.JavaSyntaxError as e:
            logger.warning(f"Syntax error in {filepath}: {e}")
            return []
        except Exception as e:
            logger.warning(f"Failed to parse {filepath}: {e}")
            return []

        package = tree.package.name if tree.package else ""
        classes = []

        for path, node in tree:
            if isinstance(node, jt.ClassDeclaration):
                classes.append(self._parse_class(node, package, str(filepath), "class"))
            elif isinstance(node, jt.InterfaceDeclaration):
                classes.append(self._parse_class(node, package, str(filepath), "interface"))
            elif isinstance(node, jt.EnumDeclaration):
                classes.append(self._parse_enum(node, package, str(filepath)))
            elif isinstance(node, jt.AnnotationDeclaration):
                classes.append(self._parse_class(node, package, str(filepath), "annotation"))

        return classes

    # ------------------------------------------------------------------
    # Class parsing
    # ------------------------------------------------------------------

    def _parse_class(self, node, package: str, filepath: str, class_type: str) -> ClassMeta:
        annotations = self._parse_annotations(getattr(node, "annotations", []))
        spring_layer = self._detect_spring_layer(annotations)

        # Determine if abstract
        modifiers = getattr(node, "modifiers", set()) or set()
        if "abstract" in modifiers:
            class_type = "abstract"

        # Extends / implements
        extends = None
        if hasattr(node, "extends") and node.extends:
            if isinstance(node.extends, list):
                extends = node.extends[0].name if node.extends else None
            else:
                extends = node.extends.name if node.extends else None

        implements = []
        if hasattr(node, "implements") and node.implements:
            implements = [i.name for i in node.implements]

        # Fields and methods
        fields = self._parse_fields(getattr(node, "fields", []) or [])
        methods = self._parse_methods(getattr(node, "methods", []) or [])

        # Constructors
        constructors = self._parse_constructors(getattr(node, "constructors", []) or [])
        methods = constructors + methods

        return ClassMeta(
            name=node.name,
            package=package,
            class_type=class_type,
            filepath=filepath,
            extends=extends,
            implements=implements,
            annotations=annotations,
            fields=fields,
            methods=methods,
            spring_layer=spring_layer,
        )

    def _parse_enum(self, node, package: str, filepath: str) -> ClassMeta:
        annotations = self._parse_annotations(getattr(node, "annotations", []))
        methods = self._parse_methods(getattr(node, "methods", []) or [])
        # Enum constants become fields
        fields = []
        if hasattr(node, "body") and node.body:
            for constant in getattr(node.body, "constants", []) or []:
                fields.append(FieldMeta(
                    name=constant.name,
                    type=node.name,
                    visibility="public",
                    is_static=True,
                    is_final=True,
                ))

        return ClassMeta(
            name=node.name,
            package=package,
            class_type="enum",
            filepath=filepath,
            annotations=annotations,
            fields=fields,
            methods=methods,
        )

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    def _parse_fields(self, field_declarations) -> List[FieldMeta]:
        fields = []
        for decl in field_declarations:
            visibility = VISIBILITY_MAP.get(
                next((m for m in (decl.modifiers or set()) if m in VISIBILITY_MAP), None),
                "package"
            )
            is_static = "static" in (decl.modifiers or set())
            is_final = "final" in (decl.modifiers or set())
            type_name = self._resolve_type(decl.type)
            annotations = self._parse_annotations(decl.annotations or [])

            for declarator in decl.declarators:
                fields.append(FieldMeta(
                    name=declarator.name,
                    type=type_name,
                    visibility=visibility,
                    annotations=annotations,
                    is_static=is_static,
                    is_final=is_final,
                ))
        return fields

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------

    def _parse_methods(self, method_declarations) -> List[MethodMeta]:
        methods = []
        for decl in method_declarations:
            visibility = VISIBILITY_MAP.get(
                next((m for m in (decl.modifiers or set()) if m in VISIBILITY_MAP), None),
                "package"
            )
            annotations = self._parse_annotations(decl.annotations or [])
            parameters = self._parse_parameters(decl.parameters or [])
            return_type = self._resolve_type(decl.return_type) if decl.return_type else "void"
            throws = [str(e) for e in (decl.throws or [])]
            calls = self._extract_method_calls(decl)
            has_if, has_loop, has_try_catch = self._analyse_control_flow(decl)

            methods.append(MethodMeta(
                name=decl.name,
                return_type=return_type,
                visibility=visibility,
                parameters=parameters,
                annotations=annotations,
                calls=calls,
                throws=throws,
                is_static="static" in (decl.modifiers or set()),
                is_abstract="abstract" in (decl.modifiers or set()),
                has_if=has_if,
                has_loop=has_loop,
                has_try_catch=has_try_catch,
            ))
        return methods

    def _parse_constructors(self, constructor_declarations) -> List[MethodMeta]:
        constructors = []
        for decl in constructor_declarations:
            visibility = VISIBILITY_MAP.get(
                next((m for m in (decl.modifiers or set()) if m in VISIBILITY_MAP), None),
                "package"
            )
            annotations = self._parse_annotations(decl.annotations or [])
            parameters = self._parse_parameters(decl.parameters or [])
            calls = self._extract_method_calls(decl)

            constructors.append(MethodMeta(
                name=decl.name,
                return_type="",
                visibility=visibility,
                parameters=parameters,
                annotations=annotations,
                calls=calls,
                is_constructor=True,
            ))
        return constructors

    def _parse_parameters(self, params) -> List[ParameterMeta]:
        result = []
        for p in params:
            result.append(ParameterMeta(
                name=p.name,
                type=self._resolve_type(p.type),
                annotations=self._parse_annotations(p.annotations or []),
            ))
        return result

    # ------------------------------------------------------------------
    # Annotations
    # ------------------------------------------------------------------

    def _parse_annotations(self, annotations) -> List[AnnotationMeta]:
        result = []
        for ann in annotations:
            attrs = {}
            if ann.element:
                if isinstance(ann.element, list):
                    for elem in ann.element:
                        if hasattr(elem, "name") and hasattr(elem, "value"):
                            attrs[elem.name] = str(elem.value)
                elif hasattr(ann.element, "value"):
                    attrs["value"] = str(ann.element.value)
            result.append(AnnotationMeta(name=ann.name, attributes=attrs))
        return result

    def _detect_spring_layer(self, annotations: List[AnnotationMeta]) -> Optional[str]:
        for ann in annotations:
            layer = SPRING_LAYER_MAP.get(ann.name)
            if layer:
                return layer
        return None

    # ------------------------------------------------------------------
    # Type resolution
    # ------------------------------------------------------------------

    def _resolve_type(self, type_node) -> str:
        if type_node is None:
            return "void"
        if isinstance(type_node, str):
            return type_node
        name = getattr(type_node, "name", "Unknown")
        # Handle generics e.g. List<User>
        args = getattr(type_node, "arguments", None)
        if args:
            inner = ", ".join(self._resolve_type(a.type) for a in args if hasattr(a, "type"))
            return f"{name}<{inner}>" if inner else name
        # Handle arrays
        dims = getattr(type_node, "dimensions", None)
        if dims:
            return name + "[]" * len([d for d in dims if d is not None])
        return name

    # ------------------------------------------------------------------
    # Call extraction (for sequence diagrams)
    # ------------------------------------------------------------------

    def _extract_method_calls(self, method_node) -> List[str]:
        calls = []
        try:
            for _, node in method_node:
                if isinstance(node, jt.MethodInvocation):
                    qualifier = getattr(node, "qualifier", None) or ""
                    member = getattr(node, "member", "") or ""
                    if qualifier and member:
                        calls.append(f"{qualifier}.{member}")
                    elif member:
                        calls.append(member)
        except Exception:
            pass
        return calls

    # ------------------------------------------------------------------
    # Control flow analysis (for flowcharts)
    # ------------------------------------------------------------------

    def _analyse_control_flow(self, method_node):
        has_if = has_loop = has_try_catch = False
        try:
            for _, node in method_node:
                if isinstance(node, (jt.IfStatement,)):
                    has_if = True
                elif isinstance(node, (jt.ForStatement, jt.WhileStatement,
                                       jt.DoStatement, jt.EnhancedForStatement)):
                    has_loop = True
                elif isinstance(node, jt.TryStatement):
                    has_try_catch = True
        except Exception:
            pass
        return has_if, has_loop, has_try_catch

    # ------------------------------------------------------------------
    # Dependency graph
    # ------------------------------------------------------------------

    def _build_dependency_graph(self, classes: List[ClassMeta]) -> Dict[str, List[str]]:
        class_names = {c.name for c in classes}
        graph: Dict[str, List[str]] = {}

        for cls in classes:
            deps = set()
            # From fields
            for field in cls.fields:
                base_type = field.type.split("<")[0].strip()
                if base_type in class_names and base_type != cls.name:
                    deps.add(base_type)
            # From method params and return types
            for method in cls.methods:
                for param in method.parameters:
                    base_type = param.type.split("<")[0].strip()
                    if base_type in class_names and base_type != cls.name:
                        deps.add(base_type)
            # From extends/implements
            if cls.extends and cls.extends in class_names:
                deps.add(cls.extends)
            for iface in cls.implements:
                if iface in class_names:
                    deps.add(iface)

            graph[cls.name] = sorted(deps)
        return graph

    # ------------------------------------------------------------------
    # Project type / build system detection
    # ------------------------------------------------------------------

    def _detect_project_type(self, path: Path, classes: List[ClassMeta]) -> str:
        annotation_names = {a.name for c in classes for a in c.annotations}
        if "SpringBootApplication" in annotation_names:
            return "spring_boot"
        if "Controller" in annotation_names or "RestController" in annotation_names:
            return "spring_mvc"
        return "pure_java"

    def _detect_build_system(self, path: Path) -> str:
        if (path / "pom.xml").exists():
            return "maven"
        if (path / "build.gradle").exists() or (path / "build.gradle.kts").exists():
            return "gradle"
        return "none"

    # ------------------------------------------------------------------
    # Layer summary
    # ------------------------------------------------------------------

    def _build_layer_summary(self, classes: List[ClassMeta]) -> Dict[str, int]:
        summary: Dict[str, int] = {}
        for cls in classes:
            layer = cls.spring_layer or "other"
            summary[layer] = summary.get(layer, 0) + 1
        return summary
