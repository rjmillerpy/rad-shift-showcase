"""Builders for simulated / transpiled languages — part B (Assembly, VB, Go, Rust, C#)."""

from __future__ import annotations

from app.widgets.compiler_base import _escape, _wrap_runtime


def _build_assembly(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return _wrap_runtime("Assembly", "", _ASM_RUNNER.replace("__CODE__", escaped), css)


_ASM_RUNNER = r"""try {
  const code = __CODE__;
  const lines = code.split('\n').map(l => l.trim()).filter(l => l && !l.startsWith(';'));
  const regs = {eax:0,ebx:0,ecx:0,edx:0,esi:0,edi:0,esp:1024,ebp:0};
  const flags = {zf:false,sf:false};
  const stack = [], output = [], labels = {}, data = {};
  lines.forEach((l,i) => { const m=l.match(/^(\w+):/); if(m) labels[m[1].toLowerCase()]=i;
    const dm=l.match(/^(\w+)\s+db\s+"(.*)"/i); if(dm) data[dm[1].toLowerCase()]=dm[2]; });
  function res(op) { op=op.trim().toLowerCase(); if(regs[op]!==undefined)return regs[op]; if(data[op]!==undefined)return data[op]; if(/^-?\d+$/.test(op))return parseInt(op); if(/^0x[\da-f]+$/i.test(op))return parseInt(op,16); return 0; }
  function set(d,v) { d=d.trim().toLowerCase(); if(regs[d]!==undefined)regs[d]=v; }
  let pc=0,iter=0;
  while(pc<lines.length&&iter<10000) { iter++;
    let l=lines[pc].replace(/;.*$/,'').trim();
    if(!l||l.endsWith(':')) { pc++; continue; }
    l=l.replace(/^\w+:\s*/,''); if(!l){pc++;continue;}
    const p=l.split(/[\s,]+/), inst=p[0].toLowerCase(), a1=p[1]||'', a2=p.slice(2).join(' ')||'';
    if(inst==='mov')set(a1,res(a2));
    else if(inst==='add'){const r=res(a1)+res(a2);set(a1,r);flags.zf=r===0;flags.sf=r<0;}
    else if(inst==='sub'){const r=res(a1)-res(a2);set(a1,r);flags.zf=r===0;flags.sf=r<0;}
    else if(inst==='mul')regs.eax=regs.eax*res(a1);
    else if(inst==='div'){const d=res(a1);if(d){regs.edx=regs.eax%d;regs.eax=Math.floor(regs.eax/d);}}
    else if(inst==='push')stack.push(res(a1));
    else if(inst==='pop')set(a1,stack.pop()||0);
    else if(inst==='cmp'){const r=res(a1)-res(a2);flags.zf=r===0;flags.sf=r<0;}
    else if(inst==='jmp'){const t=labels[a1.toLowerCase()];if(t!==undefined){pc=t;continue;}}
    else if(inst==='je'||inst==='jz'){if(flags.zf){const t=labels[a1.toLowerCase()];if(t!==undefined){pc=t;continue;}}}
    else if(inst==='jne'||inst==='jnz'){if(!flags.zf){const t=labels[a1.toLowerCase()];if(t!==undefined){pc=t;continue;}}}
    else if(inst==='int'){if(regs.eax===4){output.push(data[Object.keys(data)[0]]||'');}else if(regs.eax===1)break;}
    else if(inst==='xor'){const r=res(a1)^res(a2);set(a1,r);flags.zf=r===0;}
    else if(inst==='ret'||inst==='hlt')break;
    pc++;
  }
  if(output.length) output.forEach(o=>print(o));
  else { print('=== Registers ==='); Object.entries(regs).forEach(([r,v])=>print('  '+r.toUpperCase()+' = '+v)); }
} catch(e) { printErr('Error: ' + e.message); }"""


def _build_visual_basic(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return _wrap_runtime("Visual Basic", "", _VB_RUNNER.replace("__CODE__", escaped), css)


_VB_RUNNER = r"""try {
  const code = __CODE__;
  const lines = code.split('\n').map(l => l.trim()).filter(Boolean);
  const vars = {}, output = [], subs = {};
  function ev(e) {
    e = e.trim();
    if (/^"(.*)"$/s.test(e)) return e.slice(1,-1);
    if (/^-?\d+\.?\d*$/.test(e)) return parseFloat(e);
    if (vars[e.toLowerCase()] !== undefined) return vars[e.toLowerCase()];
    if (e.includes('&')) return e.split('&').map(p=>String(ev(p))).join('');
    const m=e.match(/^(.+?)\s*([+\-*/])\s*(.+)$/);
    if(m){const l=ev(m[1]),r=ev(m[3]);return m[2]==='+'?(typeof l==='string'?l+r:l+r):m[2]==='-'?l-r:m[2]==='*'?l*r:r?l/r:0;}
    return e;
  }
  let inSub=null, subLines=[], mainLines=[];
  for (const line of lines) {
    if (/^(?:SUB|FUNCTION)\s+(\w+)/i.test(line)) { inSub=line.match(/^(?:SUB|FUNCTION)\s+(\w+)/i)[1].toLowerCase(); subLines=[]; continue; }
    if (/^END\s+(?:SUB|FUNCTION)/i.test(line)) { if(inSub) subs[inSub]=subLines; inSub=null; continue; }
    if (inSub) { subLines.push(line); continue; }
    mainLines.push(line);
  }
  function exec(lns) {
    for (const line of lns) {
      const t = line.trim();
      let m=t.match(/^(?:MsgBox|Console\.WriteLine\(|Debug\.Print)\s*(.*?)[\)]?$/i);
      if(m){output.push(String(ev(m[1])));continue;}
      m=t.match(/^Dim\s+(\w+)(?:\s+As\s+\w+)?(?:\s*=\s*(.+))?$/i);
      if(m){vars[m[1].toLowerCase()]=m[2]?ev(m[2]):0;continue;}
      m=t.match(/^(\w+)\s*=\s*(.+)$/);
      if(m&&!/^(IF|FOR|DIM)/i.test(t)){vars[m[1].toLowerCase()]=ev(m[2]);continue;}
    }
  }
  exec(mainLines);
  output.forEach(o=>print(o));
  if(!output.length) print('(No output)');
} catch(e) { printErr('Error: ' + e.message); }"""


def _build_golang(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return _wrap_runtime("Go", "", _GO_RUNNER.replace("__CODE__", escaped), css)


_GO_RUNNER = r"""try {
  const code = __CODE__;
  const lines = code.split('\n');
  const output = [], vars = {};
  function ev(e) {
    e = e.trim();
    if (/^"(.*)"$/.test(e)) return e.slice(1,-1);
    if (/^\d+\.?\d*$/.test(e)) return parseFloat(e);
    if (vars[e] !== undefined) return vars[e];
    return e;
  }
  for (const line of lines) {
    const t = line.trim();
    let m = t.match(/^fmt\.Println\((.*)\)$/);
    if (m) { output.push(m[1].split(',').map(a => String(ev(a))).join(' ')); continue; }
    m = t.match(/^fmt\.Printf\("(.*)"\s*(?:,\s*(.*))?\)$/);
    if (m) { let s=m[1]; if(m[2]) { const args=m[2].split(',').map(a=>ev(a)); let i=0; s=s.replace(/%[dvsfq]/g,()=>String(args[i++]||'')); } output.push(s); continue; }
    m = t.match(/^(?:var\s+)?(\w+)\s*:?=\s*(.+)$/);
    if (m && !t.startsWith('package') && !t.startsWith('import') && !t.startsWith('func')) {
      vars[m[1]] = ev(m[2]);
    }
  }
  if (output.length) output.forEach(o => print(o));
  else { print('(No fmt.Print output detected)'); lines.forEach((l,i) => print(String(i+1).padStart(3) + ' | ' + l)); }
} catch(e) { printErr('Error: ' + e.message); }"""


def _build_rust(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return _wrap_runtime("Rust", "", _RUST_RUNNER.replace("__CODE__", escaped), css)


_RUST_RUNNER = r"""try {
  const code = __CODE__;
  const lines = code.split('\n');
  const output = [], vars = {};
  function ev(e) {
    e = e.trim();
    if (/^"(.*)"$/.test(e)) return e.slice(1,-1);
    if (/^\d+\.?\d*$/.test(e)) return parseFloat(e);
    if (vars[e] !== undefined) return vars[e];
    return e;
  }
  for (const line of lines) {
    const t = line.trim().replace(/;$/, '');
    let m = t.match(/^println!\("(.*)"\s*(?:,\s*(.*))?\)$/);
    if (m) {
      let s = m[1];
      const args = m[2] ? m[2].split(',').map(a => ev(a)) : [];
      let i = 0;
      s = s.replace(/\{\}/g, () => i < args.length ? String(args[i++]) : '{}');
      output.push(s);
      continue;
    }
    m = t.match(/^let\s+(?:mut\s+)?(\w+)(?::\s*\w+)?\s*=\s*(.+)$/);
    if (m) { vars[m[1]] = ev(m[2]); }
  }
  if (output.length) output.forEach(o => print(o));
  else { print('(No println! output detected)'); lines.forEach((l,i) => print(String(i+1).padStart(3) + ' | ' + l)); }
} catch(e) { printErr('Error: ' + e.message); }"""


def _build_csharp(code: str, css: str | None = None) -> str:
    escaped = _escape(code)
    return _wrap_runtime("C#", "", _CSHARP_RUNNER.replace("__CODE__", escaped), css)


_CSHARP_RUNNER = r"""try {
  const code = __CODE__;
  const lines = code.split('\n');
  const output = [], vars = {};
  function ev(e) {
    e = e.trim();
    if (/^"(.*)"$/.test(e)) return e.slice(1,-1);
    if (/^\d+\.?\d*f?$/.test(e)) return parseFloat(e);
    if (vars[e] !== undefined) return vars[e];
    if (/^\$"(.*)"$/.test(e)) return e.slice(2,-1).replace(/\{(\w+)\}/g,(_,v)=>vars[v]!==undefined?String(vars[v]):'{'+v+'}');
    return e;
  }
  for (const line of lines) {
    const t = line.trim().replace(/;$/, '');
    let m = t.match(/^Console\.WriteLine\((.*)\)$/);
    if (m) { output.push(String(ev(m[1]))); continue; }
    m = t.match(/^(?:var|int|string|float|double|bool)\s+(\w+)\s*=\s*(.+)$/);
    if (m) { vars[m[1]] = ev(m[2]); }
  }
  if (output.length) output.forEach(o => print(o));
  else { print('(No Console.WriteLine output detected)'); lines.forEach((l,i) => print(String(i+1).padStart(3) + ' | ' + l)); }
} catch(e) { printErr('Error: ' + e.message); }"""
