// static/market/js/viewer.js
// Ініціалізація STL/3D viewer на сторінці detail.html

import { initViewer } from "/static/js/stl_viewer.js";

document.addEventListener("DOMContentLoaded", async () => {
  const el = document.getElementById("viewer");
  if (!el) return;

  try {
    // Якщо маєш елемент статусу — додай id="status" у шаблоні
    const ctx = await initViewer({ containerId: "viewer", statusId: "status" });

    // Збережемо глобально (зручно для інших скриптів: favorites/reviews, тощо)
    window.MARKET_VIEWER = ctx;

    // Якщо у контейнера задано data-src — автоматично завантажуємо модель
    const src = el.dataset.src;
    if (src && ctx.loadModel) {
      try {
        await ctx.loadModel(src);
        console.debug("Model auto-loaded:", src);
      } catch (err) {
        console.error("Auto-load model failed:", err);
      }
    }

    // Приклад: якщо хочеш одразу режим 'stl' або 'wm'
    // ctx.setViewerMode('stl');

  } catch (e) {
    console.error("Viewer init error:", e);
  }
});
