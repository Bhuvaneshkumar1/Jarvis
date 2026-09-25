"""
Component Registry & Dependency Resolution for JARVIS Application Kernel.
"""

from collections import deque
from typing import Dict, List, Optional
from jarvis.core.runtime.lifecycle import LifecycleComponent
from jarvis.core.exceptions import (
    DuplicateComponentError,
    MissingDependencyError,
    DependencyCycleError,
)


class ComponentRegistry:
    """
    Authoritative Component Registry for application runtime components.
    Handles component registration, lookup, dependency validation, and ordering.
    """

    def __init__(self) -> None:
        self._components: Dict[str, LifecycleComponent] = {}

    def register(self, component: LifecycleComponent) -> None:
        """
        Register a component in the runtime registry.
        Fails if a component with the same name is already registered.
        """
        if component.name in self._components:
            raise DuplicateComponentError(f"Component with name '{component.name}' is already registered.")
        self._components[component.name] = component

    def get(self, name: str) -> Optional[LifecycleComponent]:
        """Lookup component by name."""
        return self._components.get(name)

    def has(self, name: str) -> bool:
        """Check if component is registered."""
        return name in self._components

    def all_components(self) -> List[LifecycleComponent]:
        """Return list of all registered components."""
        return list(self._components.values())

    def count(self) -> int:
        """Return count of registered components."""
        return len(self._components)

    def clear(self) -> None:
        """Clear all registered components."""
        self._components.clear()

    def validate_dependencies(self) -> None:
        """
        Validate that all dependencies exist and there are no circular dependencies.
        Raises MissingDependencyError or DependencyCycleError.
        """
        for name, comp in self._components.items():
            for dep in comp.dependencies:
                if dep not in self._components:
                    raise MissingDependencyError(f"Component '{name}' depends on missing component '{dep}'.")

        # Trigger topological sort to verify cycle freedom
        self.get_initialization_order()

    def get_initialization_order(self) -> List[LifecycleComponent]:
        """
        Compute deterministic initialization order using topological sort.
        If A depends on B, B is initialized BEFORE A.
        """
        # Validate missing dependencies first
        for name, comp in self._components.items():
            for dep in comp.dependencies:
                if dep not in self._components:
                    raise MissingDependencyError(f"Component '{name}' depends on missing component '{dep}'.")

        # Build in-degree map and adjacency list (dep -> dependent)
        in_degree: Dict[str, int] = {name: 0 for name in self._components}
        dependents_map: Dict[str, List[str]] = {name: [] for name in self._components}

        for name, comp in self._components.items():
            in_degree[name] = len(comp.dependencies)
            for dep in comp.dependencies:
                dependents_map[dep].append(name)

        # Queue nodes with 0 in-degree (components with no dependencies)
        # Use sorted keys for deterministic execution order when multiple components have 0 in-degree
        queue: deque = deque(sorted([name for name, deg in in_degree.items() if deg == 0]))
        ordered_names: List[str] = []

        while queue:
            node = queue.popleft()
            ordered_names.append(node)

            # Collect newly eligible dependents
            newly_eligible = []
            for dependent in dependents_map[node]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    newly_eligible.append(dependent)

            # Sort newly eligible components deterministically before appending to queue
            for name in sorted(newly_eligible):
                queue.append(name)

        if len(ordered_names) < len(self._components):
            remaining = set(self._components.keys()) - set(ordered_names)
            raise DependencyCycleError(f"Circular dependency detected involving components: {sorted(list(remaining))}")

        return [self._components[name] for name in ordered_names]

    def get_shutdown_order(self) -> List[LifecycleComponent]:
        """
        Return component shutdown order (exact reverse of initialization order).
        """
        init_order = self.get_initialization_order()
        return list(reversed(init_order))
