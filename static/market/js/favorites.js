import { toggleFav } from "./api.js";

// =========================================================
// favorites.js — управління обраними моделями
// =========================================================
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("#btn-fav,[data-fav]");
  if (!btn) return;

  const itemId = btn.dataset.id || btn.getAttribute("data-id");
  if (!itemId) return;

  // захист від подвійного натискання
  if (btn.dataset.loading === "1") return;
  btn.dataset.loading = "1";
  const oldText = btn.textContent;
  btn.textContent = "⏳ ...";

  try {
    const r = await toggleFav(Number(itemId));
    // Очікуємо { ok:true, fav:true/false }
    if (r && r.ok) {
      const fav = !!r.fav;
      btn.classList.toggle("active", fav);
      btn.textContent = fav ? "♥ В обраному" : "♡ В обране";

      // коротке сповіщення
      showFavToast(fav ? "Додано в обране 💖" : "Видалено з обраного 💔");
    } else if (r.status === 401) {
      alert("Увійди в акаунт, щоб додавати в обране.");
    } else {
      alert("Помилка при оновленні списку обраного.");
    }
  } catch (err) {
    console.error(err);
    alert("Увійди в акаунт, щоб додавати в обране.");
  } finally {
    btn.dataset.loading = "0";
    btn.textContent = oldText;
  }
});

// =========================================================
// 🔔 Міні-сповіщення (toast)
// =========================================================
function showFavToast(text) {
  let toast = document.createElement("div");
  toast.className = "fav-toast";
  toast.textContent = text;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.classList.add("show");
    setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => toast.remove(), 400);
    }, 1800);
  }, 10);
}

// =========================================================
// CSS
// =========================================================
const css = `
.fav-toast {
  position: fixed;
  bottom: 30px;
  left: 50%;
  transform: translateX(-50%) translateY(40px);
  background: var(--card);
  color: var(--text);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 8px 14px;
  font-size: 14px;
  opacity: 0;
  transition: all .35s ease;
  z-index: 2000;
}
.fav-toast.show {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}
#btn-fav.active, [data-fav].active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
`;
const style = document.createElement("style");
style.textContent = css;
document.head.appendChild(style);
