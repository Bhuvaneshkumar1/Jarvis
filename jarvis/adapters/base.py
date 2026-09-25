from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseAdapter(ABC):
    """
    Base Adapter interface enforcing Rule 17.
    All external service integrations (Telegram, Obsidian, Voice, Vision, LLM) inherit from BaseAdapter.
    """

    @abstractmethod
    def initialize(self) -> bool:
        """Initialize adapter connection/config."""
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Return adapter operational status."""
        pass
