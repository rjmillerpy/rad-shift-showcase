"""
Compile widget source code into executable HTML by wrapping it with the
appropriate browser-based interpreter runtime.

This is the backend equivalent of the frontend ``wrapCodeForBrowser()``
in ``src/lib/widgetRuntimes.ts``.  It produces a complete HTML document
that can be served as ``html_output`` or used with the ``/render`` endpoint.

The per-language builders now live in ``compiler_native``, ``compiler_interpreted``,
``compiler_framework``, ``compiler_simulated`` / ``compiler_simulated_b``, and
``compiler_multi_panel``. This module remains the public entry point so existing
``from app.widgets.compiler import ...`` call sites keep working unchanged.
"""

from __future__ import annotations

from collections.abc import Callable

from app.widgets.compiler_framework import _build_react, _build_vue
from app.widgets.compiler_interpreted import (
    _build_lua,
    _build_php,
    _build_python,
    _build_ruby,
    _build_sql,
)
from app.widgets.compiler_multi_panel import compile_multi_panel
from app.widgets.compiler_native import _build_css, _build_html, _build_javascript
from app.widgets.compiler_simulated import (
    _build_basic,
    _build_cobol,
    _build_cpp,
    _build_fortran,
    _build_nodejs,
    _build_simulated,
    _build_typescript,
)
from app.widgets.compiler_simulated_b import (
    _build_assembly,
    _build_csharp,
    _build_golang,
    _build_rust,
    _build_visual_basic,
)

__all__ = [
    "compile_to_html",
    "compile_multi_panel",
]


# ---------------------------------------------------------------------------
# Dispatch map
# ---------------------------------------------------------------------------


def _build_angular(code: str, css: str | None = None) -> str:
    return _build_simulated(code, "Angular", css)


def _build_svelte(code: str, css: str | None = None) -> str:
    return _build_simulated(code, "Svelte", css)


_RUNTIME_MAP: dict[str, Callable[[str, str | None], str]] = {
    "html": _build_html,
    "javascript": _build_javascript,
    "css": _build_css,
    "typescript": _build_typescript,
    "python": _build_python,
    "ruby": _build_ruby,
    "php": _build_php,
    "sql": _build_sql,
    "lua": _build_lua,
    "c": _build_cpp,
    "cpp": _build_cpp,
    "csharp": _build_csharp,
    "golang": _build_golang,
    "rust": _build_rust,
    "react": _build_react,
    "vue": _build_vue,
    "angular": _build_angular,
    "svelte": _build_svelte,
    "nodejs": _build_nodejs,
    "nextjs": _build_react,  # Next.js treated as React
    "basic": _build_basic,
    "fortran": _build_fortran,
    "cobol": _build_cobol,
    "assembly": _build_assembly,
    "visual_basic": _build_visual_basic,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compile_to_html(code: str, language: str, css: str | None = None) -> str:
    """Wrap user code with the appropriate browser runtime to produce
    executable HTML suitable for use as iframe ``srcdoc``."""
    builder = _RUNTIME_MAP.get(language.lower())
    if builder:
        return builder(code, css)
    return _build_simulated(code, language, css)
