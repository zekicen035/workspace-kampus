require('dotenv').config();
const express=require('express'),path=require('path'),crypto=require('crypto'),jwt=require('jsonwebtoken');
const {createClient}=require('@supabase/supabase-js');
const db=createClient(process.env.SUPABASE_URL,process.env.SUPABASE_SERVICE_KEY);
const SECRET=process.env.JWT_SECRET||'dev-secret';
const app=express();app.use(express.json());app.use(express.static(path.join(__dirname,'public')));
const sign=u=>jwt.sign({id:u.id},SECRET,{expiresIn:'12h'});
const hash=s=>crypto.createHash('sha256').update(s+SECRET).digest('hex');
const phoneNorm=p=>{p=String(p||'').replace(/\D/g,'');return p.startsWith('0')?'62'+p.slice(1):p};
// ---------- SANDI (scrypt) & PEMBATAS PERCOBAAN ----------
const scrypt=(pw,salt)=>new Promise((res,rej)=>crypto.scrypt(pw,salt,64,(e,k)=>e?rej(e):res(k)));
async function hashPw(pw){const salt=crypto.randomBytes(16);return 'scrypt$'+salt.toString('hex')+'$'+(await scrypt(pw,salt)).toString('hex')}
async function checkPw(pw,stored){if(!stored)return false;try{const[,salt,h]=stored.split('$');const k=await scrypt(pw,Buffer.from(salt,'hex')),a=Buffer.from(h,'hex');return a.length===k.length&&crypto.timingSafeEqual(a,k)}catch{return false}}
const pwOk=p=>typeof p==='string'&&p.length>=8&&p.length<=72;
const fails=new Map(); // maks 5 percobaan gagal per NIM dalam 15 menit
const locked=k=>{const f=fails.get(k);return !!f&&f.n>=5&&Date.now()-f.t<9e5};
const fail=k=>{const f=fails.get(k);fails.set(k,f&&Date.now()-f.t<9e5?{n:f.n+1,t:f.t}:{n:1,t:Date.now()})};
const wrap=fn=>(q,s)=>fn(q,s).catch(e=>{console.error(e);s.status(500).json({error:'Terjadi kesalahan server'})});
const auth=async(q,s,n)=>{try{const{id}=jwt.verify((q.headers.authorization||'').slice(7),SECRET);
  const{data}=await db.from('users').select('*').eq('id',id).single();if(!data)throw 0;q.user=data;n()}
  catch{s.status(401).json({error:'Sesi berakhir, silakan login lagi'})}};

