"""Shared primitives used by all compiler_* builder modules."""

from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# Shared HTML template
# ---------------------------------------------------------------------------

_TERMINAL_STYLES = """\
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Courier New', monospace; background: #1e1e1e; color: #d4d4d4; }
#output { padding: 12px; white-space: pre-wrap; font-size: 13px; min-height: 100vh; overflow: auto; }
.error { color: #f44747; }
.info { color: #569cd6; }"""


def _wrap_runtime(
    language: str,
    interpreter_url: str,
    runner_js: str,
    css: str | None = None,
) -> str:
    script_tag = f'<script src="{interpreter_url}"></script>' if interpreter_url else ""
    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
{_TERMINAL_STYLES}
{css or ""}
</style>
</head><body>
<div id="output"><span class="info">Loading {language} runtime...</span>
</div>
{script_tag}
<script>
const _out = document.getElementById('output');
function print(msg) {{ _out.textContent += msg + '\\n'; }}
function printErr(msg) {{ _out.innerHTML += '<span class="error">' + msg + '</span>\\n'; }}
_out.textContent = '';
{runner_js}
</script>
</body></html>"""


def _escape(code: str) -> str:
    """JSON-encode user code so it can be safely embedded in JS."""
    return json.dumps(code)
