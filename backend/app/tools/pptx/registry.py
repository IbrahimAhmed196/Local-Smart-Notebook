"""Bind drawing functions to the ARC-06 layout registry."""
from app.schemas.layouts import LAYOUTS, get_layout

_RENDERERS = {}

def register_renderer(name):
    get_layout(name)  # Require a canonical layout already defined by ARC-06.
    def register(function):
        if name in _RENDERERS:
            raise ValueError(f"Renderer already registered: {name}")
        _RENDERERS[name] = function
        return function
    return register

def validate_renderers():
    expected = {spec.name for spec in LAYOUTS} | {"sources"}
    actual = set(_RENDERERS)
    if actual != expected:
        raise RuntimeError(f"Renderer mismatch: missing={expected - actual}, extra={actual - expected}")
