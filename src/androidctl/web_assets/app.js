'use strict';
const $=id=>document.getElementById(id);
const token=new URLSearchParams(location.hash.slice(1)).get('token')||sessionStorage.getItem('androidctl-token')||'';
sessionStorage.setItem('androidctl-token',token);history.replaceState(null,'',location.pathname);
const tiles=new Map();const opened=new Set();let paused=false,dragged=null;let currentView='catalog',selectedHost='',selectedInstance='',catalogPage=0;
let selection={kind:'root'},section='Summary',devices=[];const collapsed=new Set();
let order;try{order=JSON.parse(localStorage.getItem('androidctl-order')||'[]');if(!Array.isArray(order))order=[];}catch{order=[];}
function notice(text,error=false){$('notice').textContent=text;$('notice').classList.toggle('error',error);}
async function api(path,data){const response=await fetch(path,{method:data?'POST':'GET',headers:{'X-AndroidCtl-Token':token,...(data?{'Content-Type':'application/json'}:{})},body:data?JSON.stringify(data):undefined});if(!response.ok){const result=await response.json();throw Error(result.error||response.statusText);}return response;}
async function action(serial,action,extra={}){const result=await(await api('/api/action',{serial,action,...extra})).json();if(action==='connect')opened.add(serial);notice(result.message||'Device inspection loaded');return result;}
function safely(fn){return async()=>{try{await fn();}catch(e){notice(e.message,true);}};}
function button(parent,label,fn){const b=document.createElement('button');b.textContent=label;b.onclick=safely(fn);parent.append(b);return b;}
function createTile(device){const el=document.createElement('article');el.className='tile';
el.innerHTML='<div class="tile-head" draggable="true"><b class="identity"></b><span class="state"></span></div><div class="meta"></div><div class="screen"><span>Waiting for preview</span><img alt="Android device screen" draggable="false"></div><div class="controls"></div><div class="stats">No frame yet</div><div class="operation" role="status"></div><div class="managed controls"></div>';
const t={el,device,busy:false,url:null,armed:false,epoch:0,previewPaused:false};const controls=el.querySelector('.controls');
button(controls,'Back',()=>action(device.serial,'key',{key:4})).className='input';button(controls,'Home',()=>action(device.serial,'key',{key:3})).className='input';button(controls,'Apps',()=>action(device.serial,'key',{key:187})).className='input';
const arm=button(controls,'Input OFF',()=>{t.armed=!t.armed;arm.textContent=t.armed?'Input ON':'Input OFF';arm.classList.toggle('armed',t.armed);for(const b of controls.querySelectorAll('.input'))b.disabled=!t.armed;});
for(const b of controls.querySelectorAll('.input'))b.disabled=true;
for(const [label,key] of [['Volume −',25],['Volume +',24],['Mute',164],['Screen power',26]])button(controls,label,()=>action(device.serial,'key',{key})).className='device-key';
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
async function refresh(){const result=await(await api('/api/devices')).json();devices=result.devices;const seen=new Set();for(const d of result.devices){if(!opened.has(d.serial))continue;seen.add(d.serial);let t=tiles.get(d.serial);if(!t){t=createTile(d);tiles.set(d.serial,t);}t.device=d;managedControls(t);if(currentView==='live'&&d.state==='device'&&!t.displayLoaded){t.displayLoaded=true;t.loadDisplay().catch(e=>{t.displayLoaded=false;notice(e.message,true);});}for(const b of t.el.querySelectorAll('button')){if(['Open live view','Inspect','Apply now','Restart','Read resolutions'].includes(b.textContent))b.disabled=d.state!=='device';if(b.classList.contains('device-key'))b.disabled=d.state!=='device';}if(d.state!=='device')stopPreview(t,d.state==='disconnected'?'Disconnected — previews stopped':d.state);const operation=t.el.querySelector('.operation');operation.textContent=d.operation?d.operation.message:'';t.el.querySelector('.identity').textContent=d.name;t.el.querySelector('.state').textContent=d.state;t.el.querySelector('.state').classList.toggle('online',d.state==='device');t.el.querySelector('.meta').textContent=d.serial+' · '+(d.managed?'Android: '+d.managed.state+' · ADB: '+d.state:(d.details||'saved endpoint'));}for(const [s,t] of tiles){if(!seen.has(s)){t.el.remove();if(t.url)URL.revokeObjectURL(t.url);tiles.delete(s);}}for(const s of order){if(tiles.has(s))$('grid').append(tiles.get(s).el);}$('count').textContent=result.devices.filter(d=>d.state==='device').length+' online / '+result.devices.length+' devices';$('empty').hidden=tiles.size>0;filterTiles();renderServerNav();if(selection.kind==='controller'||selection.kind==='root'||section==='Console')renderObject();}
async function frame(t){if(currentView!=='live'||t.el.hidden||t.busy||paused||t.previewPaused||document.hidden||t.device.state!=='device')return;t.busy=true;const epoch=t.epoch;const start=performance.now();try{const blob=await(await api('/api/frame?serial='+encodeURIComponent(t.device.serial))).blob();if(currentView!=='live'||t.el.hidden||!t.el.isConnected||t.epoch!==epoch||t.device.state!=='device')return;const url=URL.createObjectURL(blob);const img=t.el.querySelector('img');img.src=url;if(t.url)URL.revokeObjectURL(t.url);t.url=url;t.el.querySelector('.screen span').textContent='';t.el.querySelector('.stats').textContent=`${new Date().toLocaleTimeString()} · ${Math.round(performance.now()-start)} ms · ${Math.round(blob.size/1024)} KiB`;}catch(e){if(t.epoch===epoch)t.el.querySelector('.stats').textContent='Preview error: '+e.message;}finally{t.busy=false;}}
$('refresh').onclick=safely(refresh);$('pause').onclick=()=>{paused=!paused;$('pause').textContent=paused?'Resume previews':'Pause previews';};$('width').oninput=()=>document.documentElement.style.setProperty('--tile',$('width').value+'px');$('close').onclick=()=>$('info').close();
async function loop(){const pending=[...tiles.values()];async function worker(){while(pending.length)await frame(pending.shift());}await Promise.all([worker(),worker()]);setTimeout(loop,Number($('rate').value));}safely(refresh)();loop();setInterval(()=>{if(!document.hidden)safely(refresh)();},10000);

async function hostAction(data){const result=await(await api('/api/host-action',data)).json();notice(result.message);await refreshHosts();return result;}
function managedControls(t){
 const m=t.device.managed,box=t.el.querySelector('.managed');box.replaceChildren();if(m){const label=document.createElement('span');label.textContent='Owner: '+m.host+' / '+m.id+' · Android '+m.state;box.append(label);}
}
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
 if(kind==='create'&&!data.host)throw Error('Select a server first.');
 flow={kind,step:0,data};renderFlow();$('wizard').showModal();
}
function renderFlow(){
 const {kind,step,data:d}=flow;const fields=$('wizard-fields');fields.replaceChildren();$('wizard-error').textContent='';
 $('wizard-progress').textContent=step===0?'Step 1 of 2 · Configure':'Step 2 of 2 · Review';
 $('wizard-back').hidden=step===0;$('wizard-next').disabled=false;$('wizard-next').textContent=step===0?'Review':({device:'Connect device',server:'Save and test connection',create:'Create instance'})[kind];
 $('wizard-title').textContent=({device:'Connect a device',server:'Set up an Android server',create:'Create Android instance'})[kind];
 $('wizard-description').textContent=({device:'Choose how this device connects. We will build the address for you.',server:'Enter the Linux server running AndroidCtl. Use your normal SSH username.',create:'Reserve a persistent identity, disk and ADB port. Android starts only when you choose Start.'})[kind];
 if(step===1){
  const review=document.createElement('dl');
  const rows=kind==='device'?(d.method==='usb'?[['Connection','USB · scan attached devices']]:[['Address',endpoint(d)],['Name',d.name||endpoint(d)],['Action',d.method==='pair'?'Pair, then connect using debugging port':'Connect over ADB']]):kind==='server'?[['Server name',d.id],['SSH connection',d.user+'@'+d.address],['SSH port',d.port],['Device address',d.address]]:[['Server',d.host],['Instance',d.instance],['Configuration',d.ram+' MiB RAM · '+d.cpus+' CPU cores'],['Default resolution',d.display_scale+'% of native size'],['Android image','API '+d.api+' · '+d.profile]];
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
  const identity=field('Display identifier (not the SSH hostname)','id',d.id||'databrick','text','Stable connection identifier.');identity.pattern='[A-Za-z0-9][A-Za-z0-9_.-]*';identity.readOnly=!!d.editing;
  field('Server IP address or hostname','address',d.address||'','text','Example: 192.168.86.48').pattern='[A-Za-z0-9][A-Za-z0-9_.-]*';
  field('SSH username','user',d.user||'','text','Example: darkmatter2222. Enter only your username.').pattern='[A-Za-z0-9_][A-Za-z0-9_.-]*';
  field('SSH port','port',d.port||'22','number');
 }else{
  if(!hosts.length){fields.textContent='Set up a server first using Servers → Set up server.';$('wizard-next').disabled=true;return;}
  const available=hosts.filter(h=>h.id===d.host&&h.inventory_known&&h.operation?.state!=='error'&&h.operation?.state!=='running');
  if(!available.length){fields.textContent='Wait for a successful server scan before creating a new instance. Existing instances are listed under Servers.';$('wizard-next').disabled=true;return;}
  const choice=selectField('Android server','host',available.map(h=>[h.id,h.id+' · '+h.endpoint_host]),d.host||selectedHost);
  const selected=available.find(h=>h.id===choice.value);const used=new Set(selected.instances.map(i=>Number(i.id)));
  const free=Array.from({length:49985},(_,i)=>i+1).find(i=>!used.has(i));
  choice.onchange=()=>{flow.data={...flow.data,...Object.fromEntries(new FormData($('wizard-form'))),instance:''};renderFlow();};
  const existing=document.createElement('p');existing.textContent='Existing instance IDs: '+([...used].map(i=>String(i).padStart(2,'0')).join(', ')||'none')+'. Start these from Servers; creation allocates a different instance.';fields.append(existing);
  if(!free){fields.append('All instance numbers are in use.');$('wizard-next').disabled=true;return;}
  field('Reserved instance ID (1–49985)','instance',d.instance||String(free).padStart(2,'0'),'number','Only unused numbers can be created. Existing instances cannot be overwritten.').max=49985;
  const nickname=field('Instance name (optional)','instance_name',d.instance_name||'','text','Letters, numbers, underscores and hyphens; leave blank to generate.');nickname.required=false;nickname.pattern='[A-Za-z0-9][A-Za-z0-9_.-]*';
  selectField('Resources','preset',[['4096','Balanced · 4 GB RAM / 4 cores'],['2048','Lightweight · 2 GB RAM / 2 cores'],['8192','Large · 8 GB RAM / 8 cores']],d.preset||'4096');
  selectField('Default screen resolution','display_scale',[['25','25% · smallest'],['33','33% · compact'],['50','50% · recommended'],['75','75% · larger'],['100','100% · native']],d.display_scale||localStorage.getItem('androidctl-default-scale')||'50');
  const extra=document.createElement('details');extra.innerHTML='<summary>Advanced image settings</summary>';fields.append(extra);
  field('Disk allocation','disk',d.disk||'16G','text','Example: 16G. Allocated disk persists when Android stops.');extra.append(fields.lastElementChild);
  field('System image variant','image',d.image||'google_apis');extra.append(fields.lastElementChild);
  field('Hardware profile','profile',d.profile||'pixel_8_pro');extra.append(fields.lastElementChild);
  field('Android API level','api',d.api||'35','number');extra.append(fields.lastElementChild);
 }
}
function endpoint(d,port=d.port){return d.address+':'+port;}
$('wizard-form').onsubmit=async e=>{
 e.preventDefault();if(!flow)return;
 if(flow.step===0){flow.data={...flow.data,...Object.fromEntries(new FormData(e.target))};if(flow.kind==='create'){const host=hosts.find(h=>h.id===flow.data.host);if(host?.instances.some(i=>Number(i.id)===Number(flow.data.instance))){$('wizard-error').textContent='That identity is already reserved. Select it in the catalog and choose Start.';return;}flow.data.ram=Number(flow.data.preset);flow.data.cpus=flow.data.ram/1024;localStorage.setItem('androidctl-default-scale',flow.data.display_scale);}flow.step=1;renderFlow();return;}
 const {kind,data:d}=flow;$('wizard-next').disabled=true;$('wizard-back').disabled=true;$('wizard-close').disabled=true;$('wizard-error').textContent='Working…';
 try{
  if(kind==='device'){
   if(d.method==='usb'){await refresh();notice('Scan complete. If your phone is missing, unlock it and accept USB debugging.');}
   else{if(d.method==='pair')await action(endpoint(d,d.pairPort),'pair',{code:d.code});
    await action(endpoint(d),'save',{name:d.name||endpoint(d)});
    await action(endpoint(d),'connect');await refresh();notice('Connected to '+endpoint(d));}
  }else if(kind==='server'){
   await hostAction({action:'save',id:d.id,ssh_user:d.user,ssh_host:d.address,endpoint_host:d.address,port:Number(d.port)});
   await hostAction({action:'scan',host:d.id});
  }else await hostAction({action:'create',host:d.host,instance:d.instance,ram:d.ram,cpus:d.cpus,api:Number(d.api),profile:d.profile,display_scale:Number(d.display_scale),runtime_ports:true,name:d.instance_name||'',disk:d.disk,image:d.image});
  $('wizard').close();if(kind==='device')navigate({kind:'controller'});if(kind==='server')navigate({kind:'server',host:d.id});if(kind!=='device'){await refreshHosts();}
 }catch(err){$('wizard-error').textContent=err.message;}
 finally{$('wizard-next').disabled=false;$('wizard-back').disabled=false;$('wizard-close').disabled=false;}
};
$('wizard-back').onclick=()=>{flow.step=0;renderFlow();};
$('wizard-close').onclick=()=>$('wizard').close();
$('wizard').addEventListener('cancel',e=>{if($('wizard-close').disabled)e.preventDefault();});
$('empty-add').onclick=()=>openFlow('device');
$('empty-host').onclick=()=>openFlow('server');

