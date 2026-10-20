"""Builders for JavaScript framework runtimes (React, Vue)."""

from __future__ import annotations

from app.widgets.compiler_base import _escape

_FRAMEWORK_STYLES = """\
* { margin: 0; padding: 0; box-sizing: border-box; }
.error { color: #f44747; font-family: monospace; padding: 12px; }"""


def _framework_head(css: str | None) -> str:
    """The page up to <body>, shared by the React and Vue builders."""
    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
{_FRAMEWORK_STYLES}
{css or ""}
</style>
</head><body>
"""


def _build_react(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return (
        _framework_head(css)
        + f"""<div id="root"></div>
<script src="https://unpkg.com/react@18/umd/react.development.js"></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
<script>
try {{
  const code = {escaped};
  const transformed = Babel.transform(code, {{ presets: ['react'] }}).code;
  const module = {{ exports: {{}} }};
  const exports = module.exports;
  (new Function('React', 'ReactDOM', 'module', 'exports', transformed))(React, ReactDOM, module, exports);
  const Component = module.exports.default || module.exports;
  if (typeof Component === 'function') {{
    const root = ReactDOM.createRoot(document.getElementById('root'));
    root.render(React.createElement(Component));
  }}
}} catch(e) {{
  document.getElementById('root').innerHTML = '<div class="error">Error: ' + e.message + '</div>';
}}
</script>
</body></html>"""
    )


def _build_vue(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return (
        _framework_head(css)
        + f"""<div id="app"></div>
<script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
<script>
try {{
  const code = {escaped};
  const fn = new Function('Vue', code);
  fn(Vue);
  if (!document.getElementById('app').innerHTML.trim()) {{
    const app = Vue.createApp({{ template: '<div>Vue app loaded.</div>' }});
    app.mount('#app');
  }}
}} catch(e) {{
  document.getElementById('app').innerHTML = '<div class="error">Error: ' + e.message + '</div>';
}}
</script>
</body></html>"""
    )
