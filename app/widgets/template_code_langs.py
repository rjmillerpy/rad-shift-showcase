"""Language-showcase widget starter templates (React, C/WASM, Ruby, PHP)."""

REACT_CODE = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>React Widget</title>
<script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#f0f2f5}
#root{max-width:460px;margin:0 auto;padding:20px}</style></head><body><div id="root"></div>
<script type="text/babel">
const{useState,useCallback,useMemo}=React;
function TaskApp(){
  const[tasks,setTasks]=useState([{id:1,text:'Build a widget',done:true},{id:2,text:'Submit for review',done:false},{id:3,text:'Share with community',done:false}]);
  const[input,setInput]=useState('');const[filter,setFilter]=useState('all');
  const add=useCallback(()=>{const t=input.trim();if(!t)return;setTasks(p=>[...p,{id:Date.now(),text:t,done:false}]);setInput('')},[input]);
  const toggle=useCallback(id=>{setTasks(p=>p.map(t=>t.id===id?{...t,done:!t.done}:t))},[]);
  const remove=useCallback(id=>{setTasks(p=>p.filter(t=>t.id!==id))},[]);
  const filtered=useMemo(()=>{if(filter==='active')return tasks.filter(t=>!t.done);if(filter==='done')return tasks.filter(t=>t.done);return tasks},[tasks,filter]);
  const st=useMemo(()=>({total:tasks.length,done:tasks.filter(t=>t.done).length,active:tasks.filter(t=>!t.done).length}),[tasks]);
  const S={box:{background:'#fff',borderRadius:12,padding:20,boxShadow:'0 1px 6px rgba(0,0,0,.06)'},
    title:{fontSize:22,marginBottom:16,textAlign:'center',color:'#222'},
    row:{display:'flex',gap:8,marginBottom:14},inp:{flex:1,padding:'10px 12px',border:'1px solid #ddd',borderRadius:8,fontSize:14,outline:'none'},
    btn:{padding:'10px 18px',background:'#4361ee',color:'#fff',border:'none',borderRadius:8,cursor:'pointer',fontSize:14,fontWeight:600},
    flts:{display:'flex',gap:6,marginBottom:14,justifyContent:'center'},
    fb:{padding:'6px 14px',border:'1px solid #dee2e6',borderRadius:20,background:'#fff',cursor:'pointer',fontSize:13},
    fa:{background:'#4361ee',color:'#fff',borderColor:'#4361ee'},
    item:{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'10px 0',borderBottom:'1px solid #f0f0f0'},
    lbl:{display:'flex',alignItems:'center',gap:10,cursor:'pointer',flex:1},
    cb:{width:18,height:18,cursor:'pointer'},txt:{fontSize:15,color:'#333'},
    dn:{textDecoration:'line-through',color:'#aaa'},rm:{background:'none',border:'none',fontSize:20,color:'#ccc',cursor:'pointer',padding:'0 4px'},
    empty:{textAlign:'center',padding:20,color:'#aaa',fontSize:14}};
  return(<div style={S.box}><h2 style={S.title}>Task Manager</h2>
    <div style={S.row}><input style={S.inp} value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==='Enter'&&add()} placeholder="Add a task..."/>
    <button style={S.btn} onClick={add}>Add</button></div>
    <div style={S.flts}>{['all','active','done'].map(f=>(<button key={f} style={{...S.fb,...(filter===f?S.fa:{})}} onClick={()=>setFilter(f)}>
      {f[0].toUpperCase()+f.slice(1)} ({f==='all'?st.total:f==='active'?st.active:st.done})</button>))}</div>
    <ul style={{listStyle:'none'}}>{filtered.map(t=>(<li key={t.id} style={S.item}>
      <label style={S.lbl}><input type="checkbox" checked={t.done} onChange={()=>toggle(t.id)} style={S.cb}/>
      <span style={{...S.txt,...(t.done?S.dn:{})}}>{t.text}</span></label>
      <button style={S.rm} onClick={()=>remove(t.id)}>&times;</button></li>))}
      {filtered.length===0&&<li style={S.empty}>No tasks here.</li>}</ul></div>)}