// ---------- AUTH ----------
app.post('/api/auth/nim',wrap(async(q,s)=>{
  const nim=String(q.body.nim||'').trim();
  const{data:st}=await db.from('students').select('*').eq('nim',nim).maybeSingle();
  if(!st){const{data:rg}=await db.from('registrations').select('status').eq('nim',nim).maybeSingle();
    const msg=rg?.status==='pending'?'Pendaftaran kamu masih menunggu persetujuan admin.':rg?.status==='rejected'?'Pendaftaran ditolak. Hubungi admin atau daftar ulang.':'NIM belum terdaftar. Silakan daftar dulu.';
    return s.status(404).json({error:msg,canRegister:!rg||rg.status==='rejected'})}
  if(locked(nim))return s.status(429).json({error:'Terlalu banyak percobaan. Coba lagi 15 menit lagi.'});
  if(!st.password_hash)return s.status(403).json({error:'Akun ini belum punya sandi. Hubungi admin untuk mengatur sandi.'});
  if(!await checkPw(String(q.body.password||''),st.password_hash)){fail(nim);return s.status(401).json({error:'NIM atau sandi salah'})}
  fails.delete(nim);
  let{data:u}=await db.from('users').select('*').eq('nim',nim).maybeSingle();
  if(!u)({data:u}=await db.from('users').insert({nim,name:st.name,role:'student'}).select().single());
  s.json({token:sign(u),user:u});
}));
app.post('/api/auth/otp/request',wrap(async(q,s)=>{
  const phone=phoneNorm(q.body.phone);
  if(!/^62\d{8,13}$/.test(phone))return s.status(400).json({error:'Nomor WhatsApp tidak valid'});
  const{data:r}=await db.from('otp_codes').select('id').eq('phone',phone).gt('created_at',new Date(Date.now()-60000).toISOString()).limit(1);
  if(r?.length)return s.status(429).json({error:'Tunggu 60 detik sebelum meminta OTP lagi'});
  const code=String(crypto.randomInt(100000,1000000));
  await db.from('otp_codes').insert({phone,code_hash:hash(code),expires_at:new Date(Date.now()+300000).toISOString()});
  const message=`Kode OTP Workspace Kampus: ${code}. Berlaku 5 menit. Jangan bagikan ke siapa pun.`;
  if(process.env.FONNTE_TOKEN){
    const f=await fetch('https://api.fonnte.com/send',{method:'POST',headers:{Authorization:process.env.FONNTE_TOKEN},body:new URLSearchParams({target:phone,message})});
    const j=await f.json().catch(()=>({}));
    if(!f.ok||j.status===false){console.error('[FONNTE]',j.reason||f.status);return s.status(502).json({error:'Gagal mengirim WhatsApp: '+(j.reason||'periksa perangkat Fonnte')})}
    return s.json({ok:true});
  }
  console.log('[DEV OTP]',phone,code);s.json({ok:true,devCode:code}); // mode demo: tanpa FONNTE_TOKEN
}));
app.post('/api/auth/otp/verify',wrap(async(q,s)=>{
  const phone=phoneNorm(q.body.phone),code=String(q.body.code||''),name=String(q.body.name||'').trim()||'Tamu';
  const{data:o}=await db.from('otp_codes').select('*').eq('phone',phone).eq('used',false).gt('expires_at',new Date().toISOString()).order('created_at',{ascending:false}).limit(1).maybeSingle();
  if(!o||o.code_hash!==hash(code))return s.status(400).json({error:'OTP salah atau sudah kedaluwarsa'});
  await db.from('otp_codes').update({used:true}).eq('id',o.id);
  let{data:u}=await db.from('users').select('*').eq('phone',phone).maybeSingle();
  if(!u)({data:u}=await db.from('users').insert({phone,name,role:'guest'}).select().single());
  s.json({token:sign(u),user:u});
}));
app.get('/api/me',auth,wrap(async(q,s)=>{
  const{data:ss}=await db.from('sessions').select('started_at,workspaces(code,name,zone)').eq('user_id',q.user.id).is('ended_at',null).maybeSingle();
  let major=null;
  if(q.user.nim){const{data:st}=await db.from('students').select('major').eq('nim',q.user.nim).maybeSingle();major=st?.major||null}
  s.json({user:{...q.user,major},session:ss});
}));

// ---------- WORKSPACE ----------
app.get('/api/workspaces',wrap(async(q,s)=>{
  const{data:ws}=await db.from('workspaces').select('*').order('code');
  const{data:ss}=await db.from('sessions').select('workspace_id,started_at').is('ended_at',null);
  const m=Object.fromEntries((ss||[]).map(x=>[x.workspace_id,x]));
  s.json(ws.map(w=>{const online=w.last_seen&&Date.now()-new Date(w.last_seen)<30000;
    return{code:w.code,name:w.name,zone:w.zone,
      map_x:w.map_x,map_y:w.map_y,map_w:w.map_w,map_h:w.map_h,
      online:!!online,distance:w.distance_cm,since:m[w.id]?.started_at||null,
      state:m[w.id]?'occupied':(online&&w.sensor_present)?'detected':'available'}}));
}));
app.post('/api/checkin',auth,wrap(async(q,s)=>{
  const code=String(q.body.code||'').trim().toUpperCase();
  const{data:w}=await db.from('workspaces').select('id,code').eq('code',code).maybeSingle();
  if(!w)return s.status(404).json({error:'QR tidak dikenali'});
  const{error}=await db.from('sessions').insert({workspace_id:w.id,user_id:q.user.id});
  if(error)return s.status(409).json({error:error.message.includes('one_active_per_user')?'Kamu masih punya sesi aktif. Check-out dulu.':'Workspace ini sedang dipakai'});
  s.json({ok:true,workspace:w.code});
}));
app.post('/api/checkout',auth,wrap(async(q,s)=>{
  await db.from('sessions').update({ended_at:new Date().toISOString()}).eq('user_id',q.user.id).is('ended_at',null);
  s.json({ok:true});
}));

