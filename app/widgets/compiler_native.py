"""Builders for native browser languages (HTML, JavaScript, CSS)."""

from __future__ import annotations

from app.widgets.compiler_base import _TERMINAL_STYLES, _escape


def _build_html(code: str, css: str | None = None) -> str:
    if not css:
        return code
    if "</head>" in code:
        return code.replace("</head>", f"<style>{css}</style></head>")
    return f"<style>{css}</style>{code}"


def _build_javascript(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<style>
{_TERMINAL_STYLES}
{css or ""}
</style>
</head><body>
<div id="output"></div>
<script>
const _out = document.getElementById('output');
function print(msg) {{ _out.textContent += msg + '\\n'; }}
function printErr(msg) {{ _out.innerHTML += '<span class="error">' + msg + '</span>\\n'; }}
const _origLog = console.log;
const _origErr = console.error;
console.log = (...a) => print(a.map(String).join(' '));
console.error = (...a) => printErr(a.map(String).join(' '));
try {{ (new Function({escaped}))(); }}
catch(e) {{ printErr('Error: ' + e.message); }}
console.log = _origLog; console.error = _origErr;
</script>
</body></html>"""


def _build_css(code: str, css: str | None = None) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{code}</style></head><body>
<div class="demo">
  <h1>CSS Preview</h1>
  <p>This is a paragraph demonstrating your styles.</p>
  <button>A Button</button>
  <div class="box" style="width:100px;height:100px;margin:10px;border:1px solid #ccc"></div>
  <ul><li>Item One</li><li>Item Two</li><li>Item Three</li></ul>
  <input type="text" placeholder="Text input" />
</div>
</body></html>"""
