// Заготовка на майбутній Stripe/покупку
import { createCheckout } from "./api.js";

document.addEventListener("DOMContentLoaded", ()=>{
  const btn = document.getElementById("btn-buy");
  if (!btn) return;

  btn.addEventListener("click", async ()=>{
    btn.disabled = true;
    try {
      const item_id = Number(btn.dataset.id);
      const r = await createCheckout({ item_id });
      // очікуємо { url: "https://stripe/checkout..." } або { ok:true, order_id:... }
      if (r.url) location.href = r.url;
      else alert("Замовлення створено.");
    } catch (e) {
      console.error(e); alert("Помилка оформлення.");
    } finally { btn.disabled = false; }
  });
});

