"""Builders for simulated / transpiled languages — part A (simulated, node, C/C++, TS, BASIC, Fortran, COBOL)."""

from __future__ import annotations

from app.widgets.compiler_base import _escape, _wrap_runtime


def _build_simulated(code: str, language: str, css: str | None = None) -> str:
    """Fallback: display source code in a terminal-style view."""
    escaped = _escape(code)
    return _wrap_runtime(
        language,
        "",
        f"""print('=== {language} (simulated) ===');
print('');
try {{
  const code = {escaped};
  const lines = code.split('\\n');
  lines.forEach((line, i) => {{
    print(String(i + 1).padStart(3) + ' | ' + line);
  }});
  print('');
  print('--- Output ---');
  print('({language} does not have a browser runtime. Showing source code above.)');
}} catch(e) {{ printErr('Error: ' + e.message); }}""",
        css,
    )


def _build_nodejs(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return _wrap_runtime(
        "Node.js",
        "",
        f"""const process = {{ env: {{}}, argv: ['node', 'script.js'], exit: () => {{}}, version: 'v20.0.0' }};
const require = (mod) => {{
  const shims = {{
    'path': {{ join: (...a) => a.join('/'), resolve: (...a) => a.join('/'), basename: (p) => p.split('/').pop() }},
    'fs': {{ readFileSync: () => '(simulated)', writeFileSync: () => {{}}, existsSync: () => false }},
    'os': {{ platform: () => 'browser', hostname: () => 'localhost' }},
    'util': {{ format: (...a) => a.map(String).join(' '), inspect: (o) => JSON.stringify(o, null, 2) }},
  }};
  if (shims[mod]) return shims[mod];
  throw new Error('Module "' + mod + '" not available in browser simulation');
}};
const module = {{ exports: {{}} }};
const exports = module.exports;
const origLog = console.log;
const origErr = console.error;
console.log = (...a) => print(a.map(String).join(' '));
console.error = (...a) => printErr(a.map(String).join(' '));
try {{
  (new Function('require', 'module', 'exports', 'process', 'console',
    {escaped}))(require, module, exports, process, console);
}} catch(e) {{ printErr('Error: ' + e.message); }}
console.log = origLog; console.error = origErr;""",
        css,
    )


def _build_cpp(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return _wrap_runtime(
        "C/C++",
        "https://cdn.jsdelivr.net/npm/JSCPP@2.0.2/dist/JSCPP.js",
        f"""try {{
  const config = {{ stdio: {{ write: function(s) {{ print(s); }} }} }};
  JSCPP.run({escaped}, '', config);
}} catch (e) {{ printErr('Error: ' + e.message); }}""",
        css,
    )


def _build_typescript(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return _wrap_runtime(
        "TypeScript",
        "",
        f"""const _tsScript = document.createElement('script');
_tsScript.src = 'https://cdn.jsdelivr.net/npm/typescript@5/lib/typescript.min.js';
_tsScript.onload = () => {{
  try {{
    const js = ts.transpile({escaped}, {{ target: ts.ScriptTarget.ES2020 }});
    const origLog = console.log;
    const origErr = console.error;
    console.log = (...args) => print(args.map(String).join(' '));
    console.error = (...args) => printErr(args.map(String).join(' '));
    (new Function(js))();
    console.log = origLog;
    console.error = origErr;
  }} catch (e) {{ printErr('Error: ' + e.message); }}
}};
_tsScript.onerror = () => printErr('Failed to load TypeScript compiler');
document.head.appendChild(_tsScript);""",
        css,
    )


def _build_basic(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return _wrap_runtime("BASIC", "", _BASIC_RUNNER.replace("__CODE__", escaped), css)


_BASIC_RUNNER = r"""try {
  const code = __CODE__;
  const lines = code.split('\n').map(l => l.trim()).filter(Boolean);
  const vars = {}, output = [];
  function ev(e) {
    e = e.trim();
    if (/^"(.*)"$/s.test(e)) return e.slice(1,-1);
    if (/^-?\d+\.?\d*$/.test(e)) return parseFloat(e);
    if (vars[e.toUpperCase()] !== undefined) return vars[e.toUpperCase()];
    const m = e.match(/^(.+?)\s*([+\-*/])\s*(.+)$/);
    if (m) { const l=ev(m[1]),r=ev(m[3]); return m[2]==='+'?(typeof l==='string'?l+r:l+r):m[2]==='-'?l-r:m[2]==='*'?l*r:r?l/r:0; }
    return e;
  }
  const parsed = lines.map(l => { const m=l.match(/^(\d+)\s+(.*)$/); return m?{num:parseInt(m[1]),text:m[2]}:{num:0,text:l}; });
  let pc=0, iter=0; const fs=[];
  while(pc<parsed.length && iter<10000) { iter++;
    const {text}=parsed[pc], u=text.toUpperCase();
    let m=text.match(/^PRINT\s+(.*)/i);
    if(m){const raw=m[1],pts=[];let buf='',inS=false;for(let i=0;i<raw.length;i++){const c=raw[i];if(c==='"'){inS=!inS;buf+=c;}else if(c===';'&&!inS){pts.push(buf.trim());buf='';}else buf+=c;}if(buf.trim())pts.push(buf.trim());output.push(pts.map(p=>String(ev(p))).join(''));pc++;continue;}
    m=text.match(/^(?:LET\s+)?(\w+)\s*=\s*(.+)/i);
    if(m&&!u.startsWith('IF')&&!u.startsWith('FOR')&&!u.startsWith('GOTO')){vars[m[1].toUpperCase()]=ev(m[2]);pc++;continue;}
    m=text.match(/^FOR\s+(\w+)\s*=\s*(\S+)\s+TO\s+(\S+)(?:\s+STEP\s+(\S+))?/i);
    if(m){const v=m[1].toUpperCase();vars[v]=ev(m[2]);fs.push({v,end:ev(m[3]),step:m[4]?ev(m[4]):1,line:pc});pc++;continue;}
    if(u.startsWith('NEXT')){if(fs.length){const f=fs[fs.length-1];vars[f.v]+=f.step;if((f.step>0&&vars[f.v]<=f.end)||(f.step<0&&vars[f.v]>=f.end)){pc=f.line+1;continue;}else fs.pop();}pc++;continue;}
    if(u==='END')break;
    pc++;
  }
  output.forEach(o => print(o));
  if(!output.length) print('(No output)');
} catch(e) { printErr('Error: ' + e.message); }"""


def _build_fortran(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return _wrap_runtime("Fortran", "", _FORTRAN_RUNNER.replace("__CODE__", escaped), css)


_FORTRAN_RUNNER = r"""try {
  const code = __CODE__;
  const lines = code.split('\n').map(l => l.trim()).filter(Boolean);
  const vars = {}, output = [];
  function ev(e) {
    e = e.trim();
    if (/^['"](.*)['"]$/s.test(e)) return e.slice(1,-1);
    if (/^-?\d+\.?\d*$/.test(e)) return parseFloat(e);
    if (vars[e.toUpperCase()] !== undefined) return vars[e.toUpperCase()];
    return e;
  }
  let pc=0, iter=0; const ds=[];
  while(pc<lines.length && iter<10000) { iter++;
    const l=lines[pc], u=l.toUpperCase();
    let m=l.match(/^(?:WRITE\s*\(\s*\*\s*,\s*\*\s*\)|PRINT\s*\*)\s*(.+)/i);
    if(m){output.push(m[1].split(',').map(p=>String(ev(p.trim()))).join(' '));pc++;continue;}
    m=l.match(/^(?:INTEGER|REAL|CHARACTER).*::\s*(\w+)\s*=\s*(.+)/i);
    if(m){vars[m[1].toUpperCase()]=ev(m[2]);pc++;continue;}
    m=l.match(/^(\w+)\s*=\s*(.+)$/);
    if(m&&!u.startsWith('IF')&&!u.startsWith('DO')&&!u.startsWith('PROGRAM')&&!u.startsWith('END')){vars[m[1].toUpperCase()]=ev(m[2]);pc++;continue;}
    m=l.match(/^DO\s+(\w+)\s*=\s*(\S+)\s*,\s*(\S+)(?:\s*,\s*(\S+))?/i);
    if(m){const v=m[1].toUpperCase();vars[v]=ev(m[2]);ds.push({v,end:ev(m[3]),step:m[4]?ev(m[4]):1,line:pc});pc++;continue;}
    if(/^END\s*DO/i.test(u)){if(ds.length){const f=ds[ds.length-1];vars[f.v]+=f.step;if((f.step>0&&vars[f.v]<=f.end)||(f.step<0&&vars[f.v]>=f.end)){pc=f.line+1;continue;}else ds.pop();}pc++;continue;}
    if(/^END\s*PROGRAM/i.test(u)||/^STOP/i.test(u))break;
    pc++;
  }
  output.forEach(o => print(o));
  if(!output.length) print('(No output)');
} catch(e) { printErr('Error: ' + e.message); }"""


def _build_cobol(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return _wrap_runtime("COBOL", "", _COBOL_RUNNER.replace("__CODE__", escaped), css)


_COBOL_RUNNER = r"""try {
  const code = __CODE__;
  const lines = code.split('\n').map(l => l.trim()).filter(Boolean);
  const vars = {}, output = [];
  function ev(e) {
    e = e.trim().replace(/\.$/,'');
    if (/^["'](.*)["']$/s.test(e)) return e.slice(1,-1);
    if (/^-?\d+\.?\d*$/.test(e)) return parseFloat(e);
    if (vars[e.toUpperCase()] !== undefined) return vars[e.toUpperCase()];
    return e;
  }
  for (const line of lines) {
    const t = line.replace(/\.$/,'').trim();
    let m = t.match(/^DISPLAY\s+(.*)/i);
    if (m) { output.push(m[1].split(/\s+/).map(p => String(ev(p))).join(' ')); continue; }
    m = t.match(/^MOVE\s+(.+?)\s+TO\s+([\w-]+)/i);
    if (m) { vars[m[2].toUpperCase()] = ev(m[1]); continue; }
    m = t.match(/^COMPUTE\s+([\w-]+)\s*=\s*(.+)/i);
    if (m) { try { vars[m[1].toUpperCase()] = eval(m[2].replace(/[A-Z][A-Z0-9-]*/gi, v => vars[v.toUpperCase()]||0)); } catch(e2) {} continue; }
    m = t.match(/^ADD\s+(\S+)\s+TO\s+([\w-]+)/i);
    if (m) { vars[m[2].toUpperCase()] = (vars[m[2].toUpperCase()]||0) + ev(m[1]); continue; }
    if (/^STOP\s+RUN/i.test(t)) break;
  }
  output.forEach(o => print(o));
  if(!output.length) print('(No output)');
} catch(e) { printErr('Error: ' + e.message); }"""
