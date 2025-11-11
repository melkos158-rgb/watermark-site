import { toggleFav } from "./api.js";

document.addEventListener("click", async (e)=>{
  const btn = e.target.closest("#btn-fav,[data-fav]");
  if (!btn) return;

  const itemId = btn.dataset.id || btn.getAttribute("data-id");
  if (!itemId) return;

  try {
    const r = await toggleFav(Number(itemId));
    // Очікуємо { ok:true, fav:true/false }
    btn.classList.toggle("active", !!r.fav);
    btn.textContent = r.fav ? "♥ В обраному" : "♡ В обране";
  } catch (err) {
    console.error(err);
    alert("Увійди в акаунт, щоб додавати в обране.");
  }
});