function hostHelp(message){
 if(/resolve hostname/i.test(message))return 'Check the server IP and username using Edit connection. The SSH target must include both.';
 if(/Permission denied|publickey/i.test(message))return 'SSH login failed. Configure key-based login from this computer to the server.';
 if(/Host key verification/i.test(message))return 'Open a terminal and connect with SSH once to verify and trust this server.';
 if(/sudo.*password|password.*required/i.test(message))return 'SSH connected successfully. Start/stop/create failed because sudo requires a password. Configure noninteractive sudo for AndroidCtl on this server; changing the hostname will not fix this.';
 if(/command not found|not recognized|No such file/i.test(message))return 'AndroidCtl or SSH is missing from the command path. See the exact command error below.';
 if(/Connection refused/i.test(message))return 'The SSH port refused the connection. Check the SSH service and port.';
 if(/timed out|TimeoutExpired/i.test(message))return 'The server request timed out. Check SSH connectivity; last known instances remain visible.';
 if(/invalid choice|unrecognized arguments/i.test(message))return 'Upgrade AndroidCtl on this server to use this command.';
 if(/JSON|inventory response/i.test(message))return 'The server did not return a valid AndroidCtl inventory. See its response below.';
 return 'The server operation failed. Its exact error is shown below; existing instance data has not been replaced.';
}
async function refreshHosts(){
 const result=await(await api('/api/hosts')).json();hosts=result.hosts;
 renderServerNav();renderTasks();const snapshot=JSON.stringify(hosts);if(snapshot===hostSnapshot)return;hostSnapshot=snapshot;
 const box=$('host-list');box.replaceChildren();
 if(!hosts.length){box.textContent='No servers yet. Add one to manage Android instances.';renderObject();return;}
 for(const h of hosts){
  const card=document.createElement('section');card.className='server-card';card.dataset.host=h.id;card.hidden=h.id!==selectedHost;const title=document.createElement('h3');title.textContent=h.id;card.append(title);
  const meta=document.createElement('p');meta.textContent='SSH: '+h.target+':'+h.port+' · Device address: '+h.endpoint_host;card.append(meta);
  const op=h.operation;const state=document.createElement('p');state.className=op?.state==='error'?'error':'muted';
  state.textContent=op?(op.state==='error'?hostHelp(op.message)+'\n'+op.message:op.message):'Loading registered instances…';card.append(state);
  if(op){const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent='Operation details';const pre=document.createElement('pre');pre.textContent=[op.message,op.output].filter(Boolean).join('\n');details.append(summary,pre);card.append(details);}
  const controls=document.createElement('div');controls.className='controls';card.append(controls);
  button(controls,'Scan instances',()=>hostAction({host:h.id,action:'scan'})).disabled=op?.state==='running';
  button(controls,'Connection help',()=>{
   $('info').querySelector('h2').textContent='Server connection';
   $('details').textContent='SSH target: '+h.target+'\nSSH port: '+h.port+'\nADB host: '+h.endpoint_host+'\n\nOn the computer running this web app, test:\nssh -p '+h.port+' '+h.target+'\n\nVerify the host fingerprint and configure SSH key login. The web app cannot answer SSH password prompts. Then test:\nssh -T -o BatchMode=yes -p '+h.port+' '+h.target+' "androidctl list --json"\n\nLifecycle operations also require noninteractive sudo for AndroidCtl.\n\nLast result: '+(h.operation?.message||'No attempt recorded');$('info').showModal();
  });
  const reports=document.createElement('details');reports.innerHTML='<summary>Diagnostics and configuration</summary>';card.append(reports);
  const limitLabel=document.createElement('label');limitLabel.textContent='New concurrency limit (save while all Android instances are stopped) ';const limit=document.createElement('input');limit.type='number';limit.min=1;limit.max=65;limit.value=3;limit.setAttribute('aria-label','Maximum concurrent instances');limitLabel.append(limit);reports.append(limitLabel);
  button(reports,'Save concurrency limit',()=>{if(!limit.reportValidity())return;return hostAction({host:h.id,action:'capacity',maximum:Number(limit.value)});}).disabled=op?.state==='running'||h.instances.some(i=>!['stopped','failed'].includes(i.state));


  for(const [label,act]of [['Performance report','diagnostics'],['System check','doctor'],['GPU devices','gpu-list'],['Port map','ports'],['Hardware profiles','profiles'],['SDK status','sdk-status'],['SDK images','sdk-images'],['Server configuration','config']])button(reports,label,()=>hostAction({host:h.id,action:act})).disabled=op?.state==='running';
  button(controls,'Edit connection',()=>{const at=h.target.indexOf('@');openFlow('server',{id:h.id,address:at>=0?h.target.slice(at+1):h.endpoint_host,user:at>=0?h.target.slice(0,at):(/resolve hostname/i.test(h.operation?.message||'')?h.target:''),port:h.port,editing:true});}).disabled=op?.state==='running';
  button(controls,'Create a new instance…',()=>openFlow('create',{host:h.id})).disabled=op?.state==='running'||!h.inventory_known||op?.state==='error';
  box.append(card);
 }
 renderObject();
}
safely(refreshHosts)();setInterval(()=>{if(!document.hidden)safely(refreshHosts)();},3000);

