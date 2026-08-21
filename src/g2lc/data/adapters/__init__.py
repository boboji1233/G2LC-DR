"""Metadata-only adapters that require legal, user-supplied local dataset paths."""

from g2lc.data.adapters.base import AdapterInspection, AdapterState
from g2lc.data.adapters.registry import adapter_for

__all__ = ["AdapterInspection", "AdapterState", "adapter_for"]
