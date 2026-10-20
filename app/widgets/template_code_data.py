"""Data/backend-oriented widget starter templates (API, lambdas, DB)."""

API_CODE = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>API Connector</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#f5f5f5;padding:16px;color:#333}
h2{margin-bottom:12px}.ctrls{display:flex;gap:8px;margin-bottom:16px}
button{padding:8px 16px;border:none;border-radius:6px;background:#4361ee;color:#fff;cursor:pointer}
button:disabled{opacity:.5}.st{padding:8px;border-radius:6px;margin-bottom:12px;font-size:14px}
.st.ld{background:#fff3cd;color:#856404}.st.er{background:#f8d7da;color:#842029}.st.ok{background:#d1e7dd;color:#0f5132}
.cd{background:#fff;border-radius:8px;padding:14px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.cd h3{font-size:15px;margin-bottom:4px}.cd p{font-size:13px;color:#666}</style></head><body>
<h2>API Connector</h2><div class="ctrls"><button onclick="fd('posts')">Posts</button>
<button onclick="fd('users')">Users</button><button onclick="fd('todos')">Todos</button></div>
<div id="st" class="st ok">Ready</div><div id="r"></div>
<script>var B='https://jsonplaceholder.typicode.com',sE=document.getElementById('st'),rE=document.getElementById('r');
async function fd(res){sE.className='st ld';sE.textContent='Loading '+res+'...';rE.innerHTML='';
document.querySelectorAll('button').forEach(b=>b.disabled=true);try{var r=await fetch(B+'/'+res+'?_limit=10');
if(!r.ok)throw new Error('HTTP '+r.status);var d=await r.json();sE.className='st ok';
sE.textContent='Loaded '+d.length+' '+res;rE.innerHTML=d.map(function(i){
if(res==='posts')return'<div class="cd"><h3>'+esc(i.title)+'</h3><p>'+esc(i.body)+'</p></div>';
if(res==='users')return'<div class="cd"><h3>'+esc(i.name)+'</h3><p>'+esc(i.email)+'</p></div>';
return'<div class="cd"><h3>'+(i.completed?'&#9745;':'&#9744;')+' '+esc(i.title)+'</h3></div>'}).join('')}
catch(e){sE.className='st er';sE.textContent='Error: '+e.message}finally{
document.querySelectorAll('button').forEach(b=>b.disabled=false)}}
function esc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML}</script></body></html>"""

LAMBDA_CODE_PY = """<!DOCTYPE html>
<html><head><style>
body { font-family: monospace; background: #1e1e1e; color: #d4d4d4; padding: 16px; margin: 0; }
.header { color: #569cd6; font-size: 14px; margin-bottom: 8px; }
textarea { width: 100%; height: 80px; background: #252526; color: #d4d4d4; border: 1px solid #3c3c3c; border-radius: 4px; padding: 8px; font-family: monospace; font-size: 13px; resize: none; }
button { background: #0e639c; color: #fff; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin: 8px 0; font-size: 13px; }
button:hover { background: #1177bb; }
#output { background: #1a1a1a; border: 1px solid #3c3c3c; border-radius: 4px; padding: 8px; min-height: 60px; white-space: pre-wrap; font-size: 13px; }
.label { color: #9cdcfe; font-size: 12px; margin: 4px 0; }
</style></head><body>
<div class="header">\u26a1 Lambda Function</div>
<div class="label">Input (JSON):</div>
<textarea id="input">{"name": "World", "count": 3}</textarea>
<button onclick="runLambda()">\u25b6 Execute</button>
<div class="label">Output:</div>
<div id="output">Click Execute to run...</div>
<script>
// === YOUR LAMBDA FUNCTION ===
function handler(event) {
  const name = event.name || "Unknown";
  const count = event.count || 1;
  const greetings = [];
  for (let i = 0; i < count; i++) {
    greetings.push("Hello, " + name + "! (#" + (i+1) + ")");
  }
  return { statusCode: 200, body: greetings, timestamp: new Date().toISOString() };
}
// === END LAMBDA ===

function runLambda() {
  const out = document.getElementById("output");
  try {
    const input = JSON.parse(document.getElementById("input").value);
    const start = performance.now();
    const result = handler(input);
    const duration = (performance.now() - start).toFixed(2);
    out.textContent = JSON.stringify(result, null, 2) + "\\n\\n\u23f1 " + duration + "ms";
    out.style.borderColor = "#4ec9b0";
  } catch (e) {
    out.textContent = "\u274c Error: " + e.message;
    out.style.borderColor = "#f44747";
  }
}
</script></body></html>"""

LAMBDA_CODE_NODE = """<!DOCTYPE html>
<html><head><style>
body { font-family: monospace; background: #1e1e1e; color: #d4d4d4; padding: 16px; margin: 0; }
.header { color: #68a063; font-size: 14px; margin-bottom: 8px; }
textarea { width: 100%; height: 80px; background: #252526; color: #d4d4d4; border: 1px solid #3c3c3c; border-radius: 4px; padding: 8px; font-family: monospace; font-size: 13px; resize: none; }
button { background: #3c873a; color: #fff; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin: 8px 0; font-size: 13px; }
button:hover { background: #4ea94b; }
#output { background: #1a1a1a; border: 1px solid #3c3c3c; border-radius: 4px; padding: 8px; min-height: 60px; white-space: pre-wrap; font-size: 13px; }
.label { color: #9cdcfe; font-size: 12px; margin: 4px 0; }
</style></head><body>
<div class="header">\u26a1 Node.js Lambda Handler</div>
<div class="label">Event (JSON):</div>
<textarea id="input">{"httpMethod": "GET", "path": "/users", "queryStringParameters": {"limit": "5"}}</textarea>
<button onclick="runLambda()">\u25b6 Invoke</button>
<div class="label">Response:</div>
<div id="output">Click Invoke to run...</div>
<script>
// === exports.handler (Node.js style) ===
const exports = {};
exports.handler = async function(event, context) {
  const method = event.httpMethod || "GET";
  const path = event.path || "/";
  const qs = event.queryStringParameters || {};
  const limit = parseInt(qs.limit) || 10;
  if (path === "/users") {
    const users = [];
    for (let i = 1; i <= limit; i++) users.push({id: i, name: "User " + i});
    return {statusCode: 200, headers: {"Content-Type": "application/json"}, body: JSON.stringify(users)};
  }
  return {statusCode: 404, body: JSON.stringify({error: "Not found: " + path})};
};
// === END HANDLER ===

async function runLambda() {
  const out = document.getElementById("output");
  try {
    const event = JSON.parse(document.getElementById("input").value);
    const ctx = {functionName: "myLambda", memoryLimitInMB: 128, getRemainingTimeInMillis: () => 30000};
    const start = performance.now();
    const result = await exports.handler(event, ctx);
    const duration = (performance.now() - start).toFixed(2);
    let display = "Status: " + result.statusCode + "\\n";
    if (result.headers) display += "Headers: " + JSON.stringify(result.headers) + "\\n";
    display += "Body:\\n" + (typeof result.body === "string" ? JSON.stringify(JSON.parse(result.body), null, 2) : JSON.stringify(result.body, null, 2));
    display += "\\n\\n\u23f1 " + duration + "ms";
    out.textContent = display;
    out.style.borderColor = result.statusCode < 400 ? "#4ec9b0" : "#f44747";
  } catch (e) {
    out.textContent = "\u274c Error: " + e.message;
    out.style.borderColor = "#f44747";
  }
}
</script></body></html>"""

DB_CONNECTOR_CODE = """<!DOCTYPE html>
<html><head><style>
body { font-family: monospace; background: #1e1e1e; color: #d4d4d4; padding: 12px; margin: 0; }
.header { color: #ce9178; font-size: 14px; margin-bottom: 8px; }
textarea { width: 100%; height: 60px; background: #252526; color: #d4d4d4; border: 1px solid #3c3c3c; border-radius: 4px; padding: 8px; font-family: monospace; font-size: 13px; resize: none; }
button { background: #c586c0; color: #fff; border: none; padding: 6px 14px; border-radius: 4px; cursor: pointer; margin: 8px 0; }
table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 12px; }
th { background: #2d2d2d; color: #9cdcfe; padding: 6px 8px; text-align: left; border: 1px solid #3c3c3c; }
td { padding: 6px 8px; border: 1px solid #3c3c3c; }
tr:nth-child(even) { background: #252526; }
.info { color: #608b4e; font-size: 12px; margin-top: 6px; }
</style></head><body>
<div class="header">\U0001f5c4\ufe0f Database Explorer</div>
<textarea id="query">SELECT * FROM users WHERE active = true ORDER BY created_at DESC LIMIT 10</textarea>
<button onclick="runQuery()">\u25b6 Run Query</button>
<div id="result"></div>
<script>
// Simulated in-memory database
const DB = {
  users: [
    {id:1, name:"Alice", email:"alice@example.com", active:true, created_at:"2024-01-15"},
    {id:2, name:"Bob", email:"bob@example.com", active:true, created_at:"2024-02-20"},
    {id:3, name:"Charlie", email:"charlie@example.com", active:false, created_at:"2024-03-10"},
    {id:4, name:"Diana", email:"diana@example.com", active:true, created_at:"2024-04-05"},
  ],
  orders: [
    {id:1, user_id:1, product:"Widget A", amount:29.99, status:"completed"},
    {id:2, user_id:2, product:"Widget B", amount:49.99, status:"pending"},
    {id:3, user_id:1, product:"Widget C", amount:19.99, status:"completed"},
  ]
};

function runQuery() {
  const sql = document.getElementById("query").value.trim();
  const result = document.getElementById("result");
  try {
    const match = sql.match(/SELECT\\s+(.+?)\\s+FROM\\s+(\\w+)/i);
    if (!match) throw new Error("Unsupported query format");
    const table = match[2].toLowerCase();
    if (!DB[table]) throw new Error("Table not found: " + table);
    let rows = [...DB[table]];
    const whereMatch = sql.match(/WHERE\\s+(.+?)(?:\\s+ORDER|\\s+LIMIT|$)/i);
    if (whereMatch) {
      const cond = whereMatch[1].trim();
      const eqMatch = cond.match(/(\\w+)\\s*=\\s*(.+)/);
      if (eqMatch) {
        const field = eqMatch[1];
        let val = eqMatch[2].trim().replace(/'/g, "");
        if (val === "true") val = true;
        if (val === "false") val = false;
        rows = rows.filter(r => String(r[field]) === String(val));
      }
    }
    const limitMatch = sql.match(/LIMIT\\s+(\\d+)/i);
    if (limitMatch) rows = rows.slice(0, parseInt(limitMatch[1]));
    if (rows.length === 0) { result.innerHTML = "<div class=\\"info\\">No results</div>"; return; }
    const cols = Object.keys(rows[0]);
    let html = "<table><tr>" + cols.map(c => "<th>"+c+"</th>").join("") + "</tr>";
    rows.forEach(r => { html += "<tr>" + cols.map(c => "<td>"+r[c]+"</td>").join("") + "</tr>"; });
    html += "</table><div class=\\"info\\">" + rows.length + " row(s) returned</div>";
    result.innerHTML = html;
  } catch (e) { result.innerHTML = "<div style=\\"color:#f44747\\">\u274c " + e.message + "</div>"; }
}
</script></body></html>"""
