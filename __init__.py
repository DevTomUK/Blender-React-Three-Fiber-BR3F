"""Blender extension entry point.

The whole add-on lives in ``BR3F.py`` — a self-contained single file that also
installs the legacy way (a plain ``.py``) on Blender 3.6–4.1. For the
Extensions platform (Blender 4.2+) this package re-exports its register hooks
so Blender can load it from the manifest.
"""
from .BR3F import register, unregister

__all__ = ["register", "unregister"]