// ---------- IoT (ESP32) ----------
app.post('/api/iot/telemetry',wrap(async(q,s)=>{
  if(q.headers['x-device-key']!==process.env.DEVICE_KEY)return s.status(403).json({error:'forbidden'});
  const{code,present,distance}=q.body;
  const{data:w}=await db.from('workspaces').update({sensor_present:!!present,distance_cm:distance,last_seen:new Date().toISOString()}).eq('code',code).select('id').maybeSingle();
  if(!w)return s.status(404).json({error:'workspace tidak ditemukan'});
  const{data:ss}=await db.from('sessions').select('id').eq('workspace_id',w.id).is('ended_at',null).maybeSingle();
  s.json({state:ss?'occupied':present?'detected':'available'});
}));
// ---------- PENDAFTARAN MANDIRI ----------
async function checkOtp(phone,code){
  const{data:o}=await db.from('otp_codes').select('*').eq('phone',phone).eq('used',false).gt('expires_at',new Date().toISOString()).order('created_at',{ascending:false}).limit(1).maybeSingle();
  if(!o||o.code_hash!==hash(code))return false;
  await db.from('otp_codes').update({used:true}).eq('id',o.id);return true;
}
async function sendWa(phone,message){ // notifikasi best-effort, tidak menggagalkan proses
  if(!process.env.FONNTE_TOKEN)return;
  try{await fetch('https://api.fonnte.com/send',{method:'POST',headers:{Authorization:process.env.FONNTE_TOKEN},body:new URLSearchParams({target:phone,message})})}
  catch(e){console.error('[WA]',e.message)}
}
app.post('/api/register/verify',wrap(async(q,s)=>{
  const nim=String(q.body.nim||'').trim(),name=String(q.body.name||'').trim(),major=String(q.body.major||'').trim().slice(0,80),phone=phoneNorm(q.body.phone),code=String(q.body.code||'');
  if(!/^[A-Za-z0-9./-]{5,25}$/.test(nim)||name.length<3||major.length<2)return s.status(400).json({error:'Isi nama, NIM, dan program studi dengan benar'});
  const password=String(q.body.password||'');
  if(!pwOk(password))return s.status(400).json({error:'Sandi minimal 8 karakter'});
  if(!/^62\d{8,13}$/.test(phone))return s.status(400).json({error:'Nomor WhatsApp tidak valid'});
  const{data:st}=await db.from('students').select('nim').eq('nim',nim).maybeSingle();
  if(st)return s.status(409).json({error:'NIM ini sudah terdaftar, silakan langsung login.'});
  const{data:rg}=await db.from('registrations').select('status').eq('nim',nim).maybeSingle();
  if(rg?.status==='pending')return s.status(409).json({error:'Pendaftaran NIM ini sudah menunggu persetujuan admin.'});
  if(!await checkOtp(phone,code))return s.status(400).json({error:'OTP salah atau sudah kedaluwarsa'});
  await db.from('registrations').upsert({nim,name,major,phone,password_hash:await hashPw(password),status:'pending',created_at:new Date().toISOString(),decided_at:null},{onConflict:'nim'});
  s.json({ok:true,message:'Pendaftaran terkirim. Tunggu persetujuan admin, lalu login dengan NIM.'});
}));

// ---------- STATISTIK PUBLIK (agregat, tanpa data pribadi) ----------
const TZ=Number(process.env.TZ_OFFSET_HOURS||7); // WIB = UTC+7
const hourOf=t=>new Date(t+TZ*36e5).getUTCHours();
app.get('/api/stats/busy',wrap(async(q,s)=>{
  const days=Math.min(30,Math.max(1,parseInt(q.query.days)||7));
  const{data}=await db.from('sessions').select('started_at,ended_at').gte('started_at',new Date(Date.now()-days*864e5).toISOString()).limit(2000);
  const hours=Array(24).fill(0);
  (data||[]).forEach(r=>{const end=r.ended_at?new Date(r.ended_at).getTime():Date.now(),seen=new Set();
    for(let i=0,t=Math.floor(new Date(r.started_at).getTime()/36e5)*36e5;i<24&&t<=end;i++,t+=36e5){const h=hourOf(t);if(!seen.has(h)){seen.add(h);hours[h]++}}});
  s.json({days,hours,nowHour:hourOf(Date.now())});
}));

// ---------- ADMIN ----------
const adminAuth=(q,s,n)=>{try{if(!jwt.verify((q.headers.authorization||'').slice(7),SECRET).admin)throw 0;n()}
  catch{s.status(401).json({error:'Akses admin diperlukan'})}};
