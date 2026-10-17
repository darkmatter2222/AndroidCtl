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
el.innerHTML='<div class="tile-head" draggable="true"><b class="identity"></b><span class="state"></span></div><div class="meta"></div><div class="screen"><span>Waiting for preview</span><img alt="Android device screen" draggable="false"></div><div class="controls"></div><div class="stats">No frame yet</div><div class="operation" role="status"></div><div class="managed controls"></div>';
const t={el,device,busy:false,url:null,armed:false,epoch:0,previewPaused:false};const controls=el.querySelector('.controls');
button(controls,'Back',()=>action(device.serial,'key',{key:4})).className='input';button(controls,'Home',()=>action(device.serial,'key',{key:3})).className='input';button(controls,'Apps',()=>action(device.serial,'key',{key:187})).className='input';
const arm=button(controls,'Input OFF',()=>{t.armed=!t.armed;arm.textContent=t.armed?'Input ON':'Input OFF';arm.classList.toggle('armed',t.armed);for(const b of controls.querySelectorAll('.input'))b.disabled=!t.armed;});
for(const b of controls.querySelectorAll('.input'))b.disabled=true;
button(controls,'Focus',()=>el.classList.toggle('focus'));
button(controls,'Open live view',()=>action(device.serial,'scrcpy'));
const advanced=document.createElement('details');advanced.innerHTML='<summary>Device settings</summary><div class="controls"></div>';el.append(advanced);const settings=advanced.querySelector('.controls');
button(settings,'Inspect',async()=>{$('details').textContent=JSON.stringify(await action(device.serial,'info'),null,2);$('info').showModal();});
button(controls,'Connect',async()=>{await action(device.serial,'connect');await refresh();});
button(controls,'Disconnect',async()=>{stopPreview(t,'Disconnecting');await action(device.serial,'disconnect');await refresh();});
const preview=button(controls,'Pause tile',()=>{t.previewPaused=!t.previewPaused;preview.textContent=t.previewPaused?'Resume tile':'Pause tile';if(t.previewPaused)stopPreview(t,'Preview paused');});
const resolution=document.createElement('select');resolution.setAttribute('aria-label','Screen resolution');
for(const [value,label] of [['current','Keep current resolution'],['default','Native default'],['75','75% size'],['50','50% size'],['33','33% size'],['25','25% size']])resolution.add(new Option(label,value));settings.append(resolution);
async function loadDisplay(){const selected=resolution.value;const result=await action(device.serial,'display');resolution.replaceChildren();for(const p of result.profiles)resolution.add(new Option(p.label,p.id));resolution.value=selected;}
t.loadDisplay=loadDisplay;button(settings,'Read resolutions',loadDisplay);
button(settings,'Apply now',async()=>{stopPreview(t,'Changing resolution');await action(device.serial,'resolution',{profile:resolution.value});await loadDisplay();});
button(settings,'Restart',async()=>{if(!confirm('Restart '+device.serial+' with '+resolution.selectedOptions[0].text+'? Pause any automation agent first.'))return;stopPreview(t,'Restarting');await action(device.serial,'restart',{profile:resolution.value});await refresh();});
button(settings,'Forget',async()=>{if(!confirm('Remove this saved connection? Android and its data will stay intact.'))return;await action(device.serial,'forget');await refresh();});
const head=el.querySelector('.tile-head');head.ondragstart=e=>{dragged=device.serial;e.dataTransfer.setData('text/plain',device.serial);};el.ondragover=e=>e.preventDefault();el.ondrop=e=>{e.preventDefault();if(dragged&&dragged!==device.serial&&tiles.has(dragged)){$('grid').insertBefore(tiles.get(dragged).el,el);order=[...$('grid').children].map(c=>c.dataset.serial);localStorage.setItem('androidctl-order',JSON.stringify(order));}};
el.dataset.serial=device.serial;const img=el.querySelector('img');let start=null;
function point(e){const r=img.getBoundingClientRect();return [Math.max(0,Math.min(img.naturalWidth-1,Math.round((e.clientX-r.left)*img.naturalWidth/r.width))),Math.max(0,Math.min(img.naturalHeight-1,Math.round((e.clientY-r.top)*img.naturalHeight/r.height)))];}
img.onpointerdown=e=>{if(!t.armed||!img.naturalWidth||t.device.state!=='device')return;start=point(e);img.setPointerCapture(e.pointerId);};img.onpointercancel=()=>start=null;img.onpointerup=async e=>{if(!start)return;const first=start;start=null;const end=point(e);try{await action(device.serial,Math.hypot(end[0]-first[0],end[1]-first[1])<15?'tap':'swipe',{points:Math.hypot(end[0]-first[0],end[1]-first[1])<15?first:[...first,...end]});}catch(err){notice(err.message,true);}};
$('grid').append(el);return t;}
function stopPreview(t,message){t.epoch++;const img=t.el.querySelector('img');img.removeAttribute('src');if(t.url){URL.revokeObjectURL(t.url);t.url=null;}t.el.querySelector('.screen span').textContent=message;t.el.querySelector('.stats').textContent=message;}
async function refresh(){const result=await(await api('/api/devices')).json();const seen=new Set();for(const d of result.devices){seen.add(d.serial);let t=tiles.get(d.serial);if(!t){t=createTile(d);tiles.set(d.serial,t);}t.device=d;managedControls(t);if(d.state==='device'&&!t.displayLoaded){t.displayLoaded=true;t.loadDisplay().catch(e=>{t.displayLoaded=false;notice(e.message,true);});}for(const b of t.el.querySelectorAll('button')){if(['Open live view','Inspect','Apply now','Restart','Read resolutions'].includes(b.textContent))b.disabled=d.state!=='device';}if(d.state!=='device')stopPreview(t,d.state==='disconnected'?'Disconnected — previews stopped':d.state);const operation=t.el.querySelector('.operation');operation.textContent=d.operation?d.operation.message:'';t.el.querySelector('.identity').textContent=d.name;t.el.querySelector('.state').textContent=d.state;t.el.querySelector('.state').classList.toggle('online',d.state==='device');t.el.querySelector('.meta').textContent=d.serial+' · '+(d.details||'saved endpoint');}for(const [s,t] of tiles){if(!seen.has(s)){t.el.remove();if(t.url)URL.revokeObjectURL(t.url);tiles.delete(s);}}for(const s of order){if(tiles.has(s))$('grid').append(tiles.get(s).el);}$('count').textContent=result.devices.filter(d=>d.state==='device').length+' online / '+result.devices.length+' devices';$('empty').hidden=tiles.size>0;}
async function frame(t){if(t.busy||paused||t.previewPaused||document.hidden||t.device.state!=='device')return;t.busy=true;const epoch=t.epoch;const start=performance.now();try{const blob=await(await api('/api/frame?serial='+encodeURIComponent(t.device.serial))).blob();if(!t.el.isConnected||t.epoch!==epoch||t.device.state!=='device')return;const url=URL.createObjectURL(blob);const img=t.el.querySelector('img');img.src=url;if(t.url)URL.revokeObjectURL(t.url);t.url=url;t.el.querySelector('.screen span').textContent='';t.el.querySelector('.stats').textContent=`${new Date().toLocaleTimeString()} · ${Math.round(performance.now()-start)} ms · ${Math.round(blob.size/1024)} KiB`;}catch(e){if(t.epoch===epoch)t.el.querySelector('.stats').textContent='Preview error: '+e.message;}finally{t.busy=false;}}
$('refresh').onclick=safely(refresh);$('pause').onclick=()=>{paused=!paused;$('pause').textContent=paused?'Resume previews':'Pause previews';};$('width').oninput=()=>document.documentElement.style.setProperty('--tile',$('width').value+'px');$('close').onclick=()=>$('info').close();
async function loop(){const pending=[...tiles.values()];async function worker(){while(pending.length)await frame(pending.shift());}await Promise.all([worker(),worker()]);setTimeout(loop,Number($('rate').value));}safely(refresh)();loop();setInterval(()=>{if(!document.hidden)safely(refresh)();},10000);

