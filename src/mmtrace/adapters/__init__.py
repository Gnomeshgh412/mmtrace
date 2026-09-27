"""Input adapters for MMTrace."""

from mmtrace.adapters.base import AdapterError, BaseAdapter
from mmtrace.adapters.browser_use import BrowserUseAdapter
from mmtrace.adapters.generic_json import GenericJSONAdapter

__all__ = ["AdapterError", "BaseAdapter", "BrowserUseAdapter", "GenericJSONAdapter"]