ReactDOM.createRoot(document.getElementById('root')).render(<TaskApp/>);
</script></body></html>"""

C_WASM_CODE = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>C/C++ Calculator (WASM Concept)</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:monospace;background:#1e1e1e;color:#d4d4d4;padding:16px}
.header{color:#dcdcaa;font-size:14px;margin-bottom:12px}
.row{display:flex;gap:8px;margin-bottom:8px;align-items:center}
input[type=number]{width:100px;padding:8px;background:#252526;color:#d4d4d4;border:1px solid #3c3c3c;border-radius:4px;font-family:monospace;font-size:14px}
select{padding:8px;background:#252526;color:#d4d4d4;border:1px solid #3c3c3c;border-radius:4px;font-family:monospace}
button{background:#0e639c;color:#fff;border:none;padding:8px 16px;border-radius:4px;cursor:pointer;font-family:monospace}
button:hover{background:#1177bb}
#result{background:#1a1a1a;border:1px solid #3c3c3c;border-radius:4px;padding:12px;margin-top:12px;font-size:16px;min-height:40px}
.note{color:#608b4e;font-size:11px;margin-top:8px}
.src{background:#252526;border:1px solid #3c3c3c;border-radius:4px;padding:10px;margin-top:12px;font-size:12px;white-space:pre;overflow-x:auto;color:#9cdcfe}
</style></head><body>
<div class="header">// C/C++ Calculator (WASM Concept)</div>
<div class="row">
<input type="number" id="a" value="42">
<select id="op"><option value="add">+</option><option value="sub">-</option><option value="mul">*</option><option value="div">/</option><option value="mod">%</option><option value="pow">^</option></select>
<input type="number" id="b" value="7">
<button onclick="calc()">= Compute</button>
</div>
<div id="result">Press Compute...</div>
<div class="note">/* This simulates a C-compiled WASM module in-browser */</div>
<div class="src" id="csrc"></div>
<script>
// Simulated WASM-like module (mirrors what compiled C would export)
const WasmModule = {
  _add: (a,b) => a + b,
  _sub: (a,b) => a - b,
  _mul: (a,b) => a * b,
  _div: (a,b) => b !== 0 ? a / b : NaN,
  _mod: (a,b) => b !== 0 ? a % b : NaN,
  _pow: (a,b) => Math.pow(a, b),
};
function calc() {
  const a = parseFloat(document.getElementById("a").value) || 0;
  const b = parseFloat(document.getElementById("b").value) || 0;
  const op = document.getElementById("op").value;
  const fn = WasmModule["_" + op];
  const r = fn ? fn(a, b) : NaN;
  document.getElementById("result").textContent = isFinite(r) ? a + " " + {add:"+",sub:"-",mul:"*",div:"/",mod:"%",pow:"^"}[op] + " " + b + " = " + r : "Error: division by zero";
}
document.getElementById("csrc").textContent = '#include <math.h>\\n\\ndouble add(double a, double b) { return a + b; }\\ndouble sub(double a, double b) { return a - b; }\\ndouble mul(double a, double b) { return a * b; }\\ndouble divide(double a, double b) { return b != 0 ? a / b : NAN; }\\nint mod(int a, int b) { return b != 0 ? a % b : 0; }\\ndouble power(double a, double b) { return pow(a, b); }';
</script></body></html>"""

