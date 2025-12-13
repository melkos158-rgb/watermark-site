// Простий збір подій (перегляд сторінки, перегляд айтема)
import { track } from "./api.js";

document.addEventListener("DOMContentLoaded", ()=>{
  const isDetail = !!document.getElementById("viewer");
  const payload = {};
  if (isDetail) {
    const id = document.getElementById("viewer")?.dataset.itemId
            || document.getElementById("btn-fav")?.dataset.id;
    if (id) payload.item_id = Number(id);
    track("item_view", payload);
  } else {
    track("market_view");
  }

  // трек кліків по картках
  document.addEventListener("click", (e)=>{
    const a = e.target.closest(".card .thumb, .card .ttl a");
    if (!a) return;
    const id = a.closest(".card")?.dataset?.id;
    track("card_click", id ? { item_id:Number(id) } : {});
  });
});

