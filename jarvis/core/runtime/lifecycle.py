"""
Component Lifecycle Contract for JARVIS Application Kernel.
"""

from abc import ABC, abstractmethod
from typing import List, TYPE_CHECKING
from jarvis.core.enums import HealthState
from jarvis.core.contracts.health import HealthStatusContract

if TYPE_CHECKING:
    from jarvis.core.runtime.context import RuntimeContext


class LifecycleComponent(ABC):
    """
    Abstract contract for all components managed by the JARVIS Application Runtime.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for the component."""
        pass

    @property
    def dependencies(self) -> List[str]:
        """
        List of component names that this component depends on.
        Must be initialized and started BEFORE this component.
        """
        return []

    async def initialize(self, context: "RuntimeContext") -> None:
        """
        Initialize component resources, configuration, or state.
        Called during INITIALIZING phase in dependency order.
        """
        pass

    async def start(self) -> None:
        """
        Start component operations or background workers.
        Called during RUNNING transition in dependency order.
        """
        pass

    async def stop(self) -> None:
        """
        Gracefully stop component operations and release resources.
        Called during STOPPING phase in reverse dependency order.
        """
        pass

    async def health(self) -> HealthStatusContract:
        """
        Query component health status.
        """
        return HealthStatusContract(
            component=self.name,
            status=HealthState.HEALTHY,
        )
