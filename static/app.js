
'use strict';

const State = {
  token: null,
  userId: null,
  userName: null,
  role: 'student',
  onboarding: null,
  persona: null,
  session: null,          
  lastFinish: null,       
  examMode: false,        
  viewingPast: false,     
  stage: 'auto',          
};


function saveUser(){ try{
  localStorage.setItem('calibr.user', JSON.stringify({id:State.userId, name:State.userName, token:State.token, role:State.role, stage:State.stage}));
}catch(e){} }
function loadUser(){ try{
  const r = JSON.parse(localStorage.getItem('calibr.user')||'null');
  if(r&&r.id&&r.token){ State.userId=r.id; State.userName=r.name; State.token=r.token; State.role=r.role||'student'; State.stage=r.stage||'auto'; return true; }
}catch(e){} return false; }
function logout(){ try{ localStorage.removeItem('calibr.user'); }catch(e){}
  State.token=null; State.userId=null; State.userName=null; State.session=null;
  State.lastFinish=null; State.examMode=false;
  document.getElementById('whoami').hidden=true; setNavEnabled(false);
  authTab('login'); go('auth'); }


async function api(path, opts={}){
  const o = Object.assign({headers:{'Content-Type':'application/json'}}, opts);
  if(o.body && typeof o.body!=='string') o.body = JSON.stringify(o.body);
  const res = await fetch(path, o);
  if(!res.ok){
    let msg = res.status+' '+res.statusText;
    try{ const j=await res.json(); if(j.detail) msg=j.detail; }catch(e){}
    throw new Error(msg);
  }
  return res.status===204 ? null : res.json();
}


const $ = (id)=>document.getElementById(id);
const esc = (s)=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const pct = (v)=> v==null ? '—' : Math.round(v)+'%';
const LETTERS = ['a','b','c','d','e','f'];
let toastT=null;
function toast(msg){ const t=$('toast'); t.textContent=msg; t.classList.add('show');
  clearTimeout(toastT); toastT=setTimeout(()=>t.classList.remove('show'),2200); }

function setNavEnabled(on){
  document.querySelectorAll('#nav button').forEach(b=>b.disabled=!on);
}
function setActiveNav(name){
  document.querySelectorAll('#nav button').forEach(b=>
    b.classList.toggle('active', b.dataset.nav===name));
}

const SCREENS = ['auth','onboarding','catalog','topics','quiz','results','plan','analytics','progress','admin'];
function show(name){
  SCREENS.forEach(s=>{ const el=$('screen-'+s); if(el) el.classList.toggle('on', s===name); });
  window.scrollTo({top:0,behavior:'smooth'});
}
function go(name, arg){
  if(name==='auth'){ show('auth'); setActiveNav(null); return; }
  if(name==='admin'){ State.examMode=false; show('admin'); setActiveNav('admin'); loadAdmin(); return; }
  if(name==='catalog'){ State.examMode=false; show('catalog'); setActiveNav('catalog'); loadCatalog(); return; }
  if(name==='analytics'){ State.examMode=false; show('analytics'); setActiveNav('analytics'); loadAnalytics(); return; }
  if(name==='progress'){ State.examMode=false; show('progress'); setActiveNav('progress'); loadProgress(); return; }
  if(name==='onboarding'){ show('onboarding'); setActiveNav(null); return; }
  if(name==='topics'){ State.examMode=false; show('topics'); setActiveNav('catalog'); loadTopics(arg); return; }
  show(name); setActiveNav(null);
}

const GA = {x0:34, x1:566, y:60, vw:600, vh:96};      // gauge geometry
const thetaX = (t)=>{ const c=Math.max(-3,Math.min(3,t)); return GA.x0 + (c+3)/6*(GA.x1-GA.x0); };

function buildGauge(theta, level){
  const x = thetaX(theta);
  let ticks='';
  for(let t=-3;t<=3;t++){
    const tx=thetaX(t), major=(t===0);
    ticks += `<line x1="${tx}" y1="${GA.y-(major?13:8)}" x2="${tx}" y2="${GA.y+(major?13:8)}"
      stroke="${major?'#9a9cc4':'#cdd0e6'}" stroke-width="${major?2:1.4}"/>
      <text x="${tx}" y="${GA.y+30}" text-anchor="middle" font-family="IBM Plex Mono" font-size="11"
      fill="${major?'#6e7193':'#a8abca'}">${t>0?'+':''}${t}</text>`;
  }
  return `
  <div class="gauge-read">
    <span class="val" id="g-val">θ = ${theta>0?'+':''}${theta.toFixed(2)}</span>
    <span class="lab" id="g-lab">${esc(level||'')}</span>
  </div>
  <div class="gauge-wrap">
  <svg class="gx" viewBox="0 0 ${GA.vw} ${GA.vh}" role="img" aria-label="Шкала уровня θ от -3 до 3, текущее значение ${theta.toFixed(2)}">
    <defs>
      <linearGradient id="gband" x1="0" x2="1">
        <stop offset="0" stop-color="#f0c0cb"/><stop offset="0.5" stop-color="#f3d9ab"/><stop offset="1" stop-color="#a8e0d4"/>
      </linearGradient>
      <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="3.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>
    </defs>
    <rect x="${GA.x0}" y="${GA.y-4}" width="${GA.x1-GA.x0}" height="8" rx="4" fill="url(#gband)" opacity=".55"/>
    ${ticks}
    <g class="needle" id="g-needle" transform="translate(${x},0)">
      <line x1="0" y1="${GA.y-22}" x2="0" y2="${GA.y+16}" stroke="#5b5bd6" stroke-width="2.4" stroke-linecap="round"/>
      <circle cx="0" cy="${GA.y-3}" r="8.5" fill="#5b5bd6" filter="url(#glow)"/>
      <circle cx="0" cy="${GA.y-3}" r="3.4" fill="#fff"/>
    </g>
  </svg>
  </div>`;
}
function moveGauge(theta, level){
  const n=$('g-needle'); if(n) n.setAttribute('transform',`translate(${thetaX(theta)},0)`);
  const v=$('g-val'); if(v) v.textContent = `θ = ${theta>0?'+':''}${theta.toFixed(2)}`;
  const l=$('g-lab'); if(l && level) l.textContent = level;
}

