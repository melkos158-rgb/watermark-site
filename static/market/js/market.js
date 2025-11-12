// static/market/js/market.js
// Загальний ініт маркету: пошук, друга шапка, модалка
const $ = (s, r=document) => r.querySelector(s);

function goWithParams(next = {}) {
  const p = new URLSearchParams(location.search);
  Object.entries(next).forEach(([k, v]) => (v==null || v==="") ? p.delete(k) : p.set(k, v));
  p.set("page", "1");
  location.search = p.toString();
}

document.addEventListener("DOMContentLoaded", () => {
  const q     = $("#q");
  const cat   = $("#cat");
  const sort  = $("#sort");
  const btnS  = $("#btn-search");
  const modal = $("#upload-modal");

  // Пошук
  btnS?.addEventListener("click", () => goWithParams({ q: q?.value || "" }));
  q?.addEventListener("keydown", (e)=>{ if(e.key==="Enter") goWithParams({ q: q.value }); });

  // Фільтри
  cat?.addEventListener("change", ()=> goWithParams({ cat: cat.value }));
  sort?.addEventListener("change",()=> goWithParams({ sort: sort.value }));

  // Модалка «Додати модель»
  const openBtn   = $("#btn-upload");
  const closeBtn  = modal?.querySelector("[data-close]");
  const xBtn      = modal?.querySelector(".modal-close");
  const free      = modal?.querySelector('input[name="is_free"]');
  const priceRow  = modal?.querySelector(".price-row");
  const titleInp  = modal?.querySelector('input[name="title"]');

  const syncPriceVis = ()=> priceRow && (priceRow.style.display = free?.checked ? "none" : "flex");

  function openModal(e){
    if (e) e.preventDefault();
    if (!modal) return;
    modal.hidden = false;
    document.body.style.overflow = "hidden";
    // автофокус на назву моделі
    setTimeout(()=> titleInp?.focus(), 0);
  }
  function closeModal(){
    if (!modal) return;
    modal.hidden = true;
    document.body.style.overflow = "";
  }

  openBtn?.addEventListener("click", openModal);
  closeBtn?.addEventListener("click", closeModal);
  xBtn?.addEventListener("click", closeModal);

  // закриття по кліку на бекдроп
  modal?.addEventListener("click", (e)=>{
    if (e.target === modal) closeModal();
  });
  // закриття по Esc
  document.addEventListener("keydown", (e)=>{
    if (e.key === "Escape" && modal && !modal.hidden) closeModal();
  });

  // Ціна: показувати/ховати поле
  free?.addEventListener("change", syncPriceVis);
  syncPriceVis();
});