RUBY_CODE = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Ruby Interactive</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:monospace;background:#2b1a1a;color:#f0d0d0;padding:16px}
.header{color:#cc342d;font-size:14px;margin-bottom:10px}
.prompt{display:flex;gap:6px;margin-bottom:8px;align-items:center}
.prompt span{color:#cc342d;font-weight:bold}
input{flex:1;padding:8px;background:#1a1010;color:#f0d0d0;border:1px solid #4a2a2a;border-radius:4px;font-family:monospace;font-size:14px}
button{background:#cc342d;color:#fff;border:none;padding:8px 14px;border-radius:4px;cursor:pointer;font-family:monospace}
button:hover{background:#e0453e}
#output{background:#1a1010;border:1px solid #4a2a2a;border-radius:4px;padding:10px;min-height:120px;white-space:pre-wrap;font-size:13px;margin-top:8px;max-height:300px;overflow-y:auto}
.info{color:#888;font-size:11px;margin-top:6px}
</style></head><body>
<div class="header">irb(main):001:0> Ruby Interactive Console</div>
<div class="prompt"><span>irb></span><input id="cmd" value='puts "Hello, Ruby!"' onkeydown="if(event.key==='Enter')run()"><button onclick="run()">Run</button></div>
<div id="output">Welcome to Ruby Interactive (simulated).\nType expressions to evaluate.\n\n</div>
<div class="info">Supported: puts, p, strings, arrays, hashes, math, .methods</div>
<script>
const out = document.getElementById("output");
const env = {name: "World", items: ["apple","banana","cherry"], counter: 0};

function evalRuby(code) {
  code = code.trim();
  if (!code) return "";
  // puts / p
  if (code.startsWith("puts ")) {
    const arg = code.slice(5).trim().replace(/^"|"$/g, '');
    return arg.replace(/#\\{(\\w+)\\}/g, (_, k) => env[k] !== undefined ? env[k] : k) + "\\n=> nil";
  }
  if (code.startsWith("p ")) {
    const arg = code.slice(2).trim();
    return JSON.stringify(arg) + "\\n=> " + JSON.stringify(arg);
  }
  // Array/Hash literals
  if (code.startsWith("[")) return "=> " + code;
  if (code.startsWith("{")) return "=> " + code;
  // String methods
  if (/^".*"\\.(upcase|downcase|reverse|length|chars|split)/.test(code)) {
    const m = code.match(/^"(.*)"\\.(\\w+)/);
    const s = m[1], method = m[2];
    const ops = {upcase: s.toUpperCase(), downcase: s.toLowerCase(), reverse: s.split('').reverse().join(''), length: s.length, chars: JSON.stringify(s.split('')), split: JSON.stringify(s.split(' '))};
    return '=> ' + (ops[method] !== undefined ? JSON.stringify(ops[method]) : '"' + s + '"');
  }
  // Math
  try {
    const r = Function('"use strict"; return (' + code.replace(/\\*\\*/g, '**') + ')')();
    return "=> " + r;
  } catch(_) {}
  return '=> nil  # (unrecognized expression)';
}

function run() {
  const input = document.getElementById("cmd");
  const code = input.value;
  out.textContent += "irb> " + code + "\\n" + evalRuby(code) + "\\n\\n";
  out.scrollTop = out.scrollHeight;
  input.value = "";
  input.focus();
}
</script></body></html>"""

PHP_CODE = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>PHP Form Processor</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#f4f2ff;padding:20px;color:#333}
h2{font-size:18px;margin-bottom:12px;color:#4f3b78}
.card{background:#fff;border-radius:10px;padding:20px;box-shadow:0 1px 6px rgba(0,0,0,.06);max-width:500px;margin:0 auto 16px}
label{display:block;font-size:13px;color:#666;margin-bottom:4px;margin-top:10px}
input,select,textarea{width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;font-size:14px;font-family:inherit}
textarea{resize:vertical;height:60px}
button{margin-top:14px;padding:10px 20px;background:#7b68ae;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px}
button:hover{background:#6a5a99}
#result{margin-top:12px;max-width:500px;margin-left:auto;margin-right:auto}
.success{background:#d4edda;color:#155724;border-radius:8px;padding:14px;font-size:14px}
.data{background:#fff;border-radius:8px;padding:14px;box-shadow:0 1px 4px rgba(0,0,0,.06);margin-top:8px;font-size:13px;font-family:monospace;white-space:pre-wrap}
.tag{display:inline-block;background:#e8e0ff;color:#4f3b78;border-radius:4px;padding:2px 8px;font-size:12px;margin:2px}
</style></head><body>
<h2>&lt;?php&gt; Form Processor</h2>
<div class="card">
<label>Name</label><input id="name" value="Jane Doe">
<label>Email</label><input id="email" type="email" value="jane@example.com">
<label>Subject</label>
<select id="subject"><option>General Inquiry</option><option>Bug Report</option><option>Feature Request</option><option>Support</option></select>
<label>Message</label><textarea id="message">Hello, I have a question about widgets.</textarea>
<label>Priority</label>
<select id="priority"><option>Low</option><option selected>Medium</option><option>High</option><option>Critical</option></select>
<button onclick="submitForm()">Submit (POST)</button>
</div>
<div id="result"></div>
<script>
function submitForm() {
  const data = {
    name: document.getElementById("name").value,
    email: document.getElementById("email").value,
    subject: document.getElementById("subject").value,
    message: document.getElementById("message").value,
    priority: document.getElementById("priority").value,
    timestamp: new Date().toISOString(),
    ip: "127.0.0.1",
    method: "POST",
  };
  // Simulate PHP processing
  const errors = [];
  if (!data.name.trim()) errors.push("Name is required");
  if (!/^[^@]+@[^@]+\\.[^@]+$/.test(data.email)) errors.push("Invalid email");
  if (!data.message.trim()) errors.push("Message is required");
  const result = document.getElementById("result");
  if (errors.length) {
    result.innerHTML = '<div style="background:#f8d7da;color:#842029;border-radius:8px;padding:14px">' + errors.join("<br>") + '</div>';
    return;
  }
  // Simulate $_POST / $_SERVER
  const phpOutput = {
    "_POST": {name: data.name, email: data.email, subject: data.subject, message: data.message, priority: data.priority},
    "_SERVER": {"REQUEST_METHOD": "POST", "REMOTE_ADDR": data.ip, "REQUEST_TIME": data.timestamp},
    "processed": true, "ticket_id": "TKT-" + Math.random().toString(36).substr(2,8).toUpperCase(),
  };
  result.innerHTML = '<div class="success">Form submitted successfully! Ticket: <strong>' + phpOutput.ticket_id + '</strong></div>' +
    '<div class="data">' + JSON.stringify(phpOutput, null, 2) + '</div>';
}
</script></body></html>"""
