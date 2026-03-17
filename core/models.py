from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple


@dataclass
class AnnotationMeta:
    name: str
    attributes: Dict[str, str] = field(default_factory=dict)

    def __str__(self):
        return f"@{self.name}"


@dataclass
class FieldMeta:
    name: str
    type: str
    visibility: str                          # public | private | protected | package
    annotations: List[AnnotationMeta] = field(default_factory=list)
    is_static: bool = False
    is_final: bool = False

    def annotation_names(self) -> List[str]:
        return [a.name for a in self.annotations]


@dataclass
class ParameterMeta:
    name: str
    type: str
    annotations: List[AnnotationMeta] = field(default_factory=list)


@dataclass
class MethodMeta:
    name: str
    return_type: str
    visibility: str
    parameters: List[ParameterMeta] = field(default_factory=list)
    annotations: List[AnnotationMeta] = field(default_factory=list)
    calls: List[str] = field(default_factory=list)   # "ClassName.methodName" strings
    is_constructor: bool = False
    is_static: bool = False
    is_abstract: bool = False
    throws: List[str] = field(default_factory=list)
    # Control flow for flowchart generation
    has_if: bool = False
    has_loop: bool = False
    has_try_catch: bool = False

    def annotation_names(self) -> List[str]:
        return [a.name for a in self.annotations]

    def signature(self) -> str:
        params = ", ".join(p.type for p in self.parameters)
        return f"{self.name}({params}): {self.return_type}"


@dataclass
class ClassMeta:
    name: str
    package: str
    class_type: str                          # class | interface | enum | abstract
    filepath: str
    extends: Optional[str] = None
    implements: List[str] = field(default_factory=list)
    annotations: List[AnnotationMeta] = field(default_factory=list)
    fields: List[FieldMeta] = field(default_factory=list)
    methods: List[MethodMeta] = field(default_factory=list)
    spring_layer: Optional[str] = None      # controller | service | repository | model | config | messaging
    inner_classes: List[str] = field(default_factory=list)

    def annotation_names(self) -> List[str]:
        return [a.name for a in self.annotations]

    def fully_qualified_name(self) -> str:
        return f"{self.package}.{self.name}" if self.package else self.name

    def public_methods(self) -> List[MethodMeta]:
        return [m for m in self.methods if m.visibility == "public" and not m.is_constructor]

    def public_fields(self) -> List[FieldMeta]:
        return [f for f in self.fields if f.visibility == "public"]


@dataclass
class RepoMetadata:
    repo_name: str
    local_path: str
    repo_url: Optional[str] = None
    project_type: str = "pure_java"         # pure_java | spring_boot | spring_mvc
    build_system: str = "none"              # maven | gradle | none
    classes: List[ClassMeta] = field(default_factory=list)
    packages: List[str] = field(default_factory=list)
    dependency_graph: Dict[str, List[str]] = field(default_factory=dict)
    layer_summary: Dict[str, int] = field(default_factory=dict)

    def classes_by_layer(self) -> Dict[str, List[ClassMeta]]:
        result: Dict[str, List[ClassMeta]] = {}
        for cls in self.classes:
            layer = cls.spring_layer or "other"
            result.setdefault(layer, []).append(cls)
        return result

    def classes_by_package(self) -> Dict[str, List[ClassMeta]]:
        result: Dict[str, List[ClassMeta]] = {}
        for cls in self.classes:
            result.setdefault(cls.package, []).append(cls)
        return result

    def find_class(self, name: str) -> Optional[ClassMeta]:
        for cls in self.classes:
            if cls.name == name or cls.fully_qualified_name() == name:
                return cls
        return None

    def summary(self) -> str:
        return (
            f"Repo: {self.repo_name} | Type: {self.project_type} | "
            f"Build: {self.build_system} | Classes: {len(self.classes)} | "
            f"Packages: {len(self.packages)} | Layers: {self.layer_summary}"
        )
