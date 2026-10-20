"""Builders for CDN-hosted interpreter runtimes (Python, Ruby, PHP, SQL, Lua)."""

from __future__ import annotations

from app.widgets.compiler_base import _escape, _wrap_runtime


def _build_python(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return _wrap_runtime(
        "Python",
        "https://cdn.jsdelivr.net/pyodide/v0.27.5/full/pyodide.js",
        f"""async function main() {{
  try {{
    const pyodide = await loadPyodide();
    pyodide.setStdout({{ batched: (msg) => print(msg) }});
    pyodide.setStderr({{ batched: (msg) => printErr(msg) }});
    await pyodide.runPythonAsync({escaped});
  }} catch (e) {{ printErr('Error: ' + e.message); }}
}}
main();""",
        css,
    )


def _build_ruby(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return _wrap_runtime(
        "Ruby",
        "https://cdn.jsdelivr.net/npm/ruby-head-wasm-wasi@latest/dist/browser.script.iife.js",
        f"""(async () => {{
  try {{
    const rubyCode = {escaped};
    const el = document.createElement('script');
    el.type = 'text/ruby';
    el.textContent = 'require "js"\\n' +
      'original_puts = method(:puts)\\n' +
      'define_method(:puts) do |*args|\\n' +
      '  args.each {{ |a| JS.global[:document].getElementById("output")[:textContent] += a.to_s + "\\\\n" }}\\n' +
      'end\\n' + rubyCode;
    document.body.appendChild(el);
  }} catch (e) {{ printErr('Error: ' + e.message); }}
}})();""",
        css,
    )


def _build_php(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return _wrap_runtime(
        "PHP",
        "https://unpkg.com/php-wasm@8.2/php-web.js",
        f"""(async () => {{
  try {{
    const php = new PHP();
    await php.init();
    const result = await php.run({escaped});
    print(result.stdout || '');
    if (result.stderr) printErr(result.stderr);
  }} catch (e) {{ printErr('Error: ' + e.message); }}
}})();""",
        css,
    )


def _build_sql(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return _wrap_runtime(
        "SQL",
        "https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/sql-wasm.js",
        f"""async function main() {{
  try {{
    const SQL = await initSqlJs({{ locateFile: f => 'https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/' + f }});
    const db = new SQL.Database();
    const statements = {escaped}.split(';').filter(s => s.trim());
    for (const stmt of statements) {{
      try {{
        const result = db.exec(stmt);
        if (result.length) {{
          print(result[0].columns.join(' | '));
          print('-'.repeat(result[0].columns.join(' | ').length));
          result[0].values.forEach(row => print(row.join(' | ')));
        }} else {{ print('OK'); }}
      }} catch (e) {{ printErr('SQL Error: ' + e.message); }}
      print('');
    }}
  }} catch (e) {{ printErr('Error: ' + e.message); }}
}}
main();""",
        css,
    )


def _build_lua(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return _wrap_runtime(
        "Lua",
        "https://cdn.jsdelivr.net/npm/fengari-web@0.1.4/dist/fengari-web.js",
        f"""try {{
  const luaCode = {escaped};
  const el = document.createElement('script');
  el.type = 'application/lua';
  el.textContent = 'js = require "js"\\nlocal document = js.global.document\\nlocal out = document:getElementById("output")\\n' +
    'function print(...)\\n  local args = {{...}}\\n  local s = ""\\n  for i,v in ipairs(args) do s = s .. tostring(v) .. "\\\\t" end\\n' +
    '  out.textContent = out.textContent .. s .. "\\\\n"\\nend\\n' + luaCode;
  document.body.appendChild(el);
}} catch (e) {{ printErr('Error: ' + e.message); }}""",
        css,
    )
