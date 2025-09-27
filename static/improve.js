const panel   = document.getElementById('improve-panel');
const closeBtn= document.getElementById('improve-close');
const list    = document.getElementById('improve-list');
const ideaBox = document.getElementById('improve-idea');
const hint    = document.getElementById('improve-hint');

let items = [];

const esc = s => (s||'').replace(/[&<>"']/g,m=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[m]));

/* Рендер карток: тільки текст ідеї + кнопка "›" для коментарів */
function render(){
  list.innerHTML = '';
  items.forEach(it=>{
    const card = document.createElement('div');
    card.className = 's-card';
    card.innerHTML = `
      <div class="s-top">
        <div class="s-idea">${esc(it.title || it.body || '')}</div>
        <button class="chev" data-id="${it.id}">›</button>
      </div>
      <div class="comments" id="cwrap-${it.id}">
        <div class="comment-list" id="clist-${it.id}"></div>
        <div class="comment-add">
          <input type="text" id="cinput-${it.id}" placeholder="Коментар… (Enter)">
          <button data-id="${it.id}" class="cadd">Надіслати</button>
        </div>
      </div>
    `;
    list.appendChild(card);
  });
}

/* Завантаження списку (порядок як на бекенді — ок) */
async function load(){
  const r = await fetch('/api/suggestions');
  const j = await r.json();
  if(j.ok){ items = j.items; render(); }
}

/* Відправка ідеї: одна текстова, без кнопки — Enter */
async function postIdea(){
  const text = (ideaBox.value || '').trim();
  if(!text){ hint.textContent = 'Напишіть ідею.'; return; }
  hint.textContent = 'Відправляємо (-1 PXP)...';
  const r = await fetch('/api/suggestions', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ title: text, body: '' })  // бекенду потрібен title — кладемо туди ідею
  });
  const j = await r.json();
  if(!j.ok){
    hint.textContent = j.error==='not_enough_pxp' ? 'Недостатньо PXP.' :
                       j.error==='auth_required'  ? 'Увійдіть у профіль.' :
                       'Помилка.';
    return;
  }
  ideaBox.value=''; hint.textContent='Опубліковано!';
  items.unshift(j.item); render();
}

/* Коментарі */
async function toggleComments(id){
  const wrap = document.getElementById(`cwrap-${id}`);
  const open = wrap.style.display !== 'block';
  wrap.style.display = open ? 'block' : 'none';
  if(!open) return;
  const r = await fetch(`/api/suggestions/${id}/comments`);
  const j = await r.json();
  if(!j.ok) return;
  const ul = document.getElementById(`clist-${id}`);
  ul.innerHTML = '';
  j.items.forEach(c=>{
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
  const r = await fetch(`/api/suggestions/${id}/comments`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ body })
  });
  const j = await r.json();
  if(j.ok){
    inp.value='';           // оновлюємо список коментів
    toggleComments(id); toggleComments(id);
  }
}

/* Події */
document.addEventListener('DOMContentLoaded', load);
closeBtn.addEventListener('click', ()=> panel.style.display='none');

ideaBox.addEventListener('keydown', (e)=>{
  if(e.key === 'Enter' && !e.shiftKey){
    e.preventDefault();
    postIdea();
  }
});

list.addEventListener('click', (e)=>{
  if(e.target.classList.contains('chev')){
    toggleComments(parseInt(e.target.dataset.id));
  }
  if(e.target.classList.contains('cadd')){
    addComment(parseInt(e.target.dataset.id));
  }
});

setInterval(()=>{ if(panel && panel.style.display!=='none') load(); }, 20000);
