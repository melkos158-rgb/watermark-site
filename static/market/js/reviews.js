// Мінімальна логіка рейтингу/відгуків
import { postReview } from "./api.js";
const $ = (s, r=document) => r.querySelector(s);

function bindStars(container) {
  const stars = [...container.querySelectorAll("[data-star]")];
  let value = Number(container.dataset.value || 0);
  const paint = (v)=> stars.forEach((s, i)=> s.classList.toggle("on", i < v));
  paint(value);
  stars.forEach((s, i)=>{
    s.addEventListener("mouseenter", ()=> paint(i+1));
    s.addEventListener("mouseleave", ()=> paint(value));
    s.addEventListener("click", ()=>{ value = i+1; container.dataset.value = value; });
  });
}

document.addEventListener("DOMContentLoaded", ()=>{
  document.querySelectorAll(".rating-input").forEach(bindStars);

  const f = $("#review-form");
  if (!f) return;
  f.addEventListener("submit", async (e)=>{
    e.preventDefault();
    const item_id = Number(f.dataset.itemId);
    const rating  = Number(f.querySelector(".rating-input")?.dataset.value || 0);
    const text    = f.querySelector("textarea")?.value || "";
    if (!rating) { alert("Оціни модель (мін. 1 зірка)"); return; }
    try {
      const r = await postReview({ item_id, rating, text });
      if (r.ok) location.reload(); else alert("Не вдалося зберегти відгук.");
    } catch { alert("Помилка мережі."); }
  });
});

