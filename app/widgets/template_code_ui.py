"""UI-centric widget starter templates (games, tools, viz, social, display)."""

GAME_CODE = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Catch Game</title>
<style>*{margin:0;padding:0}body{background:#1a1a2e;overflow:hidden}canvas{display:block}
#hud{position:absolute;top:10px;left:10px;right:10px;display:flex;justify-content:space-between;color:#eee;font:18px sans-serif}
#start{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#eee;cursor:pointer}
#start h1{font-size:28px;margin-bottom:12px}#start p{opacity:.7}</style></head><body>
<div id="hud"><span id="sc">Score: 0</span><span id="lv">Lives: 3</span></div>
<div id="start"><h1>Catch Game</h1><p>Click to start</p></div><canvas id="c"></canvas>
<script>!function(){var c=document.getElementById("c"),x=c.getContext("2d"),se=document.getElementById("sc"),
le=document.getElementById("lv"),ss=document.getElementById("start"),W,H,obs,score,lives,run,
CL=["#e94560","#0f3460","#533483","#00b4d8"];function rz(){W=c.width=innerWidth;H=c.height=innerHeight}
window.onresize=rz;rz();function sp(){obs.push({x:Math.random()*(W-40)+20,y:-30,r:14+Math.random()*12,
s:1.5+Math.random()*2,cl:CL[Math.random()*CL.length|0]})}function up(){for(var i=obs.length-1;i>=0;i--){
obs[i].y+=obs[i].s;if(obs[i].y-obs[i].r>H){obs.splice(i,1);lives--}}le.textContent="Lives: "+lives;
if(lives<=0){run=false;ss.querySelector("h1").textContent="Game Over: "+score;
ss.querySelector("p").textContent="Click to restart";ss.style.display="flex"}}
function dr(){x.clearRect(0,0,W,H);obs.forEach(function(o){x.beginPath();x.arc(o.x,o.y,o.r,0,Math.PI*2);
x.fillStyle=o.cl;x.fill()})}function lp(){if(!run)return;if(Math.random()<.03)sp();up();dr();
requestAnimationFrame(lp)}c.onclick=function(e){for(var i=obs.length-1;i>=0;i--){var dx=e.clientX-obs[i].x,
dy=e.clientY-obs[i].y;if(Math.sqrt(dx*dx+dy*dy)<obs[i].r+5){obs.splice(i,1);score+=10;
se.textContent="Score: "+score;break}}};function go(){obs=[];score=0;lives=3;run=true;
se.textContent="Score: 0";le.textContent="Lives: 3";ss.style.display="none";lp()}
ss.onclick=go}()</script></body></html>"""

VIZ_CODE = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Chart Widget</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#fafafa;padding:16px}
h2{font-size:18px;margin-bottom:8px}.tb{display:flex;gap:8px;margin-bottom:12px}
.tb button{padding:6px 14px;border:1px solid #ccc;border-radius:4px;background:#fff;cursor:pointer;font-size:13px}
.tb button.a{background:#4361ee;color:#fff;border-color:#4361ee}
canvas{background:#fff;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.08)}</style></head><body>
<h2>Data Visualization</h2><div class="tb"><button class="a" onclick="sc('bar')">Bar</button>
<button onclick="sc('line')">Line</button><button onclick="rnd()">Randomize</button></div>
<canvas id="ch" width="560" height="300"></canvas>
<script>var cv=document.getElementById('ch'),cx=cv.getContext('2d'),
LB=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
CL=['#4361ee','#3a0ca3','#7209b7','#f72585','#4cc9f0','#4895ef','#560bad','#b5179e','#f15bb5','#fee440','#00bbf9','#00f5d4'],
dt=[],ct='bar',ap=0,ai;function rnd(){dt=LB.map(()=>Math.floor(Math.random()*90)+10);ap=0;if(ai)cancelAnimationFrame(ai);an()}
function sc(t){ct=t;document.querySelectorAll('.tb button').forEach(b=>b.classList.toggle('a',b.textContent.toLowerCase().startsWith(t[0])));ap=0;an()}
function an(){ap=Math.min(ap+.04,1);dr(ap);if(ap<1)ai=requestAnimationFrame(an)}
function dr(t){var W=cv.width,H=cv.height,p={t:20,r:20,b:40,l:50},pw=W-p.l-p.r,ph=H-p.t-p.b,mx=Math.max(...dt)||1;
cx.clearRect(0,0,W,H);cx.strokeStyle='#eee';cx.lineWidth=1;for(var g=0;g<=4;g++){var gy=p.t+ph-ph*g/4;
cx.beginPath();cx.moveTo(p.l,gy);cx.lineTo(W-p.r,gy);cx.stroke();cx.fillStyle='#999';cx.font='11px sans-serif';
cx.textAlign='right';cx.fillText(Math.round(mx*g/4),p.l-6,gy+4)}var bw=pw/dt.length;
if(ct==='bar'){dt.forEach((v,i)=>{var x=p.l+i*bw+bw*.15,w=bw*.7,h=v/mx*ph*t,y=p.t+ph-h;
cx.fillStyle=CL[i%CL.length];cx.fillRect(x,y,w,h);cx.fillStyle='#555';cx.font='11px sans-serif';
cx.textAlign='center';cx.fillText(LB[i],x+w/2,H-p.b+16)})}else{cx.beginPath();cx.strokeStyle=CL[0];cx.lineWidth=2.5;
dt.forEach((v,i)=>{var x=p.l+i*bw+bw/2,y=p.t+ph-v/mx*ph*t;i===0?cx.moveTo(x,y):cx.lineTo(x,y)});cx.stroke();
dt.forEach((v,i)=>{var x=p.l+i*bw+bw/2,y=p.t+ph-v/mx*ph*t;cx.beginPath();cx.arc(x,y,4,0,Math.PI*2);
cx.fillStyle=CL[0];cx.fill();cx.fillStyle='#555';cx.font='11px sans-serif';cx.textAlign='center';
cx.fillText(LB[i],x,H-p.b+16)})}}rnd()</script></body></html>"""

SOCIAL_CODE = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Social Widget</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#f0f2f5;
display:flex;align-items:center;justify-content:center;min-height:100vh}
.c{background:#fff;border-radius:12px;padding:20px;max-width:420px;width:100%;box-shadow:0 2px 12px rgba(0,0,0,.08)}
.ch{display:flex;align-items:center;gap:10px;margin-bottom:14px}
.av{width:44px;height:44px;border-radius:50%;background:linear-gradient(135deg,#667eea,#764ba2);
display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:18px}
.nm{font-weight:600;font-size:15px}.hn{font-size:13px;color:#888}
.cb{font-size:15px;line-height:1.55;color:#333;margin-bottom:16px}.hl{color:#4361ee;font-weight:500}
.ts{font-size:12px;color:#aaa;margin-bottom:14px}.dv{height:1px;background:#eee;margin-bottom:12px}
.act{display:flex;justify-content:space-around}
.act button{background:none;border:none;cursor:pointer;display:flex;align-items:center;gap:6px;
font-size:14px;color:#666;padding:6px 12px;border-radius:8px}.act button:hover{background:#f0f2f5}
.act button.lk{color:#e74c3c}.ct{font-weight:600}</style></head><body>
<div class="c"><div class="ch"><div class="av">A</div><div><div class="nm">Alex Rivera</div>
<div class="hn">@alexrivera</div></div></div>
<div class="cb">Just shipped a new <span class="hl">#widget</span> for the platform.
Building in public is the best way to learn &mdash; every mistake is a lesson.</div>
<div class="ts">2:34 PM &middot; Apr 9, 2026</div><div class="dv"></div>
<div class="act"><button onclick="tl(this)"><span>&#9825;</span> <span class="ct" id="lc">12</span></button>
<button onclick="inc('rc')">&#128172; <span class="ct" id="rc">3</span></button>
<button onclick="inc('sc')">&#8635; <span class="ct" id="sc">5</span></button></div></div>
<script>function tl(b){b.classList.toggle('lk');var e=document.getElementById('lc'),v=+e.textContent;
e.textContent=b.classList.contains('lk')?v+1:v-1;b.querySelector('span').textContent=b.classList.contains('lk')?'\\u2665':'\\u2661'}
function inc(id){var e=document.getElementById(id);e.textContent=+e.textContent+1}</script></body></html>"""

TOOL_CODE = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Unit Converter</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#f8f9fa;padding:20px;color:#333}
h2{font-size:20px;margin-bottom:16px;text-align:center}.tabs{display:flex;justify-content:center;gap:6px;margin-bottom:20px}
.tabs button{padding:8px 18px;border:1px solid #dee2e6;border-radius:20px;background:#fff;cursor:pointer;font-size:14px}
.tabs button.a{background:#4361ee;color:#fff;border-color:#4361ee}
.cv{max-width:380px;margin:0 auto;background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 6px rgba(0,0,0,.06)}
.f{margin-bottom:14px}.f label{display:block;font-size:13px;color:#666;margin-bottom:4px}
.f input,.f select{width:100%;padding:10px;border:1px solid #dee2e6;border-radius:8px;font-size:15px}
.f input:focus{outline:none;border-color:#4361ee}.rb{text-align:center;padding:16px;background:#e8f4fd;border-radius:10px;margin-top:12px}
.rb .v{font-size:28px;font-weight:700;color:#4361ee}.rb .l{font-size:13px;color:#666;margin-top:4px}
.sw{display:block;margin:10px auto;background:none;border:none;font-size:22px;cursor:pointer}</style></head><body>
<h2>Unit Converter</h2><div class="tabs"><button class="a" onclick="sm('length')">Length</button>
<button onclick="sm('weight')">Weight</button><button onclick="sm('temp')">Temperature</button></div>
<div class="cv"><div class="f"><label>From</label><select id="fu" onchange="cv()"></select></div>
<div class="f"><label>Value</label><input id="vl" type="number" value="1" oninput="cv()"></div>
<button class="sw" onclick="sw()">&#8645;</button>
<div class="f"><label>To</label><select id="tu" onchange="cv()"></select></div>
<div class="rb"><div class="v" id="rs">-</div><div class="l" id="rl"></div></div></div>
<script>var U={length:{m:1,km:1000,cm:.01,mm:.001,mi:1609.34,yd:.9144,ft:.3048,in:.0254},
weight:{kg:1,g:.001,mg:1e-6,lb:.453592,oz:.0283495,ton:1000},temp:{C:'C',F:'F',K:'K'}},md='length';
function sm(m){md=m;document.querySelectorAll('.tabs button').forEach(b=>b.classList.toggle('a',
b.textContent.toLowerCase().startsWith(m.substring(0,3))));pp();cv()}
function pp(){var k=Object.keys(U[md]);['fu','tu'].forEach((id,i)=>{var s=document.getElementById(id);
s.innerHTML=k.map(v=>'<option value="'+v+'">'+v+'</option>').join('');if(i===1&&k.length>1)s.selectedIndex=1})}
function sw(){var f=document.getElementById('fu'),t=document.getElementById('tu'),tmp=f.value;f.value=t.value;t.value=tmp;cv()}
function cv(){var v=parseFloat(document.getElementById('vl').value)||0,f=document.getElementById('fu').value,
t=document.getElementById('tu').value,r;if(md==='temp'){var c;if(f==='C')c=v;else if(f==='F')c=(v-32)*5/9;else c=v-273.15;
r=t==='C'?c:t==='F'?c*9/5+32:c+273.15}else{r=v*U[md][f]/U[md][t]}
document.getElementById('rs').textContent=isFinite(r)?parseFloat(r.toFixed(6)):'-';
document.getElementById('rl').textContent=f+' to '+t}pp();cv()</script></body></html>"""

DISPLAY_MOD_CODE = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Display Modifier</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#fafafa;padding:16px}
h2{font-size:18px;margin-bottom:12px}.ir{display:flex;gap:8px;margin-bottom:16px}
.ir input{flex:1;padding:10px;border:1px solid #ddd;border-radius:8px;font-size:14px}
.ir button{padding:10px 18px;background:#4361ee;color:#fff;border:none;border-radius:8px;cursor:pointer}
.pv{background:#fff;border-radius:12px;box-shadow:0 1px 6px rgba(0,0,0,.06);overflow:hidden}
.et{padding:16px;border-left:4px solid #1da1f2}.et .s{color:#1da1f2;font-size:12px;font-weight:600;margin-bottom:6px}
.et .a{font-weight:600;font-size:15px}.et .h{font-size:13px;color:#888;margin-bottom:8px}
.et .t{font-size:15px;line-height:1.5;color:#333}
.er{padding:16px;border-left:4px solid #ff4500}.er .s{color:#ff4500;font-size:12px;font-weight:600;margin-bottom:4px}
.er .sr{font-size:13px;color:#888;margin-bottom:6px}.er .ti{font-weight:600;font-size:16px;margin-bottom:6px}
.er .m{font-size:12px;color:#999}
.ey{}.ey .th{width:100%;aspect-ratio:16/9;background:#000;display:flex;align-items:center;justify-content:center}
.ey .pb{width:60px;height:42px;background:rgba(255,0,0,.85);border-radius:10px;display:flex;align-items:center;justify-content:center}
.ey .pb::after{content:'';border-left:18px solid #fff;border-top:10px solid transparent;border-bottom:10px solid transparent;margin-left:4px}
.ey .inf{padding:12px 16px}.ey .inf .ti{font-weight:600;font-size:15px}.ey .inf .ch{font-size:13px;color:#888;margin-top:2px}
.eg{padding:16px;border-left:4px solid #aaa}.eg .u{font-size:13px;color:#4361ee;word-break:break-all}
.eg .s{font-size:12px;color:#888;margin-bottom:4px}</style></head><body>
<h2>Display Modifier</h2><div class="ir">
<input id="ui" type="text" placeholder="Paste a URL..." value="https://twitter.com/user/status/123">
<button onclick="rp()">Preview</button></div><div id="o" class="pv"></div>
<script>var o=document.getElementById('o');function rp(){var u=document.getElementById('ui').value.trim();
if(!u){o.innerHTML='';return}var t=dt(u);o.innerHTML=t==='twitter'?rt(u):t==='reddit'?rr(u):t==='youtube'?ry(u):rg(u)}
function dt(u){if(/twitter\\.com|x\\.com/i.test(u))return'twitter';if(/reddit\\.com/i.test(u))return'reddit';
if(/youtube\\.com|youtu\\.be/i.test(u))return'youtube';return'generic'}
function rt(u){var p=u.replace(/https?:\\/\\/(www\\.)?(twitter|x)\\.com\\//i,'').split('/'),n=p[0]||'user';
return'<div class="et"><div class="s">Twitter / X</div><div class="a">'+e(n)+'</div><div class="h">@'+e(n)+
'</div><div class="t">Preview of tweet content. Actual content fetched via API.</div></div>'}
function rr(u){var m=u.match(/r\\/([^\\/]+)/),s=m?m[1]:'all';
return'<div class="er"><div class="s">Reddit</div><div class="sr">r/'+e(s)+
'</div><div class="ti">Reddit post title preview</div><div class="m">by u/user &middot; 42 upvotes</div></div>'}
function ry(){return'<div class="ey"><div class="th"><div class="pb"></div></div>'+
'<div class="inf"><div class="ti">YouTube Video Preview</div><div class="ch">Channel &middot; 1.2M views</div></div></div>'}
function rg(u){var h='';try{h=new URL(u).hostname}catch(x){h=u}
return'<div class="eg"><div class="s">'+e(h)+'</div><div class="u">'+e(u)+'</div></div>'}
function e(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML}rp()</script></body></html>"""
