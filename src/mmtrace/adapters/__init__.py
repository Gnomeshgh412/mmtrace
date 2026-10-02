"""Input adapters for MMTrace."""

from mmtrace.adapters.base import AdapterError, BaseAdapter
from mmtrace.adapters.browser_use import BrowserUseAdapter
from mmtrace.adapters.generic_json import GenericJSONAdapter
from mmtrace.adapters.holo4 import Holo4Adapter
from mmtrace.adapters.osworld import OSWorldAdapter

__all__ = [
    "AdapterError",
    "BaseAdapter",
    "BrowserUseAdapter",
    "GenericJSONAdapter",
    "Holo4Adapter",
    "OSWorldAdapter",
]