function sparkline(series, {w=600,h=150,pad=22}={}){
  const pts = (series||[]).map((d,i)=> typeof d==='number' ? {i:i+1,theta:d} : {i:d.i??i+1,theta:d.theta,ok:d.is_correct});
  if(pts.length===0) return `<div class="empty small">Пока нет точек.</div>`;
  const n=pts.length;
  const X=(i)=> pad + (n===1?0.5:(i-1)/(n-1))*(w-2*pad);
  const Y=(t)=> { const c=Math.max(-3,Math.min(3,t)); return (h-pad) - ((c+3)/6)*(h-2*pad); };
  let grid='';
  [-3,-1.5,0,1.5,3].forEach(t=>{ const y=Y(t);
    grid+=`<line x1="${pad}" y1="${y}" x2="${w-pad}" y2="${y}" stroke="${t===0?'#d7dAeb':'#eef0f8'}" stroke-width="1"/>
    <text x="${pad-6}" y="${y+3}" text-anchor="end" font-family="IBM Plex Mono" font-size="9.5" fill="#a8abca">${t>0?'+':''}${t}</text>`;});
  const line = pts.map((p,k)=>`${k?'L':'M'}${X(p.i).toFixed(1)},${Y(p.theta).toFixed(1)}`).join(' ');
  const area = `M${X(pts[0].i)},${h-pad} `+pts.map(p=>`L${X(p.i).toFixed(1)},${Y(p.theta).toFixed(1)}`).join(' ')+` L${X(pts[n-1].i)},${h-pad} Z`;
  const dots = pts.map(p=>{
    const col = p.ok===undefined ? '#5b5bd6' : (p.ok?'#1fa98f':'#e0566e');
    return `<circle cx="${X(p.i).toFixed(1)}" cy="${Y(p.theta).toFixed(1)}" r="3.6" fill="${col}" stroke="#fff" stroke-width="1.4"/>`;
  }).join('');
  return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Динамика θ по вопросам">
    <defs><linearGradient id="spk" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="#5b5bd6" stop-opacity=".18"/><stop offset="1" stop-color="#5b5bd6" stop-opacity="0"/>
    </linearGradient></defs>
    ${grid}<path d="${area}" fill="url(#spk)"/>
    <path d="${line}" fill="none" stroke="#5b5bd6" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
    ${dots}</svg>`;
}

function authTab(which){
  document.querySelectorAll('#auth-seg button').forEach(b=>b.classList.toggle('on', b.dataset.auth===which));
  $('auth-login').hidden = which!=='login';
  $('auth-register').hidden = which!=='register';
  authErr('');
}
function authErr(msg){ const e=$('auth-err'); if(!e) return;
  e.textContent=msg||''; e.hidden=!msg; }

async function afterAuth(res){
  State.token=res.token; State.userId=res.user_id; State.userName=res.name;
  State.role=res.role||'student'; saveUser();
  $('whoami').hidden=false; $('whoami-name').textContent=res.name||res.username||'Студент';
  applyRole(); setNavEnabled(true);
  if(State.role==='admin'){ go('admin'); return; }
  if(res.has_profile){ go('catalog'); }
  else { go('onboarding'); }
}

function applyRole(){
  const admin = State.role==='admin';
  const btn=$('nav-admin'); if(btn) btn.hidden=!admin;
  const wr=$('whoami-role'); if(wr){ wr.textContent = admin?'администратор':'студент'; }
  const sp=$('stage-pick'); if(sp) sp.hidden = admin;
  if(!admin) populateStages();
}

const STAGE_HINTS = {
  grade_1: '1 класс — задачи начального уровня. Сложность адаптируется.',
  grade_2: '2 класс — задачи начального уровня. Сложность адаптируется.',
  grade_3: '3 класс. Сложность адаптируется от начального к лёгкому.',
  grade_4: '4 класс. Сложность адаптируется от начального к лёгкому.',
  grade_5: '5 класс. Сложность адаптируется от начального к лёгкому.',
  grade_6: '6 класс. Сложность адаптируется от лёгкого к среднему.',
  grade_7: '7 класс. Сложность адаптируется от лёгкого к среднему.',
  grade_8: '8 класс. Сложность адаптируется от среднего к сложному.',
  grade_9: '9 класс. Сложность адаптируется от среднего к сложному.',
  grade_10:'10 класс. Сложность адаптируется от сложного к экспертному.',
  grade_11:'11 класс (выпускной). Сложность адаптируется.',
  primary: '1–4 класс (диапазон). Сложность адаптируется.',
  easy:    '5–6 класс (диапазон). Сложность адаптируется.',
  medium:  '7–8 класс (диапазон). Сложность адаптируется.',
  hard:    '9–10 класс (диапазон). Сложность адаптируется.',
  expert:  '11 класс (выпускной). Сложность адаптируется.',
  auto:    'Сложность подстраивается под ваш уровень (θ) без ограничений.',
};

const STAGE_ORDER = [
  'grade_1','grade_2','grade_3','grade_4','grade_5','grade_6',
  'grade_7','grade_8','grade_9','grade_10','grade_11','auto'
];

function populateStages(){
  const sel=$('stage-select'); if(!sel) return;
  const raw=(State.onboarding&&State.onboarding.stages)||[];
  const stageMap={}; raw.forEach(s=>stageMap[s.id]=s);
  const stages = STAGE_ORDER.map(id=>stageMap[id]).filter(Boolean);
  sel.innerHTML = stages.map(s=>`<option value="${s.id}" ${s.id===State.stage?'selected':''}>${esc(s.label)}</option>`).join('');
  const h=$('stage-hint'); if(h) h.textContent=STAGE_HINTS[State.stage]||'';
}
function setStage(id){
  State.stage=id; saveUser();
  const h=$('stage-hint'); if(h) h.textContent=STAGE_HINTS[id]||'';
}

async function doLogin(){
  const username=$('login-username').value.trim();
  const password=$('login-password').value;
  if(!username||!password){ authErr('Введите логин и пароль.'); return; }
  const btn=$('btn-login'); btn.disabled=true; const old=btn.innerHTML; btn.innerHTML='<span class="spin"></span> Входим…';
  try{
    const res=await api('/auth/login',{method:'POST',body:{username,password}});
    await afterAuth(res);
  }catch(e){ authErr(e.message||'Не удалось войти.'); }
  finally{ btn.disabled=false; btn.innerHTML=old; }
}

async function doRegister(){
  const name=$('reg-name').value.trim();
  const username=$('reg-username').value.trim();
  const password=$('reg-password').value;
  if(username.length<3){ authErr('Логин — минимум 3 символа.'); return; }
  if(password.length<4){ authErr('Пароль — минимум 4 символа.'); return; }
  const btn=$('btn-register'); btn.disabled=true; const old=btn.innerHTML; btn.innerHTML='<span class="spin"></span> Создаём…';
  try{
    const res=await api('/auth/register',{method:'POST',body:{username,password,name:name||username}});
    await afterAuth(res);
  }catch(e){ authErr(e.message||'Не удалось зарегистрироваться.'); }
  finally{ btn.disabled=false; btn.innerHTML=old; }
}

async function loadOnboarding(){
  const d = await api('/onboarding');
  State.onboarding = d;

  const order = ['Начинающий','Средний','Сильный'];
  const lp = {'Начинающий':'Мало практики, начинаю с азов',
              'Средний':'База есть, нужно укрепить',
              'Сильный':'Уверенно, хочу сложное'};
  const names = Object.keys(d.presets||{}).sort((a,b)=>order.indexOf(a)-order.indexOf(b));
  $('personas').innerHTML = names.map(n=>`
    <div class="card pad persona" data-p="${esc(n)}" onclick="pickPersona('${esc(n)}')" tabindex="0"
         onkeydown="if(event.key==='Enter')pickPersona('${esc(n)}')">
      <div class="tag">${n==='Сильный'?'★★★':n==='Средний'?'★★':'★'} профиль</div>
      <h3>${esc(n)}</h3>
      <div class="lp">${esc(lp[n]||'')}</div>
    </div>`).join('');

  if(!d.groq){
    const note = document.createElement('div');
    note.className='small muted'; note.style.marginTop='14px';
    note.innerHTML='Работаем на курированном банке вопросов (ключ Groq не задан) — адаптивность IRT полностью активна.';
    $('assess-slot').appendChild(note);
  }
}
function pickPersona(name){
  State.persona = name;
  document.querySelectorAll('.persona').forEach(c=>c.classList.toggle('sel', c.dataset.p===name));
}
async function createUser(){
  const btn=$('btn-start'); btn.disabled=true; const old=btn.innerHTML; btn.innerHTML='<span class="spin"></span> Начинаем…';
  try{
    if($('username') && $('username').value.trim()){ State.userName=$('username').value.trim(); saveUser(); }
    const presets = (State.onboarding && State.onboarding.presets) || {};
    const features = State.persona ? (presets[State.persona] || null) : null;
    const res = await api(`/users/${State.userId}/profile`,{method:'POST',body:{features, behavior: null}});
    $('whoami').hidden=false; $('whoami-name').textContent=State.userName||'Студент'; setNavEnabled(true);

    if(res.assessment){
      const a=res.assessment;
      $('assess-slot').innerHTML = `
        <div class="card pad assess">
          <div><div class="pm">${pct(a.p_mastery*100)}</div>
            <div class="tiny mono muted" style="margin-top:4px">P(ОСВОЕНИЯ) · LEARNERPROFILENET</div></div>
          <div style="flex:1;min-width:220px">
            <div class="small muted" style="margin-bottom:4px">Стартовый уровень</div>
            <div style="font-family:var(--display);font-weight:700;font-size:20px;color:var(--ink)">${esc(a.level||'')} · θ ${a.start_theta>0?'+':''}${a.start_theta}</div>
            <div class="small muted" style="margin-top:6px">С него начнётся адаптивный подбор. Переходим к предметам…</div>
          </div>
          <button class="btn primary" onclick="go('catalog')">К предметам <span class="arr">→</span></button>
        </div>`;
      $('assess-slot').scrollIntoView({behavior:'smooth',block:'center'});
    } else {
      go('catalog');
    }
  }catch(e){ toast('Не удалось сохранить профиль: '+e.message); }
  finally{ btn.disabled=false; btn.innerHTML=old; }
}

async function loadCatalog(){
  const slot=$('subjects'); slot.innerHTML='<div class="loading"><span class="spin"></span> Загружаем предметы…</div>';
  try{
    const stageParam = (State.stage && State.stage !== 'auto') ? `&stage=${encodeURIComponent(State.stage)}` : '';
    const d = await api('/subjects?user_id='+State.userId+stageParam);
    slot.innerHTML = d.subjects.map(s=>{
      const m = s.mastery_pct;
      const lvl = s.level ? `${esc(s.level)} · θ ${s.theta>0?'+':''}${s.theta}` : 'Ещё не начато';
      return `<div class="card pad subj" onclick="go('topics','${esc(s.name)}')" tabindex="0"
                onkeydown="if(event.key==='Enter')go('topics','${esc(s.name)}')">
        <div class="ico">${s.icon||'📘'}</div>
        <h3>${esc(s.name)}</h3>
        <div class="lv">${lvl}</div>
        <div class="meter" style="margin-top:12px"><i style="width:${m||0}%"></i></div>
        <div class="foot"><span class="nt">${s.topics_total} тем</span>
          <span class="mono small" style="color:var(--accent)">${m==null?'':pct(m)}</span></div>
      </div>`;
    }).join('');
  }catch(e){ slot.innerHTML=`<div class="empty">Ошибка: ${esc(e.message)}</div>`; }
}

let _subjectForTopics=null;
async function loadTopics(subject){
  if(subject) _subjectForTopics=subject;
  subject=_subjectForTopics;
  $('tp-subject').textContent=subject; $('tp-title').textContent=subject;
  $('tp-subject-test').onclick=()=>startSession({scope:'subject',subject});
  const slot=$('topics'); slot.innerHTML='<div class="loading"><span class="spin"></span> Загружаем темы…</div>';
  try{
    const d = await api(`/subjects/${encodeURIComponent(subject)}/topics?user_id=${State.userId}`);
    const STBADGE = {
      not_started:['grey','Не начато'], in_progress:['indigo','В процессе'],
      gap:['rose','Пробел'], strong:['teal','Освоено']
    };
    slot.innerHTML = d.topics.map(t=>{
      const [cls,lab]=STBADGE[t.status]||STBADGE.not_started;
      const m=t.mastery_pct;
      return `<div class="topic ${t.recommended?'rec':''}" onclick="startSession({scope:'topic',subject:'${esc(subject)}',topic:'${esc(t.topic)}'})"
                tabindex="0" onkeydown="if(event.key==='Enter')startSession({scope:'topic',subject:'${esc(subject)}',topic:'${esc(t.topic)}'})">
        <div class="tinfo">
          <h3>${esc(t.topic)}</h3>
          <div class="concept">${esc(t.concept||'')}</div>
          <div class="status-row">
            <span class="badge ${cls}"><span class="dot" style="background:currentColor"></span>${lab}</span>
            ${t.recommended?'<span class="badge amber">Рекомендуем</span>':''}
            ${t.attempts?`<span class="tiny mono muted">${t.attempts} ответов</span>`:''}
          </div>
        </div>
        <div class="tmeter"><div class="meter ${t.status==='strong'?'teal':'indigo'}"><i style="width:${m||0}%"></i></div>
          <div class="tiny mono muted" style="text-align:right;margin-top:4px">${m==null?'нет данных':pct(m)}</div></div>
        <svg class="go" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 6l6 6-6 6"/></svg>
      </div>`;
    }).join('');
  }catch(e){ slot.innerHTML=`<div class="empty">Ошибка: ${esc(e.message)}</div>`; }
}

async function startSession({scope,subject=null,topic=null}){
  try{
    const body={user_id:State.userId, scope, subject, topic, q_limit:25, stage:State.stage||'auto'};
    const s = await api('/sessions',{method:'POST',body});
    State.session={id:s.session_id, scope, subject, topic, qLimit:s.q_limit};
    State.viewingPast=false;
    go_quiz_crumbs();
    show('quiz'); setActiveNav(null);
    await nextQuestion();
  }catch(e){ toast('Не удалось начать тест: '+e.message); }
}
function go_quiz_crumbs(){
  const s=State.session; const c=$('quiz-crumbs');
  const scopeLabel = s.scope==='all'?'Полная диагностика':s.scope==='subject'?esc(s.subject):`${esc(s.subject)} · ${esc(s.topic)}`;
  c.innerHTML = `<button onclick="abandonQuiz()">← Выйти</button><span class="sep">/</span><span>${scopeLabel}</span>`;
}
function abandonQuiz(){ if(confirm('Выйти из теста? Прогресс по ответам сохранён.')){ go('catalog'); } }

async function nextQuestion(){
  const slot=$('quiz-slot');
  slot.innerHTML='<div class="card pad"><div class="loading"><span class="spin"></span> Подбираем вопрос под ваш уровень…</div></div>';
  let q;
  try{ q = await api(`/sessions/${State.session.id}/question`); }
  catch(e){ slot.innerHTML=`<div class="card pad empty">Ошибка: ${esc(e.message)}<br><button class="btn" style="margin-top:12px" onclick="nextQuestion()">Повторить</button></div>`; return; }

  if(q.done){ return finishSession(q); }

  $('quiz-prog').style.width = Math.round((q.index-1)/q.total*100)+'%';
  $('quiz-count').textContent = `${q.index} / ${q.total}`;
  $('quiz-gauge').innerHTML = buildGauge(q.theta, q.level);

  const actionBadge = q.action_label
    ? `<span class="badge indigo">${esc(q.action_label)}</span>` : '';
  slot.innerHTML = `
    <div class="card qcard">
      <div class="qmeta">
        <span class="badge grey">${esc(q.subject)} · ${esc(q.topic)}</span>
        <span class="stars" title="Сложность">${q.difficulty_stars||''}</span>
        ${actionBadge}
      </div>
      <div class="qtext">${esc(q.question)}</div>
      <div class="opts" id="opts">
        ${q.options.map((o,i)=>`
          <button class="opt" data-l="${LETTERS[i]}" onclick="answer('${LETTERS[i]}')">
            <span class="key">${LETTERS[i].toUpperCase()}</span><span>${esc(o)}</span>
          </button>`).join('')}
      </div>
    </div>`;
}

async function answer(letter){
  document.querySelectorAll('.opt').forEach(b=>b.disabled=true);
  let d;
  try{ d = await api(`/sessions/${State.session.id}/answer`,{method:'POST',body:{answer:letter}}); }
  catch(e){ toast('Ошибка: '+e.message); document.querySelectorAll('.opt').forEach(b=>b.disabled=false); return; }

  document.querySelectorAll('.opt').forEach(b=>{
    if(b.dataset.l===d.correct_answer) b.classList.add('correct','reveal');
    else if(b.dataset.l===letter) b.classList.add('wrong','shake');
  });
  moveGauge(d.theta, d.level);

  renderFeedback(d);
}

function renderFeedback(d){
  const ok=d.is_correct;
  const dth = d.delta_theta;
  const dthStr = (dth>0?'+':'')+dth.toFixed(2);
  const blocks = [];
  if(d.explanation) blocks.push(`<div class="blk"><span class="lbl">Почему так</span><div>${esc(d.explanation)}</div></div>`);
  if(!ok && d.common_mistake) blocks.push(`<div class="blk"><span class="lbl">Частая ошибка</span><div>${esc(d.common_mistake)}</div></div>`);
  let miscHTML='';
  if(!ok && d.misconception){
    const m=d.misconception;
    const steps=(m.corrective_steps||[]).map(s=>`<li>${esc(s)}</li>`).join('');
    miscHTML = `<div class="misc">
      <div class="mt"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>${esc(m.type||'Разбор ошибки')}</div>
      ${m.description?`<div class="small">${esc(m.description)}</div>`:''}
      ${m.hint?`<div class="small"><b>Подсказка:</b> ${esc(m.hint)}</div>`:''}
      ${steps?`<div class="small"><b>Как исправить:</b><ol>${steps}</ol></div>`:''}
    </div>`;
  }
  const correctNote = (!ok && d.correct_option)
    ? `<div class="blk"><span class="lbl">Верный ответ</span><div><b>${esc(d.correct_answer.toUpperCase())}.</b> ${esc(d.correct_option)}</div></div>` : '';

  const fb = document.createElement('div');
  fb.className = 'fb '+(ok?'ok':'no');
  fb.innerHTML = `
    <div class="verdict">
      <span class="em">${ok?'✓':'✕'}</span>
      <span>${ok?'Верно':'Неверно'}</span>
      <span class="dth" title="Изменение уровня θ">θ ${dthStr}</span>
    </div>
    <div class="body">${correctNote}${blocks.join('')}${miscHTML}</div>
    <div class="foot"><button class="btn primary" id="fb-next" onclick="nextQuestion()">Дальше <span class="arr">→</span></button></div>`;
  $('quiz-slot').appendChild(fb);
  fb.scrollIntoView({behavior:'smooth',block:'nearest'});
  setTimeout(()=>{ const n=$('fb-next'); if(n)n.focus(); },60);
}

function outcomeTabs(active){
  const tab=(key,label)=>`<button class="${active===key?'on':''}" onclick="outcomeGo('${key}')">${label}</button>`;
  return `<div class="outcome-bar">
    ${tab('results','Итоги')}
    ${tab('plan','Рекомендации')}
    ${tab('analytics','Аналитика')}
    <button class="retry" onclick="outcomeGo('retry')">↻ Ещё тест</button>
  </div>`;
}
function outcomeGo(which){
  State.examMode=true;
  if(which==='results'){
    show('results'); setActiveNav(null);
    if(State.lastFinish) renderResults(State.lastFinish);   // из кэша, без повторного finish
    return;
  }
  if(which==='plan'){
    if(State.viewingPast && State.session) loadSessionPlan(State.session.id);
    else makePlan();
    return;
  }
  if(which==='analytics'){ show('analytics'); setActiveNav(null); loadAnalytics(); return; }
  if(which==='retry'){ retryScope(); return; }
}

async function openPastSession(sid){
  try{
    const r = await api(`/sessions/${sid}/summary?token=${encodeURIComponent(State.token||'')}`);
    State.lastFinish=r;
    State.session={id:sid, scope:r.scope, subject:r.subject, topic:r.topic};
    State.viewingPast=true; State.examMode=true;
    show('results'); setActiveNav(null);
    renderResults(r);
  }catch(e){ toast('Не удалось открыть тест: '+e.message); }
}

async function loadSessionPlan(sid){
  show('plan'); setActiveNav(null);
  const slot=$('plan-slot'); slot.innerHTML='<div class="card pad"><div class="loading"><span class="spin"></span> Загружаем рекомендации…</div></div>';
  try{
    const r = await api(`/sessions/${sid}/plan?token=${encodeURIComponent(State.token||'')}`);
    if(!r || r.plan===null || !r.items){ return makePlan(); }   // плана ещё нет — сгенерируем
    renderPlan(r, true);
  }catch(e){ slot.innerHTML=`<div class="empty">Ошибка: ${esc(e.message)}</div>`; }
}

async function finishSession(doneInfo){
  $('quiz-slot').innerHTML='<div class="card pad"><div class="loading"><span class="spin"></span> Собираем итоги…</div></div>';
  $('quiz-prog').style.width='100%';
  try{
    const r = await api(`/sessions/${State.session.id}/finish`,{method:'POST'});
    State.lastFinish=r; State.examMode=true; State.viewingPast=false;
    show('results'); setActiveNav(null);
    renderResults(r, doneInfo);
  }catch(e){ toast('Ошибка при подведении итогов: '+e.message); }
}

function renderResults(r, doneInfo){
  $('oc-results').innerHTML = State.examMode ? outcomeTabs('results') : '';
  const title = r.scope==='topic' ? `${esc(r.subject)} · ${esc(r.topic)}`
             : r.scope==='subject' ? esc(r.subject) : 'Полная диагностика';
  $('res-title').textContent = 'Итоги: '+title;
  const score=Math.round(r.overall_score||0);
  const ring=`<svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="52" fill="none" stroke="#eceef7" stroke-width="12"/>
    <circle cx="60" cy="60" r="52" fill="none" stroke="#5b5bd6" stroke-width="12" stroke-linecap="round"
      stroke-dasharray="${(score/100*2*Math.PI*52).toFixed(1)} 999" transform="rotate(-90 60 60)"/></svg>`;
  const dth=r.delta_theta||0;
  const reason = doneInfo&&doneInfo.reason==='confident'
    ? 'Тест завершён досрочно: оценка уровня стала достаточно точной (низкая ошибка SE).' : '';

  const mistakes = (r.mistakes||[]);
  const mlist = mistakes.length? mistakes.map(m=>`
    <div class="mistake"><div style="flex:1">
      <div class="qn">${esc(m.question)}</div>
      <div class="status-row">${m.type?`<span class="badge rose">${esc(m.type)}</span>`:''}
        <span class="tiny mono muted">${esc(m.topic)} · ${esc(m.difficulty)}</span></div>
      ${m.hint?`<div class="small muted" style="margin-top:5px">${esc(m.hint)}</div>`:''}
    </div></div>`).join('') : '<div class="empty small">Ошибок нет — отличная работа!</div>';

  const cats=(r.mistake_categories||[]);
  const catHTML = cats.length? `<div class="card pad"><h3 style="margin-bottom:12px">Типы ошибок</h3>${
    cats.map(c=>mistcatRow(c)).join('')}</div>` : '';

  $('results-slot').innerHTML = `
    <div class="card pad" style="margin-bottom:16px">
      <div class="score-hero">
        <div class="score-ring">${ring}<div class="num"><b>${score}%</b><span>точность</span></div></div>
        <div style="flex:1">
          <div class="kpis">
            <div class="kpi"><div class="k">Уровень θ</div><div class="v">${r.theta>0?'+':''}${r.theta} <span class="small muted">${esc(r.level||'')}</span></div></div>
            <div class="kpi"><div class="k">Освоение</div><div class="v">${pct(r.mastery_pct)}</div></div>
            <div class="kpi"><div class="k">Изменение θ</div><div class="v ${dth>0?'up':dth<0?'down':''}">${dth>0?'+':''}${dth}</div></div>
            <div class="kpi"><div class="k">Ответов</div><div class="v">${r.correct}/${r.answered}</div></div>
          </div>
          ${reason?`<div class="small muted" style="margin-top:12px">${reason}</div>`:''}
        </div>
      </div>
    </div>

    <div class="grid cols-2" style="align-items:start">
      <div class="card pad trend-card">
        <h3 style="margin-bottom:6px">Траектория уровня за сессию</h3>
        <div class="small muted" style="margin-bottom:8px">Как θ менялся после каждого ответа.</div>
        ${sparkline(r.theta_series)}
      </div>
      <div class="card pad">
        <h3 style="margin-bottom:12px">Разбор ошибок</h3>
        <div class="stack" style="gap:10px">${mlist}</div>
      </div>
    </div>

    ${catHTML}`;
}
function mistcatRow(c){
  return `<div class="mistcat">
    <div style="flex:0 0 auto;min-width:160px"><b class="small">${esc(c.type)}</b>
      <div class="tiny muted">${esc((c.topics||[]).slice(0,3).join(', '))}</div></div>
    <div class="mbar"><i style="width:${c.share||0}%"></i></div>
    <div class="mc">${c.count}× · ${c.share}%</div></div>`;
}
function retryScope(){ const s=State.session; if(!s) return go('catalog');
  startSession({scope:s.scope,subject:s.subject,topic:s.topic}); }

async function makePlan(){
  show('plan'); setActiveNav(null);
  const slot=$('plan-slot'); slot.innerHTML='<div class="card pad"><div class="loading"><span class="spin"></span> Генерируем план под ваши результаты…</div></div>';
  try{
    const sid = State.session ? State.session.id : '';
    const r = await api(`/users/${State.userId}/plan${sid?('?session_id='+sid):''}`,{method:'POST'});
    if(!r.ok){ slot.innerHTML=`<div class="empty"><div class="ec">📝</div><h3>${esc(r.message||'Недостаточно данных')}</h3><div class="small">Пройдите хотя бы один тест, чтобы получить рекомендации.</div></div>`; return; }
    renderPlan(r);
  }catch(e){ slot.innerHTML=`<div class="empty">Ошибка: ${esc(e.message)}</div>`; }
}

async function loadLatestPlan(){
  const slot=$('plan-slot'); slot.innerHTML='<div class="loading"><span class="spin"></span> Загружаем план…</div>';
  try{
    const r = await api(`/users/${State.userId}/plan`);
    if(!r || r.plan===null || !r.items){ slot.innerHTML=`<div class="empty"><div class="ec">📝</div><h3>Плана пока нет</h3><div class="small">Пройдите тест и нажмите «Получить рекомендации».</div></div>`; return; }
    renderPlan(r, true);
  }catch(e){ slot.innerHTML=`<div class="empty">Ошибка: ${esc(e.message)}</div>`; }
}

function renderPlan(r, fromSaved=false){
  $('plan-intro').textContent = r.intro || 'План построен из ваших результатов.';
  const b=r.blocks||{};
  const blocks=[];

  if(b.priorities) blocks.push(planBlock(1,'Приоритетные темы', b.priorities.map(p=>`
    <div class="prio"><div class="pi"><b>${esc(p.subject)} · ${esc(p.topic)}</b>
      <div class="why">${esc(p.reason||'')}${p.gap?` · пробел ${p.gap.gap_pct}% [${esc(p.gap.domain)}]`:''}</div></div>
      <span class="badge ${p.theta<-0.2?'rose':p.theta>=0.6?'teal':'indigo'}">${pct(p.mastery_pct)}</span></div>`).join('')));

  if(b.exercises) blocks.push(planBlock(2,'Упражнения', b.exercises.map(e=>`
    <div><div class="small" style="font-weight:600;margin-bottom:4px">${esc(e.subject)} · ${esc(e.topic)}</div>
      <ul class="exlist">${(e.exercises||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`).join('')));

  if(b.resources) blocks.push(planBlock(3,'Материалы', b.resources.map(rs=>`
    <div><div class="small" style="font-weight:600;margin-bottom:6px">${esc(rs.subject)} · ${esc(rs.topic)}</div>
      <div class="reslist">${(rs.resources||[]).map(x=>`
        <a class="reslink" href="${esc(x.url)}" target="_blank" rel="noopener">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M10 13a5 5 0 007 0l3-3a5 5 0 00-7-7l-1 1"/><path d="M14 11a5 5 0 00-7 0l-3 3a5 5 0 007 7l1-1"/></svg>
          <span class="t">${esc(x.title)}</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--muted)"><path d="M7 17L17 7M9 7h8v8"/></svg>
        </a>`).join('')}</div></div>`).join('')));

  if(r.items) blocks.push(planBlock(4,'План по дням', `<div class="stack" style="gap:8px" id="plan-items">${
    r.items.map(it=>checkItem(it)).join('')}</div>
    <div class="small muted" style="margin-top:6px">Отмечайте выполненное — прогресс сохраняется.</div>`));

  if(b.criteria) blocks.push(planBlock(5,'Критерии достижения', b.criteria.map(c=>`
    <div class="crititem"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1fa98f" stroke-width="2.2" style="flex:0 0 auto;margin-top:2px"><path d="M5 12l4 4L19 6"/></svg>
      <div><b class="small">${esc(c.subject)} · ${esc(c.topic)}</b><div class="small muted">${esc(c.criterion)}</div></div></div>`).join('')));

  const badge = r.model_used
    ? '<span class="badge indigo">Приоритеты: модель рекомендаций × θ</span>'
    : '<span class="badge grey">Приоритеты: по уровню θ</span>';

  $('plan-slot').innerHTML = `${State.examMode?outcomeTabs('plan'):''}<div class="row wrap" style="margin-bottom:16px">${badge}
    ${fromSaved?'':'<span class="badge teal">Свежий план</span>'}</div>
    <div class="stack">${blocks.join('')}</div>`;
}
function planBlock(n,title,inner){
  return `<div class="planblock"><div class="h"><span class="n">${n}</span><h3>${esc(title)}</h3></div><div class="c">${inner}</div></div>`;
}
function checkItem(it){
  const done=!!it.done;
  return `<label class="checkitem ${done?'done':''}" data-id="${it.id}">
    <input type="checkbox" ${done?'checked':''} onchange="toggleItem(${it.id}, this.checked)">
    <span class="day">День ${it.day}</span><span class="task">${esc(it.task)}</span></label>`;
}
async function toggleItem(id, done){
  const el=document.querySelector(`.checkitem[data-id="${id}"]`);
  if(el) el.classList.toggle('done', done);
  try{ await api(`/plan_items/${id}`,{method:'PATCH',body:{done}}); }
  catch(e){ toast('Не сохранилось: '+e.message); }
}

async function loadAnalytics(){
  const slot=$('analytics-slot'); slot.innerHTML='<div class="loading"><span class="spin"></span> Считаем аналитику…</div>';
  try{
    const d = await api(`/users/${State.userId}/analytics`);
    if((d.overall?.answered||0)===0){
      slot.innerHTML=`<div class="empty"><div class="ec">📊</div><h3>Данных пока нет</h3><div class="small">Пройдите тест — здесь появятся освоение, слабые темы и разбор ошибок.</div>
        <button class="btn primary" style="margin-top:16px" onclick="go('catalog')">Выбрать предмет</button></div>`; return;
    }
    const o=d.overall;
    const subjBars = (d.subject_mastery||[]).map(s=>barRow(s.subject, s.mastery_pct, `θ ${s.theta>0?'+':''}${s.theta} · ${pct(s.accuracy)} точн.`)).join('')
      || '<div class="empty small">Нет начатых предметов.</div>';
    const weak=(d.weak||[]), strong=(d.strong||[]);
    const weakTags = weak.length? weak.map(t=>`<span class="concept-tag weak">${esc(t.topic)} · ${pct(t.mastery_pct)}</span>`).join(' ') : '<span class="muted small">Слабых тем не выявлено.</span>';
    const strongTags = strong.length? strong.map(t=>`<span class="concept-tag strong">${esc(t.topic)} · ${pct(t.mastery_pct)}</span>`).join(' ') : '<span class="muted small">Пока нет освоенных тем.</span>';
    const heat=(d.topic_mastery||[]).map(t=>`<div class="cell"><div class="cn">${esc(t.topic)}</div>
      <div class="cv">${esc(t.subject)} · θ ${t.theta>0?'+':''}${t.theta} · ${pct(t.mastery_pct)}</div>
      <div class="meter ${t.theta>=0.6?'teal':t.theta<-0.2?'':'indigo'}" style="margin-top:7px"><i style="width:${t.mastery_pct||0}%"></i></div></div>`).join('')
      || '<div class="empty small">Нет данных по темам.</div>';
    const cats=(d.mistake_categories||[]);
    const catHTML = cats.length? cats.map(c=>mistcatRow(c)).join('') : '<div class="empty small">Ошибок не зафиксировано.</div>';

    slot.innerHTML = `
      ${State.examMode?outcomeTabs('analytics'):''}
      <div class="grid cols-3" style="margin-bottom:18px">
        <div class="statcard"><div class="lab">Всего ответов</div><div class="big">${o.answered}</div></div>
        <div class="statcard"><div class="lab">Средняя точность</div><div class="big">${Math.round(o.accuracy||0)}<span class="suf">%</span></div></div>
        <div class="statcard"><div class="lab">Среднее освоение</div><div class="big">${o.avg_mastery_pct==null?'—':Math.round(o.avg_mastery_pct)}<span class="suf">%</span></div></div>
      </div>

      <div class="sec-title"><h2>Освоение по предметам</h2><div class="rule"></div></div>
      <div class="card pad"><div class="bars">${subjBars}</div></div>

      <div class="grid cols-2" style="margin-top:18px;align-items:start">
        <div class="card pad"><h3 style="margin-bottom:12px">Сильные концепции</h3><div class="row wrap" style="gap:8px">${strongTags}</div></div>
        <div class="card pad"><h3 style="margin-bottom:12px">Слабые концепции (пробелы)</h3><div class="row wrap" style="gap:8px">${weakTags}</div></div>
      </div>

      <div class="sec-title"><h2>Карта тем</h2><div class="rule"></div></div>
      <div class="heat">${heat}</div>

      <div class="sec-title"><h2>Типы ошибок</h2><div class="rule"></div></div>
      <div class="card pad">${catHTML}</div>`;
  }catch(e){ slot.innerHTML=`<div class="empty">Ошибка: ${esc(e.message)}</div>`; }
}
function barRow(name, value, right){
  return `<div class="barrow"><div class="nm" title="${esc(name)}">${esc(name)}</div>
    <div class="meter indigo"><i style="width:${value||0}%"></i></div>
    <div class="rt">${right?esc(right):pct(value)}</div></div>`;
}

async function loadProgress(){
  const slot=$('progress-slot'); slot.innerHTML='<div class="loading"><span class="spin"></span> Загружаем прогресс…</div>';
  try{
    const d = await api(`/users/${State.userId}/analytics`);
    const sessions=(d.sessions||[]);
    if(sessions.length===0){
      slot.innerHTML=`<div class="empty"><div class="ec">📈</div><h3>Прогресс появится после первого теста</h3>
        <button class="btn primary" style="margin-top:16px" onclick="go('catalog')">Начать</button></div>`; return;
    }
    const cov = Object.entries(d.coverage||{}).map(([s,c])=>{
      const p = c.total? Math.round(c.started/c.total*100):0;
      return `<div class="barrow"><div class="nm">${esc(s)}</div><div class="meter"><i style="width:${p}%"></i></div>
        <div class="rt">${c.started}/${c.total} тем</div></div>`;
    }).join('');
    const fmt = (iso)=>{ if(!iso) return ''; const dt=new Date(iso.replace(' ','T')+(iso.includes('Z')?'':'Z'));
      return isNaN(dt)? iso : dt.toLocaleString('ru-RU',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}); };
    const tl = sessions.map(s=>{
      const scopeL = s.scope==='topic'?`${esc(s.subject)} · ${esc(s.topic)}`:s.scope==='subject'?esc(s.subject):'Полная диагностика';
      const st = s.status==='finished'?'<span class="badge teal">завершён</span>':'<span class="badge grey">активен</span>';
      const clickable = s.status==='finished';
      return `<div class="tl ${clickable?'clickable':''}" ${clickable?`onclick="openPastSession(${s.id})" tabindex="0" onkeydown="if(event.key==='Enter')openPastSession(${s.id})"`:''}>
        <div class="marker"><div class="pin"></div><div class="line"></div></div>
        <div class="ev"><div class="when">${fmt(s.started_at)}</div>
          <div class="what">${scopeL} ${clickable?'<span class="arr-open">→ открыть итоги</span>':''}</div>
          <div class="status-row">${st}<span class="tiny mono muted">${s.answered} ответов · ${pct(s.accuracy)} точн.</span></div></div></div>`;
    }).join('');

    const startedSubjects=(d.subject_mastery||[]).map(s=>s.subject);
    slot.innerHTML = `
      <div class="grid cols-3" style="margin-bottom:18px">
        <div class="statcard"><div class="lab">Сессий пройдено</div><div class="big">${sessions.filter(s=>s.status==='finished').length}</div></div>
        <div class="statcard"><div class="lab">Всего ответов</div><div class="big">${d.overall.answered}</div></div>
        <div class="statcard"><div class="lab">Средняя точность</div><div class="big">${Math.round(d.overall.accuracy||0)}<span class="suf">%</span></div></div>
      </div>
      <div class="sec-title"><h2>Динамика уровня θ</h2><div class="rule"></div></div>
      <div class="grid cols-2" id="trend-grid">${startedSubjects.length?'':'<div class="empty small">Нет данных для графиков.</div>'}</div>

      <div class="sec-title"><h2>Охват программы</h2><div class="rule"></div></div>
      <div class="card pad"><div class="bars">${cov}</div></div>

      <div class="sec-title"><h2>История сессий</h2><div class="rule"></div></div>
      <div class="card pad"><div class="timeline">${tl}</div></div>`;

    const grid=$('trend-grid');
    for(const subj of startedSubjects){
      try{
        const t = await api(`/users/${State.userId}/trend?subject=${encodeURIComponent(subj)}`);
        const card=document.createElement('div'); card.className='card pad trend-card';
        card.innerHTML=`<h3 style="margin-bottom:8px">${esc(subj)}</h3>${sparkline(t.series)}`;
        grid.appendChild(card);
      }catch(e){/* skip */}
    }
  }catch(e){ slot.innerHTML=`<div class="empty">Ошибка: ${esc(e.message)}</div>`; }
}

async function loadAdmin(){
  const slot=$('admin-slot'); slot.innerHTML='<div class="loading"><span class="spin"></span> Загружаем панель…</div>';
  const t=encodeURIComponent(State.token||'');
  try{
    const [ov,uu]=await Promise.all([api(`/admin/overview?token=${t}`), api(`/admin/users?token=${t}`)]);
    renderAdmin(ov, uu.users||[]);
  }catch(e){ slot.innerHTML=`<div class="empty"><div class="ec">🔒</div><h3>${esc(e.message)}</h3></div>`; }
}

function renderAdmin(ov, users){
  const tBar=(theta)=>Math.max(2,Math.round((theta+3)/6*100));
  const weak=(ov.weakest_topics||[]).map(t=>`<div class="barrow"><div class="nm">${esc(t.subject)} · ${esc(t.topic)}</div>
    <div class="meter"><i style="width:${tBar(t.avg_theta)}%"></i></div>
    <div class="rt">θ ${t.avg_theta>0?'+':''}${t.avg_theta} · ${t.learners} уч.</div></div>`).join('')
    || '<div class="empty small">Пока нет данных по темам.</div>';

  const rows=users.map(u=>{
    const nm=(u.name||u.username).replace(/'/g,'');
    return `<tr>
    <td><b>${esc(u.name||u.username)}</b><div class="tiny mono muted">@${esc(u.username)}</div></td>
    <td>${u.role==='admin'?'<span class="badge indigo">админ</span>':'<span class="badge grey">студент</span>'}</td>
    <td class="num">${u.sessions}</td>
    <td class="num">${u.answered}</td>
    <td class="num">${u.answered?pct(u.accuracy):'—'}</td>
    <td class="num">${u.avg_theta==null?'—':(u.avg_theta>0?'+':'')+u.avg_theta}</td>
    <td class="ar">${u.role==='admin'?'':
      `<button class="btn tiny" onclick="adminViewUser(${u.user_id},'${nm}')">Тесты</button>
       <button class="btn tiny danger" onclick="adminDeleteUser(${u.user_id},'${nm}')">Удалить</button>`}</td></tr>`;
  }).join('');

  $('admin-slot').innerHTML=`
    <div class="grid cols-4" style="margin-bottom:18px">
      <div class="statcard"><div class="lab">Студентов</div><div class="big">${ov.students}</div></div>
      <div class="statcard"><div class="lab">Тестов пройдено</div><div class="big">${ov.finished_sessions}</div></div>
      <div class="statcard"><div class="lab">Всего ответов</div><div class="big">${ov.answered}</div></div>
      <div class="statcard"><div class="lab">Средняя точность</div><div class="big">${Math.round(ov.accuracy||0)}<span class="suf">%</span></div></div>
    </div>
    <div class="sec-title"><h2>Самые сложные темы для студентов</h2><div class="rule"></div></div>
    <p class="muted small" style="margin-top:-8px;margin-bottom:12px">Темы с самой низкой средней θ по всем учащимся — кандидаты на доработку программы.</p>
    <div class="card pad"><div class="bars">${weak}</div></div>
    <div class="sec-title"><h2>Пользователи</h2><div class="rule"></div></div>
    <div class="card pad atable-wrap"><table class="atable">
      <thead><tr><th>Пользователь</th><th>Роль</th><th class="num">Тесты</th><th class="num">Ответы</th><th class="num">Точн.</th><th class="num">Ср. θ</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <div id="admin-user-sessions"></div>
    <div id="admin-content"></div>`;
  loadAdminContent();
}


let ADMIN_CAT = {catalog:[], difficulties:[]};
async function loadAdminContent(){
  const box=$('admin-content'); if(!box) return;
  try{ ADMIN_CAT = await api(`/admin/catalog?token=${encodeURIComponent(State.token||'')}`); }
  catch(e){ box.innerHTML=`<div class="empty small">Контент: ${esc(e.message)}</div>`; return; }
  const subjOpts = ADMIN_CAT.catalog.map(s=>`<option value="${esc(s.subject)}">${esc(s.icon||'')} ${esc(s.subject)}</option>`).join('');
  const diffOpts = (ADMIN_CAT.difficulties||[]).map(d=>`<option value="${d.id}">${esc(d.label)}</option>`).join('');
  box.innerHTML=`
    <div class="sec-title"><h2>Управление контентом</h2><div class="rule"></div></div>
    <div class="grid cols-2" style="align-items:start">
      <div class="card pad">
        <h3 style="margin-top:0">Новый предмет</h3>
        <div class="field"><label>Иконка (эмодзи)</label><input id="ac-subj-icon" maxlength="2" placeholder="🌍" style="width:80px"></div>
        <div class="field"><label>Название предмета</label><input id="ac-subj-name" placeholder="Например: География"></div>
        <button class="btn primary" onclick="acAddSubject()">Добавить предмет</button>
      </div>
      <div class="card pad">
        <h3 style="margin-top:0">Новая тема</h3>
        <div class="field"><label>Предмет</label><select id="ac-topic-subject">${subjOpts}</select></div>
        <div class="field"><label>Тема</label><input id="ac-topic-name" placeholder="Например: Материки"></div>
        <div class="field"><label>Ключевой концепт (необяз.)</label><input id="ac-topic-concept" placeholder="Континенты Земли"></div>
        <button class="btn primary" onclick="acAddTopic()">Добавить тему</button>
      </div>
    </div>
    <div class="card pad" style="margin-top:14px">
      <h3 style="margin-top:0">Новый вопрос</h3>
      <div class="grid cols-2">
        <div class="field"><label>Предмет</label><select id="ac-q-subject" onchange="acSyncTopics()">${subjOpts}</select></div>
        <div class="field"><label>Тема</label><select id="ac-q-topic"></select></div>
      </div>
      <div class="field"><label>Сложность (класс)</label><select id="ac-q-diff">${diffOpts}</select></div>
      <div class="field"><label>Текст вопроса</label><input id="ac-q-text" placeholder="Вопрос…"></div>
      <div class="grid cols-2">
        <div class="field"><label>Вариант A</label><input id="ac-q-a"></div>
        <div class="field"><label>Вариант B</label><input id="ac-q-b"></div>
        <div class="field"><label>Вариант C</label><input id="ac-q-c"></div>
        <div class="field"><label>Вариант D</label><input id="ac-q-d"></div>
      </div>
      <div class="grid cols-2">
        <div class="field"><label>Правильный</label><select id="ac-q-correct"><option value="a">A</option><option value="b">B</option><option value="c">C</option><option value="d">D</option></select></div>
        <div class="field"><label>Объяснение (необяз.)</label><input id="ac-q-expl"></div>
      </div>
      <button class="btn primary" onclick="acAddQuestion()">Добавить вопрос</button>
      <span class="tiny muted" id="ac-q-count" style="margin-left:10px"></span>
    </div>
    <div class="card pad" style="margin-top:14px">
      <h3 style="margin-top:0">Догенерировать вопросы (Groq)</h3>
      <p class="small muted" style="margin-top:0">Добавьте минимум 3 вопроса в тему вручную — затем Groq продолжит сам. Сгенерированные нужно перепроверить и одобрить.</p>
      <div class="grid cols-2">
        <div class="field"><label>Предмет</label><select id="ac-gen-subject" onchange="acSyncGenTopics()">${subjOpts}</select></div>
        <div class="field"><label>Тема</label><select id="ac-gen-topic"></select></div>
      </div>
      <div class="field"><label>Сколько сгенерировать</label><input id="ac-gen-n" type="number" value="5" min="1" max="10" style="width:90px"></div>
      <button class="btn" onclick="acGenerate()">Сгенерировать через Groq</button>
    </div>
    <div id="ac-pending"></div>`;
  acSyncTopics(); acSyncGenTopics(); acLoadPending();
}
function _topicsOf(subject){ const s=(ADMIN_CAT.catalog||[]).find(x=>x.subject===subject); return s?s.topics:[]; }
function acSyncTopics(){ const sub=$('ac-q-subject').value; $('ac-q-topic').innerHTML=_topicsOf(sub).map(t=>`<option>${esc(t)}</option>`).join(''); }
function acSyncGenTopics(){ const sub=$('ac-gen-subject').value; $('ac-gen-topic').innerHTML=_topicsOf(sub).map(t=>`<option>${esc(t)}</option>`).join(''); }
const _tk=()=>encodeURIComponent(State.token||'');
async function acAddSubject(){
  const name=$('ac-subj-name').value.trim(), icon=$('ac-subj-icon').value.trim()||'📘';
  if(!name) return toast('Введите название предмета');
  try{ await api(`/admin/subjects?token=${_tk()}`,{method:'POST',body:{name,icon}}); toast('Предмет добавлен'); loadAdminContent(); }
  catch(e){ toast('Ошибка: '+e.message); }
}
async function acAddTopic(){
  const subject=$('ac-topic-subject').value, topic=$('ac-topic-name').value.trim(), concept=$('ac-topic-concept').value.trim();
  if(!topic) return toast('Введите тему');
  try{ await api(`/admin/topics?token=${_tk()}`,{method:'POST',body:{subject,topic,concept}}); toast('Тема добавлена'); loadAdminContent(); }
  catch(e){ toast('Ошибка: '+e.message); }
}
async function acAddQuestion(){
  const subject=$('ac-q-subject').value, topic=$('ac-q-topic').value, difficulty=$('ac-q-diff').value;
  const question=$('ac-q-text').value.trim();
  const options=[$('ac-q-a').value.trim(),$('ac-q-b').value.trim(),$('ac-q-c').value.trim(),$('ac-q-d').value.trim()].filter(x=>x);
  const correct=$('ac-q-correct').value, explanation=$('ac-q-expl').value.trim();
  if(!topic) return toast('Сначала выберите/создайте тему');
  if(!question||options.length<2) return toast('Заполните вопрос и минимум 2 варианта');
  try{
    const r=await api(`/admin/questions?token=${_tk()}`,{method:'POST',body:{subject,topic,difficulty,question,options,correct,explanation}});
    $('ac-q-text').value='';['a','b','c','d'].forEach(x=>$('ac-q-'+x).value='');$('ac-q-expl').value='';
    $('ac-q-count').textContent=`В теме одобрено: ${r.approved_in_topic}`;
    toast('Вопрос добавлен');
  }catch(e){ toast('Ошибка: '+e.message); }
}
async function acGenerate(){
  const subject=$('ac-gen-subject').value, topic=$('ac-gen-topic').value, n=parseInt($('ac-gen-n').value)||5;
  if(!topic) return toast('Выберите тему');
  toast('Генерация…');
  try{ const r=await api(`/admin/questions/generate?token=${_tk()}`,{method:'POST',body:{subject,topic,n}});
    toast(`Сгенерировано: ${r.generated}. Проверьте ниже.`); acLoadPending(); }
  catch(e){ toast('Ошибка: '+e.message); }
}
async function acLoadPending(){
  const box=$('ac-pending'); if(!box) return;
  try{ const r=await api(`/admin/questions?token=${_tk()}&status=pending`); const qs=r.questions||[];
    if(!qs.length){ box.innerHTML=''; return; }
    box.innerHTML=`<div class="sec-title"><h2>На проверке (${qs.length})</h2><div class="rule"></div></div>`+
      qs.map(q=>`<div class="card pad" style="margin-bottom:10px">
        <div class="tiny mono muted">${esc(q.subject)} · ${esc(q.topic)} · ${esc(q.difficulty)} · ${esc(q.source)}</div>
        <div style="font-weight:600;margin:6px 0">${esc(q.question)}</div>
        <ol type="a" style="margin:0 0 8px 18px">${(q.options||[]).map((o,i)=>`<li ${'abcd'[i]===q.correct?'style="color:var(--teal,#1FA98F);font-weight:600"':''}>${esc(o)}</li>`).join('')}</ol>
        ${q.explanation?`<div class="small muted">${esc(q.explanation)}</div>`:''}
        <div class="ar" style="margin-top:8px">
          <button class="btn tiny" onclick="acApprove(${q.id})">Одобрить</button>
          <button class="btn tiny danger" onclick="acDeleteQ(${q.id})">Удалить</button></div></div>`).join('');
  }catch(e){ box.innerHTML=`<div class="empty small">${esc(e.message)}</div>`; }
}
async function acApprove(id){ try{ await api(`/admin/questions/${id}/approve?token=${_tk()}`,{method:'POST'}); toast('Одобрено'); acLoadPending(); }catch(e){ toast('Ошибка: '+e.message); } }
async function acDeleteQ(id){ try{ await api(`/admin/questions/${id}?token=${_tk()}`,{method:'DELETE'}); toast('Удалено'); acLoadPending(); }catch(e){ toast('Ошибка: '+e.message); } }

async function adminViewUser(uid, name){
  const box=$('admin-user-sessions');
  box.innerHTML=`<div class="sec-title"><h2>Тесты: ${esc(name)}</h2><div class="rule"></div></div><div class="card pad"><div class="loading"><span class="spin"></span> Загрузка…</div></div>`;
  const fmt=(iso)=>{ if(!iso) return ''; const dt=new Date(iso.replace(' ','T')+(iso.includes('Z')?'':'Z')); return isNaN(dt)?iso:dt.toLocaleString('ru-RU',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}); };
  try{
    const r=await api(`/admin/users/${uid}/sessions?token=${encodeURIComponent(State.token||'')}`);
    const list=(r.sessions||[]).map(s=>{
      const scopeL=s.scope==='topic'?`${esc(s.subject)} · ${esc(s.topic)}`:s.scope==='subject'?esc(s.subject):'Полная диагностика';
      return `<div class="tl"><div class="marker"><div class="pin"></div><div class="line"></div></div>
        <div class="ev"><div class="when">${fmt(s.started_at)}</div><div class="what">${scopeL}</div>
        <div class="status-row"><span class="badge ${s.status==='finished'?'teal':'grey'}">${s.status==='finished'?'завершён':'активен'}</span>
        <span class="tiny mono muted">${s.answered} ответов · ${pct(s.accuracy)} точн.</span></div></div></div>`;
    }).join('')||'<div class="empty small">Тестов нет.</div>';
    box.innerHTML=`<div class="sec-title"><h2>Тесты: ${esc(name)}</h2><div class="rule"></div></div><div class="card pad"><div class="timeline">${list}</div></div>`;
    box.scrollIntoView({behavior:'smooth',block:'start'});
  }catch(e){ box.innerHTML=`<div class="empty">Ошибка: ${esc(e.message)}</div>`; }
}

async function adminDeleteUser(uid, name){
  if(!confirm(`Удалить пользователя «${name}» и все его данные? Действие необратимо.`)) return;
  try{
    await api(`/admin/users/${uid}?token=${encodeURIComponent(State.token||'')}`,{method:'DELETE'});
    toast('Пользователь удалён'); loadAdmin();
  }catch(e){ toast('Ошибка: '+e.message); }
}


function loadAI(){
  const d=State.onboarding||{};
  const m=d.model, r=d.recommender;
  const card=(title,tag,rows,note)=>`<div class="card pad" style="margin-bottom:14px">
    <div class="row" style="justify-content:space-between;align-items:baseline">
      <h3 style="margin:0">${title}</h3><span class="badge indigo">${tag}</span></div>
    <table class="atable" style="margin-top:10px"><tbody>${rows}</tbody></table>
    ${note?`<div class="small muted" style="margin-top:10px">${note}</div>`:''}</div>`;
  const row=(k,v)=>`<tr><td class="muted">${k}</td><td class="num"><b>${v}</b></td></tr>`;

  const lpn = m ? card('1. LearnerProfileNet — нейросеть стартовой оценки','model.pkl',
      row('Архитектура', esc(m.arch||'9→64→32→1'))+
      row('Эпох обучения', m.epochs??'—')+
      row('Точность (val_acc)', m.val_acc!=null?(m.val_acc*100).toFixed(1)+'%':'—')+
      row('ROC-AUC (val)', m.val_auc!=null?m.val_auc.toFixed(3):'—')+
      row('Порог', m.threshold??'—'),
      'Полносвязная сеть на 9 признаках профиля обучения. Предсказывает P(освоения) → '+
      'стартовый уровень θ для адаптивного теста. Forward-pass на NumPy.')
    : '<div class="empty small">model.pkl не загружен.</div>';

  const irt = card('2. IRT — адаптивная оценка уровня (модель Раша 1PL)','движок',
      row('Шкала θ', '−3 … +3')+
      row('Уровни сложности', (d.grade_bands?Object.keys(d.grade_bands).length:5)+' (от 1–4 кл. до 11 кл.)')+
      row('Обновление θ', 'онлайн, после каждого ответа')+
      row('Критерий остановки', 'SE(θ) или лимит вопросов'),
      'После каждого ответа θ пересчитывается; следующий вопрос подбирается так, чтобы его '+
      'трудность b была близка к θ−0.3 (зона ближайшего развития). Точность θ оценивается через информацию Фишера.');

  const rec = r ? card('3. RecommendationModel — прогноз пробелов','recommender.pkl',
      row('Модель', esc(r.model_name||'Multi-Output Random Forest'))+
      row('ROC-AUC', r.auc!=null?(typeof r.auc==='number'?r.auc.toFixed(3):r.auc):'—')+
      row('Домены', Object.keys(r.labels_ru||{}).length||3)+
      row('Признаков на входе', r.ranges?Object.keys(r.ranges).length:'—'),
      'Случайный лес по поведенческим признакам предсказывает вероятность пробела по доменам '+
      '(математика / естеств. науки / языки). Эти вероятности задают приоритеты в плане рекомендаций.')
    : '<div class="empty small">recommender.pkl не загружен.</div>';

  const misc = card('4. Детектор заблуждений','правила + LLM',
      row('Уровень 1', 'правила по ключевым словам')+
      row('Уровень 2', 'LLM (Groq) при наличии ключа')+
      row('Статус LLM', d.groq?'подключён':'офлайн (только правила)'),
      'Классифицирует тип ошибки и формирует подсказку — это попадает в обратную связь после ответа и в разбор ошибок.');

  $('ai-slot').innerHTML = `
    <div class="card pad" style="margin-bottom:14px;background:rgba(91,91,214,.04)">
      <p style="margin:0">Система объединяет <b>четыре компонента ИИ</b>. Все модели обучены на данных и
      загружаются из артефактов проекта — цифры ниже считываются из них вживую.</p>
    </div>
    <div class="grid cols-2" style="align-items:start">${lpn}${irt}</div>
    <div class="grid cols-2" style="align-items:start">${rec}${misc}</div>
    <div class="sec-title"><h2>Как это работает вместе</h2><div class="rule"></div></div>
    <div class="card pad"><ol style="margin:0;padding-left:20px;line-height:1.9">
      <li><b>Старт:</b> LearnerProfileNet по профилю даёт P(освоения) → стартовый θ.</li>
      <li><b>Адаптация:</b> IRT после каждого ответа уточняет θ и подбирает сложность (с учётом выбранной ступени).</li>
      <li><b>Диагностика:</b> детектор заблуждений объясняет ошибки.</li>
      <li><b>Рекомендации:</b> Random Forest оценивает пробелы → персональный план обучения.</li>
    </ol></div>`;
}


(async function boot(){
  setNavEnabled(false);
  try{ await loadOnboarding(); }catch(e){  }
  if(loadUser()){
    try{
      const me = await api('/auth/me?token='+encodeURIComponent(State.token));
      State.userId=me.user_id; State.userName=me.name; State.role=me.role||'student'; saveUser();
      $('whoami').hidden=false; $('whoami-name').textContent=me.name||me.username||'Студент';
      applyRole(); setNavEnabled(true);
      if(State.role==='admin') go('admin');
      else if(me.has_profile) go('catalog'); else go('onboarding');
      return;
    }catch(e){  }
  }
  authTab('login'); go('auth');
})();