async function hostAction(data){const result=await(await api('/api/host-action',data)).json();notice(result.message);await refreshHosts();return result;}
function managedControls(t){const m=t.device.managed,box=t.el.querySelector('.managed');if(!m){box.replaceChildren();return;}const signature=JSON.stringify(m);if(t.managedSignature===signature)return;t.managedSignature=signature;box.replaceChildren();const label=document.createElement('span');label.textContent=`${m.host} / ${m.id} · ${m.state} · ${m.gpu} · ${m.cpus} CPU / ${m.ram} MiB`;box.append(label);
button(box,'Start instance',()=>hostAction({host:m.host,instance:m.id,action:'start'}));
button(box,'Stop instance',async()=>{if(confirm('Stop Android instance '+m.id+' completely? Running apps/agents will be interrupted.')){stopPreview(t,'Stopping instance');await hostAction({host:m.host,instance:m.id,action:'stop'});}});
const more=document.createElement('details');more.innerHTML='<summary>Instance settings</summary>';box.append(more);
const renderer=document.createElement('select');renderer.setAttribute('aria-label','Renderer');renderer.add(new Option('Host GPU (single NVIDIA or single Mesa)','host'));renderer.add(new Option('Software SwANGLE (rollback)','swangle'));more.append(renderer);
button(more,'Set renderer (stopped)',()=>hostAction({host:m.host,instance:m.id,action:'renderer',gpu:renderer.value}));
button(more,'Delete instance',async()=>{const typed=prompt('Delete instance '+m.id+'? Type DELETE '+m.id+' to confirm.');if(typed!=='DELETE '+m.id)return;const erase=confirm('Also permanently erase its Android userdata? OK = erase; Cancel = preserve data.');await hostAction({host:m.host,instance:m.id,action:'delete',confirm:typed,erase_data:erase});});}
let hosts=[],flow=null,hostSnapshot="";
function field(label,key,value='',type='text',hint=''){
 const wrap=document.createElement('label');wrap.textContent=label;
 const input=document.createElement('input');input.name=key;input.type=type;input.value=value;input.required=true;
 if(type==='number'){input.min=1;input.max=65535;}
 wrap.append(input);if(hint){const small=document.createElement('small');small.textContent=hint;wrap.append(small);}
 $('wizard-fields').append(wrap);return input;
}
function selectField(label,key,options,value){
 const wrap=document.createElement('label');wrap.textContent=label;const sel=document.createElement('select');sel.name=key;
 for(const [v,l] of options)sel.add(new Option(l,v));if(value)sel.value=value;wrap.append(sel);$('wizard-fields').append(wrap);return sel;
}
function openFlow(kind,data={}){
 flow={kind,step:0,data};$('servers').close();renderFlow();$('wizard').showModal();
}
function renderFlow(){
 const {kind,step,data:d}=flow;const fields=$('wizard-fields');fields.replaceChildren();$('wizard-error').textContent='';
 $('wizard-progress').textContent=step===0?'Step 1 of 2 · Configure':'Step 2 of 2 · Review';
 $('wizard-back').hidden=step===0;$('wizard-next').disabled=false;$('wizard-next').textContent=step===0?'Review':({device:'Connect device',server:'Save and test connection',create:'Create instance'})[kind];
 $('wizard-title').textContent=({device:'Connect a device',server:'Set up an Android server',create:'Create Android'})[kind];
 $('wizard-description').textContent=({device:'Choose how this device connects. We will build the address for you.',server:'Enter the Linux server running AndroidCtl. Use your normal SSH username.',create:'Create an instance on a configured server. It will appear as a tile when the server inventory refreshes.'})[kind];
 if(step===1){
  const review=document.createElement('dl');
  const rows=kind==='device'?(d.method==='usb'?[['Connection','USB · scan attached devices']]:[['Address',endpoint(d)],['Name',d.name||endpoint(d)],['Action',d.method==='pair'?'Pair, then connect using debugging port':'Connect over ADB']]):kind==='server'?[['Server name',d.id],['SSH connection',d.user+'@'+d.address],['SSH port',d.port],['Device address',d.address]]:[['Server',d.host],['Instance',d.instance],['Configuration',d.ram+' MiB RAM · '+d.cpus+' CPU cores'],['Android image','API '+d.api+' · '+d.profile]];
  for(const [k,v]of rows){const dt=document.createElement('dt');dt.textContent=k;const dd=document.createElement('dd');dd.textContent=v;review.append(dt,dd);}fields.append(review);
  const note=document.createElement('p');note.className='muted';note.textContent=kind==='server'?'Testing uses your existing SSH key and trusted host entry. Start/stop/create also require passwordless sudo for AndroidCtl.':kind==='create'?'Uses an already installed Android SDK image. Creation can take several minutes; track progress in Servers.':'The connection is saved so its tile remains available when disconnected.';fields.append(note);return;
 }
 if(kind==='device'){
  const method=selectField('Connection type','method',[['network','Network device / server instance'],['usb','USB phone'],['pair','Pair a wireless Android phone']],d.method||'network');
  method.onchange=()=>{flow.data={...flow.data,...Object.fromEntries(new FormData($('wizard-form')))};renderFlow();};
  if(method.value==='usb'){const p=document.createElement('p');p.textContent='Plug in your phone, enable USB debugging, and accept the authorization prompt on its screen. Continue to scan.';fields.append(p);return;}
  field('Device IP address or hostname','address',d.address||'','text','Example: 192.168.86.48. Do not include a port.').pattern='[A-Za-z0-9_.-]+';
  field('Debugging port','port',d.port||'15551','number','AndroidCtl instance 01 usually uses 15551. Wireless phones show their debugging port in Settings.');
  const name=field('Display name (optional)','name',d.name||'');name.required=false;
  if(method.value==='pair'){field('Pairing port','pairPort',d.pairPort||'','number','From “Pair device with pairing code” on the phone; different from the debugging port.');field('Six-digit pairing code','code','','password').pattern='[0-9]{6}';}
 }else if(kind==='server'){
  field('Server name','id',d.id||'databrick','text','A short label, e.g. databrick.').pattern='[A-Za-z0-9][A-Za-z0-9_.-]*';
  field('Server IP address or hostname','address',d.address||'','text','Example: 192.168.86.48').pattern='[A-Za-z0-9][A-Za-z0-9_.-]*';
  field('SSH username','user',d.user||'','text','Example: darkmatter2222. Enter only your username.').pattern='[A-Za-z0-9_][A-Za-z0-9_.-]*';
  field('SSH port','port',d.port||'22','number');
 }else{
  if(!hosts.length){fields.textContent='Set up a server first using Servers → Set up server.';$('wizard-next').disabled=true;return;}
  selectField('Android server','host',hosts.map(h=>[h.id,h.id+' · '+h.endpoint_host]),d.host);
  field('Instance number (01–64)','instance',d.instance||'','number','Choose an unused number; scan the server first.').max=64;
  selectField('Resources','preset',[['4096','Balanced · 4 GB RAM / 4 cores'],['2048','Lightweight · 2 GB RAM / 2 cores'],['8192','Large · 8 GB RAM / 8 cores']],d.preset||'4096');
  const extra=document.createElement('details');extra.innerHTML='<summary>Advanced image settings</summary>';fields.append(extra);
  field('Hardware profile','profile',d.profile||'pixel_8_pro');extra.append(fields.lastElementChild);
  field('Android API level','api',d.api||'35','number');extra.append(fields.lastElementChild);
 }
}
function endpoint(d,port=d.port){return d.address+':'+port;}
$('wizard-form').onsubmit=async e=>{
 e.preventDefault();if(!flow)return;
 if(flow.step===0){flow.data={...flow.data,...Object.fromEntries(new FormData(e.target))};if(flow.kind==='create'){flow.data.ram=Number(flow.data.preset);flow.data.cpus=flow.data.ram/1024;}flow.step=1;renderFlow();return;}
 const {kind,data:d}=flow;$('wizard-next').disabled=true;$('wizard-back').disabled=true;$('wizard-close').disabled=true;$('wizard-error').textContent='Working…';
 try{
  if(kind==='device'){
   if(d.method==='usb'){await refresh();notice('Scan complete. If your phone is missing, unlock it and accept USB debugging.');}
   else{if(d.method==='pair')await action(endpoint(d,d.pairPort),'pair',{code:d.code});
    await action(endpoint(d),'save',{name:d.name||endpoint(d)});
    await action(endpoint(d),'connect');await refresh();notice('Connected to '+endpoint(d));}
  }else if(kind==='server'){
   await hostAction({action:'save',id:d.id,target:d.user+'@'+d.address,endpoint_host:d.address,port:Number(d.port)});
   await hostAction({action:'scan',host:d.id});
  }else await hostAction({action:'create',host:d.host,instance:d.instance,ram:d.ram,cpus:d.cpus,api:Number(d.api),profile:d.profile});
  $('wizard').close();if(kind!=='device'){$('servers').showModal();await refreshHosts();}
 }catch(err){$('wizard-error').textContent=err.message;}
 finally{$('wizard-next').disabled=false;$('wizard-back').disabled=false;$('wizard-close').disabled=false;}
};
$('wizard-back').onclick=()=>{flow.step=0;renderFlow();};
$('wizard-close').onclick=()=>$('wizard').close();
$('wizard').addEventListener('cancel',e=>{if($('wizard-close').disabled)e.preventDefault();});
for(const id of ['add','empty-add'])$(id).onclick=()=>openFlow('device');
for(const id of ['server-add','empty-host'])$(id).onclick=()=>openFlow('server');
$('new-instance').onclick=()=>openFlow('create');
$('manage-hosts').onclick=safely(async()=>{await refreshHosts();$('servers').showModal();});
$('servers-close').onclick=()=>$('servers').close();
function hostHelp(message){
 if(/resolve hostname/i.test(message))return 'Check the server IP and username using Edit connection. The SSH target must include both.';
 if(/Permission denied|publickey/i.test(message))return 'SSH login failed. Configure key-based login from this computer to the server.';
 if(/Host key verification/i.test(message))return 'Open a terminal and connect with SSH once to verify and trust this server.';
 if(/sudo|password/i.test(message))return 'Server access works, but AndroidCtl needs passwordless sudo for instance changes.';
 return 'Check that the server is reachable and AndroidCtl is installed. Details are below.';
}
async function refreshHosts(){
 const result=await(await api('/api/hosts')).json();hosts=result.hosts;
 const snapshot=JSON.stringify(hosts);if(snapshot===hostSnapshot)return;hostSnapshot=snapshot;
 const box=$('host-list');box.replaceChildren();
 if(!hosts.length){box.textContent='No servers yet. Add one to manage Android instances.';return;}
 for(const h of hosts){
  const card=document.createElement('section');card.className='server-card';const title=document.createElement('h3');title.textContent=h.id;card.append(title);
  const meta=document.createElement('p');meta.textContent=h.target+' · '+h.instances.length+' instances';card.append(meta);
  const op=h.operation;const state=document.createElement('p');state.className=op?.state==='error'?'error':'muted';
  state.textContent=op?(op.state==='error'?hostHelp(op.message):op.message):'Not tested. Scan to discover instances.';card.append(state);
  if(op){const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent='Operation details';const pre=document.createElement('pre');pre.textContent=[op.message,op.output].filter(Boolean).join('\n');details.append(summary,pre);card.append(details);}
  const controls=document.createElement('div');controls.className='controls';card.append(controls);
  for(const [label,act]of [['Scan instances','scan'],['Performance report','diagnostics']])button(controls,label,()=>hostAction({host:h.id,action:act})).disabled=op?.state==='running';
  button(controls,'Edit connection',()=>{const at=h.target.indexOf('@');openFlow('server',{id:h.id,address:h.endpoint_host,user:at>=0?h.target.slice(0,at):'',port:h.port});}).disabled=op?.state==='running';
  button(controls,'Create Android',()=>openFlow('create',{host:h.id})).disabled=op?.state==='running';
  box.append(card);
 }
}
safely(refreshHosts)();setInterval(()=>{if(!document.hidden)safely(refreshHosts)();},3000);
