const panel    = document.getElementById('improve-panel');
const closeBtn = document.getElementById('improve-close');
const list     = document.getElementById('improve-list');
const ideaBox  = document.getElementById('improve-idea');
const sendBtn  = document.getElementById('improve-send');
const hint     = document.getElementById('improve-hint');

let items = [];
const esc = s => (s||'').replace(/[&<>"']/g,m=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[m]));

/* ставимо панель точно ПІД банер, щоб не заходила на кнопки */
function placeUnderBanner(){
  try{
    const banner = document.querySelector('.promo-wrap');
    const nav = document.querySelector('.navbar');
    let top;
    if (banner){
      const r = banner.getBoundingClientRect();
      top = window.scrollY + r.top + r.height + 8; // під банер
    } else if (nav){
      const r = nav.getBoundingClientRect();
      top = window.scrollY + r.bottom + 12;
    } else {
      top = 120;
    }
    panel.style.top = `${Math.max(8, Math.round(top))}px`;
  }catch(e){}
}

function render(){
  list.innerHTML = '';
  items.forEach(it=>{
    const el = document.createElement('div');
    el.className = 's-card';
    el.innerHTML = `
      <div class="s-top">
        <div class="s-idea">${esc(it.title || it.body || '')}</div>
        <button class="chev" data-id="${it.id}">›</button>
      </div>
      <div class="comments" id="cwrap-${it.id}">
        <div class="comment-list" id="clist-${it.id}"></div>
        <div class="comment-add">
          <input type="text" id="cinput-${it.id}" placeholder="Коментар…">
          <button data-id="${it.id}" class="cadd">Надіслати</button>
        </div>
      </div>
    `;
    list.appendChild(el);
  });
}

/* допоміжна: безпечно читаємо JSON або текст */
async function safeJson(resp){
  const ct = (resp.headers.get('content-type') || '').toLowerCase();
  if (ct.includes('application/json')) {
    try { return await resp.json(); } catch { return null; }
  }
  return null; // не JSON
}

async function load(){
  const resp = await fetch('/api/suggestions', { credentials:'same-origin' });
  const data = await safeJson(resp);
  if (data && data.ok){
    items = data.items;
    render();
  }
}

/* відправка ідеї */
async function postIdea(){
  const text = (ideaBox.value || '').trim();
  if(!text){ hint.textContent = 'Напишіть ідею.'; return; }
  hint.textContent = 'Відправляємо (-1 PXP)…';
  sendBtn.disabled = true;

  let resp;
  try{
    resp = await fetch('/api/suggestions', {
      method:'POST',
      headers:{ 'Content-Type':'application/json' }, // без зайвих заголовків
      credentials:'same-origin',
      body: JSON.stringify({ title: text, body: '' })
    });
  }catch(err){
    hint.textContent = 'Мережа недоступна.';
    sendBtn.disabled = false;
    return;
  }

  const data = await safeJson(resp);
  sendBtn.disabled = false;

  // не-JSON або редирект
  if (!data){
    if (resp.status === 401 || resp.redirected){
      hint.textContent = 'Увійдіть у профіль.';
    } else {
      hint.textContent = `Помилка: HTTP ${resp.status}`;
    }
    return;
  }

  // API повернуло JSON з помилкою
  if (!data.ok){
    const code = data.error || `HTTP ${resp.status}`;
    // якщо бекенд дав detail — покажемо його
    const detail = (data.detail && String(data.detail).trim()) ? ` — ${data.detail}` : '';
    hint.textContent = (
      code === 'auth_required'  ? 'Увійдіть у профіль.' :
      code === 'not_enough_pxp' ? 'Недостатньо PXP.' :
      code === 'title_required' ? 'Порожня ідея.' :
      `Помилка: ${code}${detail}`
    );
    return;
  }

  // успіх
  ideaBox.value = '';
  hint.textContent = 'Опубліковано! (-1 PXP)';
  items.unshift(data.item);
  render();
}

/* коментарі */
async function toggleComments(id){
  const wrap = document.getElementById(`cwrap-${id}`);
  const open = wrap.style.display !== 'block';
  wrap.style.display = open ? 'block' : 'none';
  if(!open) return;

  const resp = await fetch(`/api/suggestions/${id}/comments`, { credentials:'same-origin' });
  const data = await safeJson(resp);
  if(!data || !data.ok) return;

  const ul = document.getElementById(`clist-${id}`);
  ul.innerHTML = '';
  data.items.forEach(c=>{
    const d = document.createElement('div');
    d.className = 'comment';
    d.innerHTML = `<strong>${esc(c.author_name || c.author_email || '')}:</strong> ${esc(c.body)}`;
    ul.appendChild(d);
  });
}

async function addComment(id){
  const inp = document.getElementById(`cinput-${id}`);
  const body = (inp.value || '').trim();
  if(!body) return;

  const resp = await fetch(`/api/suggestions/${id}/comments`, {
    method:'POST',
    headers:{ 'Content-Type':'application/json' },
    credentials:'same-origin',
    body: JSON.stringify({ body })
  });
  const data = await safeJson(resp);
  if(data && data.ok){
    inp.value=''; toggleComments(id); toggleComments(id);
  } else if (!data && (resp.status === 401 || resp.redirected)){
    hint.textContent = 'Увійдіть у профіль.';
  } else if (data && !data.ok){
    const detail = (data.detail && String(data.detail).trim()) ? ` — ${data.detail}` : '';
    hint.textContent = `Помилка: ${data.error || 'server'}${detail}`;
  }
}

/* події */
document.addEventListener('DOMContentLoaded', ()=>{
  placeUnderBanner();
  load();
});
window.addEventListener('resize', placeUnderBanner);
closeBtn.addEventListener('click', ()=> panel.style.display='none');
sendBtn.addEventListener('click', postIdea);
ideaBox.addEventListener('keydown', (e)=>{
  if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); postIdea(); }
});
list.addEventListener('click', (e)=>{
  if(e.target.classList.contains('chev')) toggleComments(parseInt(e.target.dataset.id));
  if(e.target.classList.contains('cadd')) addComment(parseInt(e.target.dataset.id));
});

/* автооновлення списку */
setInterval(()=>{ if(panel && panel.style.display!=='none') load(); }, 20000);
