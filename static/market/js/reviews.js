// static/market/js/reviews.js
// =====================================================
// Мінімальна логіка рейтингу/відгуків для STL Market
// =====================================================
import { postReview } from "./api.js";

const $ = (s, r = document) => r.querySelector(s);

function bindStars(container) {
  const stars = [...container.querySelectorAll("[data-star]")];
  let value = Number(container.dataset.value || 0);
  const paint = (v) => stars.forEach((s, i) => s.classList.toggle("on", i < v));
  paint(value);

  stars.forEach((s, i) => {
    s.addEventListener("mouseenter", () => paint(i + 1));
    s.addEventListener("mouseleave", () => paint(value));
    s.addEventListener("click", () => {
      value = i + 1;
      container.dataset.value = value;
      paint(value);
      showStarToast(`Оцінка: ${value} ⭐`);
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".rating-input").forEach(bindStars);

  const f = $("#review-form");
  if (!f) return;

  const msgBox = document.createElement("div");
  msgBox.className = "review-msg";
  f.appendChild(msgBox);

  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    const item_id = Number(f.dataset.itemId);
    const rating = Number(f.querySelector(".rating-input")?.dataset.value || 0);
    const text = f.querySelector("textarea")?.value?.trim() || "";

    if (!rating) {
      showError("Оціни модель (мін. 1 зірка)");
      return;
    }

    const btn = f.querySelector("button[type='submit']");
    const oldText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "⏳ Надсилання...";

    try {
      const r = await postReview({ item_id, rating, text });
      if (r.ok) {
        showSuccess("Відгук додано ✔");
        setTimeout(() => location.reload(), 800);
      } else {
        showError("Не вдалося зберегти відгук.");
      }
    } catch {
      showError("Помилка мережі.");
    } finally {
      btn.disabled = false;
      btn.textContent = oldText;
    }
  });

  function showError(t) {
    msgBox.textContent = "❌ " + t;
    msgBox.className = "review-msg error";
  }
  function showSuccess(t) {
    msgBox.textContent = "✅ " + t;
    msgBox.className = "review-msg success";
  }
});

// =====================================================
// Додаткове візуальне підкріплення
// =====================================================
function showStarToast(text) {
  let toast = document.createElement("div");
  toast.className = "star-toast";
  toast.textContent = text;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.classList.add("show");
    setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => toast.remove(), 400);
    }, 1200);
  }, 10);
}

// =====================================================
// CSS для зірок та повідомлень
// =====================================================
const css = `
.rating-input{
  display:flex;
  gap:4px;
  font-size:22px;
  cursor:pointer;
}
.rating-input [data-star]{color:var(--line);transition:color .15s}
.rating-input [data-star].on{color:#facc15}
.review-msg{margin-top:8px;font-size:13px;opacity:.9}
.review-msg.error{color:#f87171}
.review-msg.success{color:#4ade80}
.star-toast{
  position:fixed;bottom:30px;left:50%;
  transform:translateX(-50%) translateY(40px);
  background:var(--card);color:var(--text);
  border:1px solid var(--line);border-radius:10px;
  padding:8px 14px;font-size:14px;opacity:0;
  transition:all .35s ease;z-index:2000;
}
.star-toast.show{
  opacity:1;
  transform:translateX(-50%) translateY(0);
}
`;
const style = document.createElement("style");
style.textContent = css;
document.head.appendChild(style);
