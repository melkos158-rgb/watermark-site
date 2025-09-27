const panel    = document.getElementById('improve-panel');
const closeBtn = document.getElementById('improve-close');
const list     = document.getElementById('improve-list');
const ideaBox  = document.getElementById('improve-idea');
const sendBtn  = document.getElementById('improve-send');
const hint     = document.getElementById('improve-hint');

let items = [];
const esc = s => (s||'').replace(/[&<>"']/g,m=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[m]));

/* ставимо панель точно під банер */
function placeUnderBanner(){
  const banner = document.querySelector('.promo-wrap');
  const nav = document.querySelector('.navbar'); // якщо є
  let top = 16;
  if (banner){
    const rect = banner.getBoundingClientRect();
    top = window.scrollY + rect.top + rect.height + 12; // трохи відступу
  } else if (nav){
    const r = nav.getBoundingClientRect();
    top = window.scrollY + r.bottom + 12;
  }
  panel.style.top = `${top}px`;
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

async function load(){
  const r = await fetch('/api/suggestions');
  const j = await r.json();
  if(j.ok){ items = j.items; render(); }
}

/* відправка ідеї */
async function postIdea(){
  const text = (ideaBox.value || '').trim();
  if(!text){ hint.textContent = 'Напишіть ідею.'; return; }
  hint.textContent = 'Відправляємо (-1 PXP)…';
  sendBtn.disabled = true;

  const r = await fetch('/api/suggestions', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ title: text, body: '' })
  });
  const j = await r.json();
  sendBtn.disabled = false;

  if(!j.ok){
    hint.textContent = j.error==='not_enough_pxp' ? 'Недостатньо PXP.' :
                       j.error==='auth_required'  ? 'Увійдіть у профіль.' :
                       'Помилка.';
    return;
  }
  ideaBox.value = '';
  hint.textContent = 'Опубліковано!';
  items.unshift(j.item);
  render();
}

/* коментарі */
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
    inp.value=''; toggleComments(id); toggleComments(id);
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
setInterval(()=>{ if(panel && panel.style.display!=='none') load(); }, 20000);
