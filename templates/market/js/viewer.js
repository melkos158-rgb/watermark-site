// static/market/js/viewer.js
// Лише підключає готовий initViewer з твого модуля і ініціалізує його на detail.html

import { initViewer } from "/static/js/stl_viewer.js";

document.addEventListener("DOMContentLoaded", async () => {
  const el = document.getElementById("viewer");
  if (!el) return;

  try {
    // Якщо маєш елемент статусу — додай id="status" у шаблоні
    const ctx = await initViewer({ containerId: "viewer", statusId: "status" });

    // Збережемо глобально (зручно для інших скриптів: favorites/reviews, тощо)
    window.MARKET_VIEWER = ctx;

    // Приклад: якщо хочеш одразу режим 'stl' або 'wm'
    // ctx.setViewerMode('stl');

  } catch (e) {
    console.error("Viewer init error:", e);
  }
});