app.post('/api/admin/login',(q,s)=>{
  if(!process.env.ADMIN_KEY||hash(String(q.body.key||''))!==hash(process.env.ADMIN_KEY))return s.status(401).json({error:'Kunci admin salah'});
  s.json({token:jwt.sign({admin:true},SECRET,{expiresIn:'8h'})});
});
app.get('/api/admin/data',adminAuth,wrap(async(q,s)=>{
  const[{data:ws},{data:act},{data:hist}]=await Promise.all([
    db.from('workspaces').select('*').order('code'),
    db.from('sessions').select('workspace_id,started_at,users(name,nim,phone,role)').is('ended_at',null),
    db.from('sessions').select('started_at,ended_at,workspaces(code,name),users(name,nim,phone,role)').order('started_at',{ascending:false}).limit(500)]);
  const m=Object.fromEntries((act||[]).map(x=>[x.workspace_id,x]));
  s.json({workspaces:ws.map(w=>({code:w.code,name:w.name,zone:w.zone,distance:w.distance_cm,present:w.sensor_present,
    online:!!(w.last_seen&&Date.now()-new Date(w.last_seen)<30000),session:m[w.id]||null})),history:hist||[]});
}));
app.post('/api/admin/checkout',adminAuth,wrap(async(q,s)=>{
  const{data:w}=await db.from('workspaces').select('id').eq('code',q.body.code).maybeSingle();
  if(w)await db.from('sessions').update({ended_at:new Date().toISOString()}).eq('workspace_id',w.id).is('ended_at',null);
  s.json({ok:true});
}));
app.post('/api/admin/workspaces',adminAuth,wrap(async(q,s)=>{
  const{code,name,zone}=q.body;
  if(!code||!name||!zone)return s.status(400).json({error:'Kode, nama, dan zona wajib diisi'});
  const{error}=await db.from('workspaces').insert({code:code.trim().toUpperCase(),name:name.trim(),zone:zone.trim()});
  if(error)return s.status(409).json({error:'Kode meja sudah dipakai'});
  s.json({ok:true});
}));
app.delete('/api/admin/workspaces/:code',adminAuth,wrap(async(q,s)=>{
  const{data:w}=await db.from('workspaces').select('id').eq('code',q.params.code).maybeSingle();
  if(w){const{data:h}=await db.from('sessions').select('id').eq('workspace_id',w.id).limit(1);
    if(h?.length)return s.status(409).json({error:'Meja ini punya riwayat sesi, tidak bisa dihapus'});
    await db.from('workspaces').delete().eq('id',w.id)}
  s.json({ok:true});
}));

app.post('/api/admin/students/:nim/password',adminAuth,wrap(async(q,s)=>{
  const password=String(q.body.password||'');
  if(!pwOk(password))return s.status(400).json({error:'Sandi minimal 8 karakter'});
  const{data:st}=await db.from('students').select('nim').eq('nim',q.params.nim).maybeSingle();
  if(!st)return s.status(404).json({error:'NIM tidak ditemukan di daftar mahasiswa'});
  await db.from('students').update({password_hash:await hashPw(password)}).eq('nim',q.params.nim);
  fails.delete(q.params.nim);
  s.json({ok:true});
}));
app.get('/api/admin/registrations',adminAuth,wrap(async(q,s)=>{
  const{data}=await db.from('registrations').select('nim,name,major,phone,status,created_at,decided_at').order('created_at',{ascending:false}).limit(200);
  s.json((data||[]).sort((a,b)=>(b.status==='pending')-(a.status==='pending')));
}));
app.post('/api/admin/registrations/:nim/:act',adminAuth,wrap(async(q,s)=>{
  const{nim,act}=q.params;if(!['approve','reject'].includes(act))return s.status(400).json({error:'Aksi tidak valid'});
  const{data:r}=await db.from('registrations').select('*').eq('nim',nim).maybeSingle();
  if(!r)return s.status(404).json({error:'Pendaftaran tidak ditemukan'});
  if(act==='approve')await db.from('students').upsert({nim:r.nim,name:r.name,major:r.major,phone:r.phone,...(r.password_hash?{password_hash:r.password_hash}:{})},{onConflict:'nim'});
  await db.from('registrations').update({status:act==='approve'?'approved':'rejected',decided_at:new Date().toISOString(),password_hash:null}).eq('nim',nim);
  sendWa(r.phone,act==='approve'?`Pendaftaran NIM ${r.nim} di Ruang Kita disetujui. Silakan login dengan NIM kamu.`:`Pendaftaran NIM ${r.nim} di Ruang Kita ditolak. Hubungi admin untuk info lebih lanjut.`);
  s.json({ok:true});
}));

app.listen(process.env.PORT||3000,()=>console.log('Server jalan'));