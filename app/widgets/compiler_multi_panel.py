"""Builder for the multi-panel (HTML + CSS + JS + optional compute) widget layout."""

from __future__ import annotations

from app.widgets.compiler_base import _escape

# str.format templates: literal JavaScript/CSS braces are doubled.

# Runs the compute panel client-side with Pyodide.
_PYODIDE_LOADER = """
<script src="https://cdn.jsdelivr.net/pyodide/v0.27.5/full/pyodide.js"></script>
<script>
(async function() {{
  try {{
    const pyodide = await loadPyodide();
    const _capturedOutput = [];
    pyodide.setStdout({{ batched: (msg) => _capturedOutput.push(msg) }});
    pyodide.setStderr({{ batched: (msg) => console.error('[compute]', msg) }});
    await pyodide.runPythonAsync({escaped_compute});
    window.computeResult = {{
      stdout: _capturedOutput.join('\\n'),
      globals: pyodide.globals.toJs ? Object.fromEntries(pyodide.globals.toJs()) : {{}},
    }};
  }} catch (e) {{
    window.computeResult = {{ error: e.message, stdout: '' }};
    console.error('Compute panel error:', e);
  }}
  // Signal that compute is ready, then run user JS
  window.dispatchEvent(new Event('compute-ready'));
}})();
</script>"""

# Runs the compute panel client-side with sql.js.
_SQLJS_LOADER = """
<script src="https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/sql-wasm.js"></script>
<script>
(async function() {{
  try {{
    const SQL = await initSqlJs({{ locateFile: f => 'https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/' + f }});
    const db = new SQL.Database();
    const statements = {escaped_compute}.split(';').filter(s => s.trim());
    const results = [];
    for (const stmt of statements) {{
      try {{
        const r = db.exec(stmt);
        if (r.length) {{
          results.push({{ columns: r[0].columns, rows: r[0].values }});
        }} else {{
          results.push({{ affected: db.getRowsModified() }});
        }}
      }} catch (e) {{
        results.push({{ error: e.message }});
      }}
    }}
    window.computeResult = {{ results: results }};
  }} catch (e) {{
    window.computeResult = {{ error: e.message, results: [] }};
    console.error('Compute panel error:', e);
  }}
  window.dispatchEvent(new Event('compute-ready'));
}})();
</script>"""

# compute_language -> the loader that runs it and fires `compute-ready`.
_COMPUTE_LOADERS: dict[str, str] = {"python": _PYODIDE_LOADER, "sql": _SQLJS_LOADER}

# User JS that waits for the compute panel to finish.
_DEFERRED_JS = """
<script>
window.addEventListener('compute-ready', function() {{
  try {{ (new Function({escaped_js}))(); }}
  catch(e) {{ console.error('JS panel error:', e); }}
}});
</script>"""

# User JS that runs straight away (no compute panel).
_IMMEDIATE_JS = """
<script>
try {{ (new Function({escaped_js}))(); }}
catch(e) {{ console.error('JS panel error:', e); }}
</script>"""

_PAGE = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
{css}
</style>
</head><body>
{html}
{compute_loader}
{js_block}
</body></html>"""


def _compute_loader(compute_panel: str | None, compute_language: str | None) -> str:
    """The <script> that runs the compute panel, or "" when there is none or
    its language has no client-side runtime."""
    template = _COMPUTE_LOADERS.get(compute_language or "")
    if not compute_panel or template is None:
        return ""
    return template.format(escaped_compute=_escape(compute_panel))


def _js_block(js_code: str, waits_for_compute: bool) -> str:
    template = _DEFERRED_JS if waits_for_compute else _IMMEDIATE_JS
    return template.format(escaped_js=_escape(js_code) if js_code else '""')


def compile_multi_panel(
    html_panel: str,
    css_panel: str,
    js_code: str,
    compute_panel: str | None = None,
    compute_language: str | None = None,
) -> str:
    """Combine HTML/CSS/JS panels into a single executable HTML document.

    When ``compute_panel`` is set with ``compute_language="python"``, Pyodide is
    embedded so the compute code runs client-side and exposes its result via
    ``window.computeResult``.  When ``compute_language="sql"``, sql.js is
    embedded instead.
    """
    # With any compute language set, the user JS waits for `compute-ready`.
    waits_for_compute = bool(compute_panel and compute_language)
    return _PAGE.format(
        css=css_panel or "",
        html=html_panel or "",
        compute_loader=_compute_loader(compute_panel, compute_language),
        js_block=_js_block(js_code, waits_for_compute),
    )
