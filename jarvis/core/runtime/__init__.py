"""
JARVIS Core Runtime Module.
"""

from jarvis.core.runtime.lifecycle import LifecycleComponent
from jarvis.core.runtime.context import RuntimeContext
from jarvis.core.runtime.registry import ComponentRegistry

__all__ = [
    "LifecycleComponent",
    "RuntimeContext",
    "ComponentRegistry",
    "JarvisApplication",
]


def __getattr__(name: str):
    if name == "JarvisApplication":
        from jarvis.core.runtime.application import JarvisApplication

        return JarvisApplication
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