// Instance actions always use the managed host identity.
let instanceTask=null;
function instanceDialog(t,kind){
 const m=t.device.managed;instanceTask={m,kind};
 $('instance-title').textContent=kind==='delete'?'Delete virtual Android':'Default screen resolution';
 $('instance-description').textContent=kind==='delete'
 ?'This stops and removes instance '+m.id+' on '+m.host+'. Choose whether to retain its Android data.'
 :'Saved on '+m.host+' for instance '+m.id+'. Applies now if running and again on service startup. Width, height and density scale together.';
 const box=$('instance-fields');box.replaceChildren();
 const label=document.createElement('label');const select=document.createElement('select');select.id='instance-choice';
 if(kind==='delete'){
  label.textContent='Android data';select.add(new Option('Keep data on server for manual recovery','keep'));select.add(new Option('Permanently erase apps, accounts and files','erase'));
  label.append(select);box.append(label);
  const typed=document.createElement('label');typed.textContent='Type DELETE '+m.id+' to confirm';const input=document.createElement('input');input.id='delete-confirm';input.required=true;input.autocomplete='off';typed.append(input);box.append(typed);
 }else{
  label.textContent='Resolution';for(const n of [25,33,50,75,100])select.add(new Option(n+'%'+(n===100?' · native':n===50?' · recommended':''),n));
  select.value=String(m.display_scale||50);label.append(select);box.append(label);
 }
 $('instance-error').textContent='';$('instance-submit').textContent=kind==='delete'?'Delete instance':'Save default resolution';$('instance-dialog').showModal();
}
$('instance-close').onclick=()=>$('instance-dialog').close();
$('instance-form').onsubmit=async e=>{
 e.preventDefault();const {m,kind}=instanceTask;
 const data={host:m.host,instance:m.id,action:kind};
 if(kind==='delete'){data.confirm=$('delete-confirm').value;data.erase_data=$('instance-choice').value==='erase';if(data.confirm!=='DELETE '+m.id){$('instance-error').textContent='Enter DELETE '+m.id+' exactly.';return;}}
 else data.display_scale=Number($('instance-choice').value);
 $('instance-submit').disabled=true;
 try{await hostAction(data);$('instance-dialog').close();showView('catalog');}
 catch(err){$('instance-error').textContent=err.message;}
 finally{$('instance-submit').disabled=false;}
};
function belongs(d){
 if(selection.kind==='instance')return d.serial===instanceSerial();
 if(selection.kind==='device')return d.serial===selection.serial;
 if(selection.kind==='server')return d.managed?.host===selection.host;
 return selection.kind==='controller'&&!d.managed;
}
function filterTiles(){const q=$('filter').value.trim().toLowerCase();for(const t of tiles.values())t.el.hidden=!belongs(t.device)||![t.device.name,t.device.serial].join(' ').toLowerCase().includes(q);}
$('filter').oninput=filterTiles;
function download(filename,content,type){
 const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
$('exports').onclick=()=>$('export-dialog').showModal();
$('export-close').onclick=()=>$('export-dialog').close();
$('export-connections').onclick=safely(async()=>{
 await refreshHosts();await refresh();
 const connections={format:'androidctl-workspace',version:1,hosts:hosts.map(({id,target,endpoint_host,port})=>({id,target,endpoint_host,port})),devices:await(await api('/api/devices')).json().then(r=>r.devices.map(d=>({serial:d.serial,name:d.name}))),preferences:{default_display_scale:Number(localStorage.getItem('androidctl-default-scale')||50)}};
 download('androidctl-connections.json',JSON.stringify(connections,null,2),'application/json');notice('Connections exported');
});
function quote(value){return "'"+String(value).replaceAll("'","'\\''")+"'";}
$('export-commands').onclick=safely(async()=>{
 await refreshHosts();await refresh();
 const lines=['#!/usr/bin/env bash','# AndroidCtl command reference — uncomment only the commands you want to run.','# Linux/macOS/Git Bash syntax. Run SSH commands from your controller.',''];
 for(const h of hosts){
  const remote=cmd=>h.target==='local'?cmd:'ssh -p '+Number(h.port)+' '+quote(h.target)+' '+quote(cmd);
  lines.push('# Server '+h.id,'# '+remote('androidctl list --json'),'# '+remote('androidctl performance --json'));
  for(const i of h.instances){
   const id=String(i.id).padStart(2,'0');
   for(const cmd of ['sudo androidctl start '+id,'sudo androidctl stop '+id,'sudo androidctl restart '+id,'sudo androidctl enable '+id,'sudo androidctl disable '+id,'sudo androidctl display '+id+' --scale '+(i.display_scale||50),'androidctl logs '+id+' --since 30m','androidctl info '+id+' --json'])lines.push('# '+remote(cmd));
  }lines.push('');
 }
 for(const {device:d}of tiles.values()){
  lines.push('# Device '+String(d.name).replace(/[\r\n]/g,' '));
  if(d.serial.includes(':'))lines.push('# adb connect '+quote(d.serial));
  lines.push('# scrcpy -s '+quote(d.serial)+' --no-audio --max-fps=30','# adb -s '+quote(d.serial)+' shell wm size','');
 }
 download('androidctl-commands.sh',lines.join('\n')+'\n','text/plain');notice('Command reference exported');
});

function serverInstance(h,i){
 const row=document.createElement('section');row.className='instance-row';
 const title=document.createElement('h4');title.textContent=String(i.id).padStart(2,'0')+' · '+i.name;
 const badge=document.createElement('span');badge.className='state';badge.textContent=i.state||'unknown';title.append(badge);row.append(title);
 const meta=document.createElement('p');meta.className='muted';meta.textContent='API '+i.api+' · '+i.cpu_cores+' CPU · '+i.ram_mb+' MiB RAM · '+i.disk_size+' disk allocation · '+i.gpu_mode+' · '+(i.display_scale?i.display_scale+'% resolution':'existing resolution');row.append(meta);
 const id=String(i.id).padStart(2,'0');const serial=h.endpoint_host+':'+i.remote_adb_port;
 const busy=h.operation?.state==='running'||['starting','stopping','booting'].includes(i.state);
 const mutate=action=>hostAction({host:h.id,instance:id,action});
 const details=document.createElement('details');details.innerHTML='<summary>Storage, configuration and more controls</summary>';
 const info=document.createElement('pre');info.textContent='Storage: '+(i.avd||'Not reported')+'\nAutostart: '+(i.autostart?'enabled':'disabled')+'\nADB endpoint: '+serial+'\nService result: '+(i.service_result||'not reported')+'\nHealth: '+(i.health||'not probed');details.append(info);
 const box=document.createElement('div');box.className='controls';details.append(box);
 const fake={device:{managed:{host:h.id,id,state:i.state,display_scale:i.display_scale,autostart:i.autostart}}};
 const renderer=document.createElement('select');renderer.setAttribute('aria-label','Renderer for instance '+id);renderer.add(new Option('Software rendering','swangle'));renderer.add(new Option('Host GPU','host'));renderer.value=i.gpu_mode==='host'?'host':'swangle';box.append(renderer);
 button(box,'Save renderer',()=>hostAction({host:h.id,instance:id,action:'renderer',gpu:renderer.value})).disabled=busy||!['stopped','failed'].includes(i.state);

 button(box,'Default resolution…',()=>instanceDialog(fake,'display')).disabled=busy;
 button(box,i.autostart?'Disable autostart':'Enable autostart',()=>mutate(i.autostart?'disable':'enable')).disabled=busy;
 for(const [label,actionName]of [['Logs','logs'],['Health','health'],['Inspect','info']])button(box,label,()=>mutate(actionName)).disabled=busy;
 row.append(details);return row;
}

function showView(view){section=view==='live'?'Console':'Summary';renderObject();}
function activeHost(){return hosts.find(h=>h.id===selection.host);}
function activeInstance(){return activeHost()?.instances.find(i=>String(i.id)===selection.id);}
function instanceSerial(){const h=activeHost(),i=activeInstance();return i?h.endpoint_host+':'+i.remote_adb_port:'';}
function navigate(object){
 for(const t of tiles.values())stopPreview(t,'Preview inactive');
 selection=object;section=object.kind==='server'?'Instances':'Summary';selectedHost=object.host||'';selectedInstance=object.id||'';catalogPage=0;renderServerNav();renderObject();
}
function labelFor(object){if(object.kind==='root')return 'Connections';if(object.kind==='controller')return 'Local controller';if(object.kind==='server')return object.host;if(object.kind==='instance'){const i=hosts.find(h=>h.id===object.host)?.instances.find(i=>String(i.id)===object.id);return object.id+' · '+(i?.name||'Instance');}return devices.find(d=>d.serial===object.serial)?.name||object.serial;}
function renderServerNav(){
 const nav=$('resource-tree'),focusKey=document.activeElement?.dataset.key;nav.replaceChildren();
 const q=$('tree-search').value.toLowerCase();
 function node(parent,obj,children=[]){
  const key=JSON.stringify(obj),item=document.createElement('div');item.setAttribute('role','treeitem');item.setAttribute('aria-selected',String(JSON.stringify(selection)===key));item.dataset.key=key;item.tabIndex=JSON.stringify(selection)===key?0:-1;
  const line=document.createElement('div');line.className='tree-line';item.append(line);
  const expanded=!collapsed.has(key)||!!q;
  if(children.length){item.setAttribute('aria-expanded',String(expanded));const toggle=button(line,expanded?'▾':'▸',()=>{if(collapsed.has(key))collapsed.delete(key);else collapsed.add(key);renderServerNav();});toggle.tabIndex=-1;toggle.setAttribute('aria-label','Expand or collapse '+labelFor(obj));}
  const text=document.createElement('span');text.textContent=labelFor(obj);line.append(text);
  const state=obj.kind==='instance'?hosts.find(h=>h.id===obj.host)?.instances.find(i=>String(i.id)===obj.id)?.state:obj.kind==='device'?devices.find(d=>d.serial===obj.serial)?.state:'';
  if(state){const badge=document.createElement('small');badge.className='tree-state';badge.textContent=state;line.append(badge);}line.onclick=e=>{if(e.target.tagName!=='BUTTON')navigate(obj);};
  item.onkeydown=e=>{if(e.target!==item)return;const all=[...nav.querySelectorAll('[role=treeitem]')],at=all.indexOf(item);let next;
   if(e.key==='ArrowDown')next=all[Math.min(at+1,all.length-1)];if(e.key==='ArrowUp')next=all[Math.max(0,at-1)];if(e.key==='Home')next=all[0];if(e.key==='End')next=all.at(-1);
   if(e.key==='ArrowRight'){collapsed.delete(key);renderServerNav();}if(e.key==='ArrowLeft'){collapsed.add(key);renderServerNav();}if(e.key==='Enter'||e.key===' ')navigate(obj);
   if(next){all.forEach(n=>n.tabIndex=-1);next.tabIndex=0;next.focus();}if(['ArrowDown','ArrowUp','ArrowLeft','ArrowRight','Home','End','Enter',' '].includes(e.key))e.preventDefault();};
  parent.append(item);if(children.length&&expanded){const group=document.createElement('div');group.setAttribute('role','group');item.append(group);for(const child of children)node(group,child);}
 }
 node(nav,{kind:'root'});
 const local=devices.filter(d=>!d.managed&&[d.name,d.serial].join(' ').toLowerCase().includes(q)).map(d=>({kind:'device',serial:d.serial}));node(nav,{kind:'controller'},local);
 for(const h of hosts){const matches=h.id.toLowerCase().includes(q);const list=h.instances.filter(i=>matches||[i.id,i.name,i.state,i.remote_adb_port].join(' ').toLowerCase().includes(q));if(matches||list.length)node(nav,{kind:'server',host:h.id},list.map(i=>({kind:'instance',host:h.id,id:String(i.id)})));}
 if(focusKey){const restored=[...nav.querySelectorAll('[role=treeitem]')].find(n=>n.dataset.key===focusKey);restored?.focus();}
}
function properties(parent,rows){const table=document.createElement('table');table.className='properties';for(const [key,value]of rows){const tr=document.createElement('tr');for(const v of [key,value??'Not reported']){const td=document.createElement('td');td.textContent=String(v);tr.append(td);}table.append(tr);}parent.append(table);}
function renderTasks(){
 const box=$('task-list'),seen=new Set();
 for(const h of hosts){if(!h.operation)continue;seen.add(h.id);
  let row=[...box.children].find(r=>r.dataset.host===h.id);
  if(!row){row=document.createElement('details');row.dataset.host=h.id;row.append(document.createElement('summary'),document.createElement('pre'));box.append(row);}
  row.querySelector('summary').textContent=h.id+' · '+h.target+' · '+h.operation.state+' · '+h.operation.message;
  row.querySelector('pre').textContent=(h.operation.state==='error'?hostHelp(h.operation.message):'')+'\nSSH target: '+h.target+'\nADB address: '+h.endpoint_host+'\n'+(h.operation.output||h.operation.message);
 }
 for(const row of [...box.children])if(!seen.has(row.dataset.host))row.remove();
}
function renderObject(){
 const h=activeHost(),i=activeInstance();currentView=section==='Console'?'live':'catalog';
 for(const id of ['overview','catalog','catalog-detail','host-list','live-workspace'])$(id).hidden=true;
 const title=labelFor(selection);$('object-title').textContent=title;$('object-state').textContent=i?.state||'';
 const crumbs=$('breadcrumbs');crumbs.replaceChildren();button(crumbs,'Connections',()=>navigate({kind:'root'}));if(selection.host)button(crumbs,selection.host,()=>navigate({kind:'server',host:selection.host}));else if(selection.kind!=='root')button(crumbs,'Local controller',()=>navigate({kind:'controller'}));
 const toolbar=$('context-actions');toolbar.replaceChildren();const busy=h?.operation?.state==='running';
 if(selection.kind==='root'){button(toolbar,'Add server…',()=>openFlow('server'));button(toolbar,'Refresh',async()=>{await refreshHosts();await refresh();});}
 if(selection.kind==='controller'){button(toolbar,'Scan ADB',refresh);button(toolbar,'Add network device…',()=>openFlow('device'));}
 if(selection.kind==='server'&&h){
  button(toolbar,'Scan instances',()=>hostAction({host:h.id,action:'scan'})).disabled=busy;
  button(toolbar,'Create instance…',()=>openFlow('create',{host:h.id})).disabled=busy||!h.inventory_known||h.operation?.state==='error';
  button(toolbar,'Edit connection…',()=>{const at=h.target.indexOf('@');openFlow('server',{id:h.id,address:at>=0?h.target.slice(at+1):h.endpoint_host,user:at>=0?h.target.slice(0,at):(/resolve hostname/i.test(h.operation?.message||'')?h.target:''),port:h.port,editing:true});}).disabled=busy;
  button(toolbar,'Remove connection…',async()=>{if(confirm('Remove saved connection '+h.id+'? Its Android instances and storage stay on the server.')){await hostAction({host:h.id,action:'remove'});navigate({kind:'root'});await refresh();}}).disabled=busy;
 }
 if(selection.kind==='instance'&&h&&i){
  const mutate=action=>hostAction({host:h.id,instance:i.id,action});
  button(toolbar,'Start',()=>mutate('start')).disabled=busy||!['stopped','failed'].includes(i.state);
  for(const [label,action]of [['Stop','stop'],['Power cycle','restart']])button(toolbar,label,async()=>{if(confirm(label+' '+i.id+' on '+h.id+'? Storage is preserved.'))await mutate(action);}).disabled=busy||i.state!=='running';
  button(toolbar,'Delete instance…',()=>instanceDialog({device:{managed:{host:h.id,id:i.id}}},'delete')).disabled=busy;
  button(toolbar,'Refresh',()=>hostAction({host:h.id,action:'scan'})).disabled=busy;
 }
 if(selection.kind==='device'){
  button(toolbar,'Connect',async()=>{await action(selection.serial,'connect');await refresh();});button(toolbar,'Disconnect',async()=>{await action(selection.serial,'disconnect');await refresh();});
  button(toolbar,'Edit name…',async()=>{const value=prompt('Device name',labelFor(selection));if(value?.trim()){await action(selection.serial,'save',{name:value.trim()});await refresh();renderObject();}});
  button(toolbar,'Remove saved connection…',async()=>{if(confirm('Forget this connection? Attached USB devices remain discoverable.')){await action(selection.serial,'forget');navigate({kind:'controller'});await refresh();}});
 }
 const names=selection.kind==='server'?['Instances','Connection','Diagnostics','Console']:selection.kind==='instance'?['Summary','Configuration','Console']:selection.kind==='device'?['Summary','Console']:selection.kind==='controller'?['Summary','Console']:['Summary'];
 if(!names.includes(section))section=names[0];const tabs=$('object-tabs');tabs.replaceChildren();for(const name of names){const b=button(tabs,name,async()=>{section=name;renderObject();if(name==='Console'&&selection.kind==='instance'&&i?.state==='running')await openConsole(instanceSerial());else if(name==='Console'&&selection.kind==='device')await openConsole(selection.serial);});b.className=name===section?'active':'';b.setAttribute('aria-current',name===section?'page':'false');}
 if(section==='Console'){
  const candidates=selection.kind==='instance'?(i?[{serial:instanceSerial(),name:labelFor(selection),state:i.state}]:[]):selection.kind==='server'?(h?.instances||[]).map(i=>({serial:h.endpoint_host+':'+i.remote_adb_port,name:i.id+' · '+i.name,state:i.state})):devices.filter(belongs);
  for(const d of candidates){button(toolbar,'Open '+d.name,()=>openConsole(d.serial)).disabled=['stopped','failed','starting','stopping','booting'].includes(d.state);}
  $('live-workspace').hidden=false;filterTiles();$('empty').hidden=[...tiles.values()].some(t=>!t.el.hidden);
  $('empty').querySelector('p').textContent=selection.kind==='instance'&&i?.state!=='running'?'Android is '+(i?.state||'unavailable')+'. Use Start above, wait for completion, then open this console. Storage and identity are preserved.':!candidates.length?'No devices available for this object. Scan its inventory or add a connection.':'Choose an Open button above. Only devices belonging to this object are shown.';return;}
 if(selection.kind==='server'&&h){if(section==='Instances'){$('catalog').hidden=false;renderCatalog();}else{$('host-list').hidden=false;for(const card of $('host-list').children){card.hidden=card.dataset.host!==h.id;const reports=card.querySelectorAll('details');for(const report of reports){const diagnostics=report.querySelector('summary')?.textContent==='Diagnostics and configuration';report.hidden=diagnostics?section!=='Diagnostics':section==='Diagnostics';report.open=true;}for(const controls of card.querySelectorAll(':scope > .controls'))controls.hidden=true;}}return;}
 const box=$('overview');box.hidden=false;box.replaceChildren();
 if(selection.kind==='instance'){
  if(!i){box.textContent='Instance is no longer in this server’s inventory. Select the server to refresh.';return;}
  if(section==='Configuration'){const detail=$('catalog-detail');detail.hidden=false;detail.replaceChildren(serverInstance(h,i));detail.querySelector('details').open=true;return;}
  properties(box,[['Owner server',h.id],['Instance ID',i.id],['Name',i.name],['Android state',i.state],['ADB endpoint',instanceSerial()],['Android API',i.api],['CPU cores',i.cpu_cores],['RAM (MiB)',i.ram_mb],['Disk allocation',i.disk_size],['Persistent storage',i.avd],['Renderer',i.gpu_mode],['Default resolution',i.display_scale?i.display_scale+'%':'Unchanged'],['Autostart',i.autostart?'Enabled':'Disabled']]);
  button(box,'Open console',()=>openConsole(instanceSerial())).disabled=i.state!=='running';for(const [label,act]of [['Logs','logs'],['Health','health'],['Inspect','info']])button(box,label,()=>hostAction({host:h.id,instance:i.id,action:act})).disabled=busy;return;
 }
 if(selection.kind==='device'){const d=devices.find(d=>d.serial===selection.serial);properties(box,[['Owner','Local controller'],['Connection',selection.serial.includes(':')?'Network ADB':selection.serial.startsWith('emulator-')?'Local emulator':'USB / local ADB'],['Serial',selection.serial],['State',d?.state],['Details',d?.details]]);button(box,'Open console',()=>openConsole(selection.serial));return;}
 if(selection.kind==='root'){for(const server of hosts){button(box,server.id,()=>navigate({kind:'server',host:server.id}));properties(box,[['SSH target',server.target],['Inventory',server.inventory_known?server.instances.length+' instances':'Unknown — scan required'],['Last operation',server.operation?.message]]);}button(box,'Local controller',()=>navigate({kind:'controller'}));return;}
 const table=document.createElement('table');const head=document.createElement('tr');for(const text of ['Device','Connection','State','Actions']){const th=document.createElement('th');th.textContent=text;head.append(th);}table.append(head);
 for(const d of devices.filter(d=>!d.managed)){const row=document.createElement('tr');const name=document.createElement('td');button(name,d.name,()=>navigate({kind:'device',serial:d.serial}));row.append(name);for(const value of [d.serial,d.state]){const cell=document.createElement('td');cell.textContent=value;row.append(cell);}const actions=document.createElement('td');button(actions,'Open',()=>{navigate({kind:'device',serial:d.serial});return openConsole(d.serial);});row.append(actions);table.append(row);}box.append(table);
}
async function openConsole(serial){const owner=JSON.stringify(selection);opened.add(serial);await action(serial,'connect');await refresh();if(JSON.stringify(selection)===owner){section='Console';renderObject();}}
function renderCatalog(){
 const h=activeHost();if(!h)return;const rows=$('catalog-rows');rows.replaceChildren();
 $('catalog-summary').textContent=h.inventory_known?h.instances.length+' instances · '+h.instances.filter(i=>i.state==='running').length+' running · '+h.instances.filter(i=>i.state==='stopped').length+' stopped':'Inventory unknown';
 $('catalog-connection').textContent=(h.operation?.state==='error'?hostHelp(h.operation.message)+' ':'')+(h.operation?.message||'')+(h.inventory_stale?' · Last known inventory; scan to refresh':'')+(h.inventory_at?' · '+new Date(h.inventory_at*1000).toLocaleString():'');
 const q=$('catalog-search').value.toLowerCase(),state=$('catalog-state').value,sort=$('catalog-sort').value;
 const filtered=h.instances.filter(i=>(!state||i.state===state)&&[i.id,i.name,i.remote_adb_port].join(' ').toLowerCase().includes(q)).sort((a,b)=>sort==='id'?Number(a.id)-Number(b.id):String(a[sort]).localeCompare(String(b[sort])));
 const pages=Math.max(1,Math.ceil(filtered.length/25));catalogPage=Math.min(catalogPage,pages-1);$('catalog-page').textContent=filtered.length+' matching · Page '+(catalogPage+1)+' of '+pages;$('page-prev').disabled=!catalogPage;$('page-next').disabled=catalogPage>=pages-1;
 for(const i of filtered.slice(catalogPage*25,catalogPage*25+25)){const row=document.createElement('tr'),cell=document.createElement('td');button(cell,i.id+' · '+i.name,()=>navigate({kind:'instance',host:h.id,id:String(i.id)}));row.append(cell);for(const v of ['API '+i.api,i.state,h.endpoint_host+':'+i.remote_adb_port,i.cpu_cores+' CPU / '+i.ram_mb+' MiB',i.display_scale+'%']){const td=document.createElement('td');td.textContent=v;row.append(td);}rows.append(row);}
 $('catalog-empty').textContent=filtered.length?'':h.inventory_known?'No matching instances.':'Inventory unavailable; this does not mean the server is empty.';
}
$('tree-search').oninput=renderServerNav;
for(const id of ['catalog-search','catalog-state','catalog-sort'])$(id).oninput=()=>{catalogPage=0;renderCatalog();};
$('page-prev').onclick=()=>{catalogPage--;renderCatalog();};$('page-next').onclick=()=>{catalogPage++;renderCatalog();};
renderServerNav();renderObject();
