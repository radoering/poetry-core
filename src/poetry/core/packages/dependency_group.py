from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from poetry.core.packages.dependency import Dependency
    from poetry.core.version.markers import BaseMarker


MAIN_GROUP = "main"


class DependencyGroup:
    def __init__(self, name: str, optional: bool = False) -> None:
        self._name: str = name
        self._optional: bool = optional
        self._dependencies: list[Dependency] = []
        self._poetry_dependencies: list[Dependency] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def dependencies(self) -> list[Dependency]:
        return self._dependencies or self._poetry_dependencies

    @property
    def dependencies_for_locking(self) -> list[Dependency]:
        if not self._poetry_dependencies:
            return self._dependencies
        if not self._dependencies:
            return self._poetry_dependencies

        poetry_dependencies_by_name = defaultdict(list)
        for dep in self._poetry_dependencies:
            poetry_dependencies_by_name[dep.name].append(dep)

        dependencies = []
        for dep in self._dependencies:
            if dep.name in poetry_dependencies_by_name:
                enriched = False
                for poetry_dep in poetry_dependencies_by_name[dep.name]:
                    marker = dep.marker.intersect(poetry_dep.marker)
                    if not marker.is_empty():
                        enriched = True
                        dependencies.append(_enrich_dependency(dep, poetry_dep, marker))
                if not enriched:
                    dependencies.append(dep)
            else:
                dependencies.append(dep)

        return dependencies

    def is_optional(self) -> bool:
        return self._optional

    def add_dependency(self, dependency: Dependency) -> None:
        if not self._dependencies and self._poetry_dependencies:
            self._poetry_dependencies.append(dependency)
        else:
            self._dependencies.append(dependency)

    def add_poetry_dependency(self, dependency: Dependency) -> None:
        self._poetry_dependencies.append(dependency)

    def remove_dependency(self, name: str) -> None:
        from packaging.utils import canonicalize_name

        name = canonicalize_name(name)

        dependencies = []
        for dependency in self.dependencies:
            if dependency.name == name:
                continue
            dependencies.append(dependency)
        self._dependencies = dependencies

        dependencies = []
        for dependency in self._poetry_dependencies:
            if dependency.name == name:
                continue
            dependencies.append(dependency)
        self._poetry_dependencies = dependencies

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DependencyGroup):
            return NotImplemented

        return (
            self._name == other.name
            and set(self._dependencies) == set(other.dependencies)
            and set(self._poetry_dependencies) == set(other._poetry_dependencies)
        )

    def __repr__(self) -> str:
        cls = self.__class__.__name__
        return f"{cls}({self._name}, optional={self._optional})"


def _enrich_dependency(
    project_dependency: Dependency, poetry_dependency: Dependency, marker: BaseMarker
) -> Dependency:
    if (
        project_dependency.source_type is not None
        and poetry_dependency.source_type is not None
        and not poetry_dependency.is_same_source_as(project_dependency)
    ):
        raise ValueError(
            "Cannot enrich dependency with different sources: "
            f"{project_dependency} and {poetry_dependency}"
        )

    constraint = project_dependency.constraint.intersect(poetry_dependency.constraint)
    if constraint.is_empty():
        raise ValueError(
            "Cannot enrich dependency with incompatible constraints: "
            f"{project_dependency} and {poetry_dependency}"
        )

    if project_dependency.source_type is not None:
        from poetry.core.packages.directory_dependency import DirectoryDependency
        from poetry.core.packages.vcs_dependency import VCSDependency

        dependency = project_dependency.clone()
        if isinstance(project_dependency, (DirectoryDependency, VCSDependency)):
            dependency._develop = poetry_dependency._develop  # type: ignore[has-type]
    else:
        dependency = poetry_dependency.with_features(project_dependency.features)

    dependency.constraint = constraint
    dependency.marker = marker

    return dependency
