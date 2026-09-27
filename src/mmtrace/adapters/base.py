"""Base abstraction for MMTrace input adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from mmtrace.schema.trace import Trace


class AdapterError(ValueError):
    """Raised when an adapter cannot load user-provided input."""


class BaseAdapter(ABC):
    """Minimal adapter interface for converting external input to Trace."""

    name: str

    @abstractmethod
    def can_load(self, path: str | Path) -> bool:
        """Return whether this adapter can load the given path."""

    @abstractmethod
    def load(self, path: str | Path) -> Trace:
        """Load external input as a Trace."""

