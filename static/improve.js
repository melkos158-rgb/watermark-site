const panel = document.getElementById('improve-panel');
const closeBtn = document.getElementById('improve-close');
const list = document.getElementById('improve-list');
const sendBtn = document.getElementById('improve-send');
const inTitle = document.getElementById('improve-title');
const inBody  = document.getElementById('improve-body');
const hint    = document.getElementById('improve-hint');

let items = [];
const esc = s => (s||'').replace(/[&<>"']/g,m=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[m]));

function render(){
  list.innerHTML='';
  items.forEach(it=>{
    const el = document.createElement('div');
    el.className='s-card';
    el.innerHTML = `
      <div class="s-top">
        <div class="s-title">${esc(it.title)}</div>
        <div class="s-meta">👍 ${it.likes} · 💬 ${it.comments_count}</div>
      </div>
      ${it.body ? `<div class="s-body" style="margin-top:6px; white-space:pre-wrap;">${esc(it.body)}</div>`:''}
      <div class="s-actions">
        <button class="like-btn" data-id="${it.id}">👍</button>
        <button class="cmt-btn"  data-id="${it.id}">› Коментарі</button>
      </div>
      <div class="comments" id="cwrap-${it.id}">
        <div class="comment-list" id="clist-${it.id}"></div>
        <div class="comment-add">
          <input type="text" id="cinput-${it.id}" placeholder="Написати коментар…">
          <button data-id="${it.id}" class="cadd">Надіслати</button>
        </div>
      </div>`;
    list.appendChild(el);
  });
}

async function load(){ const r=await fetch('/api/suggestions'); const j=await r.json(); if(j.ok){ items=j.items; render(); } }
async function post(){
  const title=inTitle.value.trim(), body=inBody.value.trim();
  if(!title){ hint.textContent='Введи назву ідеї.'; return; }
  sendBtn.disabled=true; hint.textContent='Публікуємо (-1 PXP)...';
  const r=await fetch('/api/suggestions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,body})});
  const j=await r.json(); sendBtn.disabled=false;
  if(!j.ok){ hint.textContent=j.error==='not_enough_pxp'?'Недостатньо PXP.':(j.error==='auth_required'?'Увійдіть у профіль.':'Помилка.'); return; }
  inTitle.value=''; inBody.value=''; hint.textContent='Опубліковано!';
  items.unshift(j.item); render();
}
async function like(id){ const r=await fetch(`/api/suggestions/${id}/like`,{method:'POST'}); const j=await r.json(); if(j.ok){ const it=items.find(x=>x.id===id); if(it){ it.likes++; render(); } } }
async function toggleComments(id){
  const wrap=document.getElementById(`cwrap-${id}`); const show=wrap.style.display!=='block';
  wrap.style.display=show?'block':'none'; if(!show) return;
  const r=await fetch(`/api/suggestions/${id}/comments`); const j=await r.json(); if(!j.ok) return;
  const ul=document.getElementById(`clist-${id}`); ul.innerHTML='';
  j.items.forEach(c=>{ const d=document.createElement('div'); d.className='comment'; d.innerHTML=`<strong>${esc(c.author_name||c.author_email||'')}:</strong> ${esc(c.body)}`; ul.appendChild(d); });
}
async function addComment(id){
  const inp=document.getElementById(`cinput-${id}`); const body=inp.value.trim(); if(!body) return;
  const r=await fetch(`/api/suggestions/${id}/comments`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({body})});
  const j=await r.json(); if(j.ok){ inp.value=''; toggleComments(id); toggleComments(id); const it=items.find(x=>x.id===id); if(it){ it.comments_count++; render(); } }
}

document.addEventListener('DOMContentLoaded', ()=>{ if(panel){ load(); } });
closeBtn.addEventListener('click', ()=> panel.style.display='none');
sendBtn.addEventListener('click', post);
list.addEventListener('click', e=>{
  if(e.target.classList.contains('like-btn')) like(parseInt(e.target.dataset.id));
  if(e.target.classList.contains('cmt-btn'))  toggleComments(parseInt(e.target.dataset.id));
  if(e.target.classList.contains('cadd'))     addComment(parseInt(e.target.dataset.id));
});
setInterval(()=>{ if(panel && panel.style.display!=='none') load(); },20000);
