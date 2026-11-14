require('dotenv').config();
const express=require('express'),path=require('path'),crypto=require('crypto'),jwt=require('jsonwebtoken');
const {createClient}=require('@supabase/supabase-js');
const db=createClient(process.env.SUPABASE_URL,process.env.SUPABASE_SERVICE_KEY);
const SECRET=process.env.JWT_SECRET||'dev-secret';
const app=express();app.use(express.json());app.use(express.static(path.join(__dirname,'public')));
const sign=u=>jwt.sign({id:u.id},SECRET,{expiresIn:'12h'});
const hash=s=>crypto.createHash('sha256').update(s+SECRET).digest('hex');
const phoneNorm=p=>{p=String(p||'').replace(/\D/g,'');return p.startsWith('0')?'62'+p.slice(1):p};
const wrap=fn=>(q,s)=>fn(q,s).catch(e=>{console.error(e);s.status(500).json({error:'Terjadi kesalahan server'})});
const auth=async(q,s,n)=>{try{const{id}=jwt.verify((q.headers.authorization||'').slice(7),SECRET);
  const{data}=await db.from('users').select('*').eq('id',id).single();if(!data)throw 0;q.user=data;n()}
  catch{s.status(401).json({error:'Sesi berakhir, silakan login lagi'})}};

// ---------- AUTH ----------
app.post('/api/auth/nim',wrap(async(q,s)=>{
  const nim=String(q.body.nim||'').trim();
  const{data:st}=await db.from('students').select('*').eq('nim',nim).maybeSingle();
  if(!st)return s.status(404).json({error:'NIM tidak terdaftar'});
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
  s.json({user:q.user,session:ss});
}));

// ---------- WORKSPACE ----------
app.get('/api/workspaces',wrap(async(q,s)=>{
  const{data:ws}=await db.from('workspaces').select('*').order('code');
  const{data:ss}=await db.from('sessions').select('workspace_id,started_at').is('ended_at',null);
  const m=Object.fromEntries((ss||[]).map(x=>[x.workspace_id,x]));
  s.json(ws.map(w=>{const online=w.last_seen&&Date.now()-new Date(w.last_seen)<30000;
    return{code:w.code,name:w.name,zone:w.zone,online:!!online,distance:w.distance_cm,since:m[w.id]?.started_at||null,
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

app.listen(process.env.PORT||3000,()=>console.log('Server jalan'));
