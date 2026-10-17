'use strict';
const $=id=>document.getElementById(id);
const token=new URLSearchParams(location.hash.slice(1)).get('token')||sessionStorage.getItem('androidctl-token')||'';
sessionStorage.setItem('androidctl-token',token);history.replaceState(null,'',location.pathname);
const tiles=new Map();let paused=false,dragged=null;
let order;try{order=JSON.parse(localStorage.getItem('androidctl-order')||'[]');if(!Array.isArray(order))order=[];}catch{order=[];}
function notice(text,error=false){$('notice').textContent=text;$('notice').classList.toggle('error',error);}
async function api(path,data){const response=await fetch(path,{method:data?'POST':'GET',headers:{'X-AndroidCtl-Token':token,...(data?{'Content-Type':'application/json'}:{})},body:data?JSON.stringify(data):undefined});if(!response.ok){const result=await response.json();throw Error(result.error||response.statusText);}return response;}
async function action(serial,action,extra={}){const result=await(await api('/api/action',{serial,action,...extra})).json();notice(result.message||'Device inspection loaded');return result;}
function safely(fn){return async()=>{try{await fn();}catch(e){notice(e.message,true);}};}
function button(parent,label,fn){const b=document.createElement('button');b.textContent=label;b.onclick=safely(fn);parent.append(b);return b;}
function createTile(device){const el=document.createElement('article');el.className='tile';
el.innerHTML='<div class="tile-head" draggable="true"><b class="identity"></b><span class="state"></span></div><div class="meta"></div><div class="screen"><span>Waiting for preview</span><img alt="Android device screen" draggable="false"></div><div class="controls"></div><div class="stats">No frame yet</div>';
const t={el,device,busy:false,url:null,armed:false};const controls=el.querySelector('.controls');
button(controls,'Back',()=>action(device.serial,'key',{key:4})).className='input';button(controls,'Home',()=>action(device.serial,'key',{key:3})).className='input';button(controls,'Apps',()=>action(device.serial,'key',{key:187})).className='input';
const arm=button(controls,'Input OFF',()=>{t.armed=!t.armed;arm.textContent=t.armed?'Input ON':'Input OFF';arm.classList.toggle('armed',t.armed);for(const b of controls.querySelectorAll('.input'))b.disabled=!t.armed;});
for(const b of controls.querySelectorAll('.input'))b.disabled=true;
button(controls,'Focus',()=>el.classList.toggle('focus'));
button(controls,'scrcpy ↗',()=>action(device.serial,'scrcpy'));
button(controls,'Inspect',async()=>{$('details').textContent=JSON.stringify(await action(device.serial,'info'),null,2);$('info').showModal();});
button(controls,'Connect',async()=>{await action(device.serial,'connect');await refresh();});
button(controls,'Disconnect',async()=>{await action(device.serial,'disconnect');await refresh();});
button(controls,'Forget',async()=>{await action(device.serial,'forget');await refresh();});
const head=el.querySelector('.tile-head');head.ondragstart=e=>{dragged=device.serial;e.dataTransfer.setData('text/plain',device.serial);};el.ondragover=e=>e.preventDefault();el.ondrop=e=>{e.preventDefault();if(dragged&&dragged!==device.serial&&tiles.has(dragged)){$('grid').insertBefore(tiles.get(dragged).el,el);order=[...$('grid').children].map(c=>c.dataset.serial);localStorage.setItem('androidctl-order',JSON.stringify(order));}};
el.dataset.serial=device.serial;const img=el.querySelector('img');let start=null;
function point(e){const r=img.getBoundingClientRect();return [Math.max(0,Math.min(img.naturalWidth-1,Math.round((e.clientX-r.left)*img.naturalWidth/r.width))),Math.max(0,Math.min(img.naturalHeight-1,Math.round((e.clientY-r.top)*img.naturalHeight/r.height)))];}
img.onpointerdown=e=>{if(!t.armed||!img.naturalWidth||t.device.state!=='device')return;start=point(e);img.setPointerCapture(e.pointerId);};img.onpointercancel=()=>start=null;img.onpointerup=async e=>{if(!start)return;const first=start;start=null;const end=point(e);try{await action(device.serial,Math.hypot(end[0]-first[0],end[1]-first[1])<15?'tap':'swipe',{points:Math.hypot(end[0]-first[0],end[1]-first[1])<15?first:[...first,...end]});}catch(err){notice(err.message,true);}};
$('grid').append(el);return t;}
async function refresh(){const result=await(await api('/api/devices')).json();const seen=new Set();for(const d of result.devices){seen.add(d.serial);let t=tiles.get(d.serial);if(!t){t=createTile(d);tiles.set(d.serial,t);}t.device=d;t.el.querySelector('.identity').textContent=d.name;t.el.querySelector('.state').textContent=d.state;t.el.querySelector('.state').classList.toggle('online',d.state==='device');t.el.querySelector('.meta').textContent=d.serial+' · '+(d.details||'saved endpoint');}for(const [s,t] of tiles){if(!seen.has(s)){t.el.remove();if(t.url)URL.revokeObjectURL(t.url);tiles.delete(s);}}for(const s of order){if(tiles.has(s))$('grid').append(tiles.get(s).el);}$('count').textContent=result.devices.filter(d=>d.state==='device').length+' online / '+result.devices.length+' devices';$('empty').hidden=tiles.size>0;notice('Inventory updated · '+new Date().toLocaleTimeString());}
async function frame(t){if(t.busy||paused||document.hidden||t.device.state!=='device')return;t.busy=true;const start=performance.now();try{const blob=await(await api('/api/frame?serial='+encodeURIComponent(t.device.serial))).blob();if(!t.el.isConnected)return;const url=URL.createObjectURL(blob);const img=t.el.querySelector('img');img.src=url;if(t.url)URL.revokeObjectURL(t.url);t.url=url;t.el.querySelector('.screen span').textContent='';t.el.querySelector('.stats').textContent=`${new Date().toLocaleTimeString()} · ${Math.round(performance.now()-start)} ms · ${Math.round(blob.size/1024)} KiB`;}catch(e){t.el.querySelector('.stats').textContent='Preview error: '+e.message;}finally{t.busy=false;}}
$('refresh').onclick=safely(refresh);$('pause').onclick=()=>{paused=!paused;$('pause').textContent=paused?'Resume previews':'Pause previews';};$('width').oninput=()=>document.documentElement.style.setProperty('--tile',$('width').value+'px');$('close').onclick=()=>$('info').close();
for(const op of ['save','connect','pair'])$(op).onclick=safely(async()=>{await action($('serial').value.trim(),op,{name:$('name').value.trim()||$('serial').value.trim(),code:$('code').value});$('code').value='';await refresh();});
async function loop(){await Promise.all([...tiles.values()].map(frame));setTimeout(loop,Number($('rate').value));}safely(refresh)();loop();setInterval(()=>{if(!document.hidden)safely(refresh)();},10000);
