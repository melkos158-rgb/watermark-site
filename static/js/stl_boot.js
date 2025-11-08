// static/js/stl_boot.js
// Єдина точка входу: динамічно імпортує модулі та ініціалізує сторінку.

(async () => {
  // Чекаємо, поки DOM готовий
  if (document.readyState === "loading") {
    await new Promise(res => document.addEventListener("DOMContentLoaded", res, { once: true }));
  }

  // Динамічні імпорти (щоб сторінка відкривалась швидше і було зручно ділити код)
  const [
    viewerMod,
    wmMod,
    expMod,
    uiMod,
  ] = await Promise.all([
    import("./stl_viewer.js"),       // сцена, камера, лоадери
    import("./stl_watermark.js"),    // водяний знак + "запекти"
    import("./stl_exporters.js"),    // експорт STL/OBJ/GLTF/PLY
    import("./stl_ui.js"),           // вкладки, кнопки, модалка, хендлери
  ]);

  // 1) Ініціалізуємо 3D-контекст (scene, camera, renderer, groups, helpers)
  const ctx = await viewerMod.initViewer({
    containerId: "viewer",
    statusId: "status",
  });

  // [+] зробимо початковий режим "stl" (зі столом)
  if (typeof ctx.setViewerMode === "function") {
    ctx.setViewerMode("stl");
  }

  // 2) Підключаємо функціональні модулі, передаючи їм спільний контекст
  wmMod.initWatermark(ctx);
  expMod.initExporters(ctx);
  uiMod.initUI(ctx);

  // [+] Експонуємо в window зручні гачки — без зміни інших модулів
  //     - window.viewerCtx: доступ до контексту з консолі / іншим скриптам
  //     - window.viewerSetMode('stl'|'wm'): швидкий перемикач режимів
  window.viewerCtx = ctx;
  window.viewerSetMode = (mode) => {
    if (typeof ctx.setViewerMode === "function") ctx.setViewerMode(mode);
  };

  // [+] Підтримка кастомної події з будь-якого місця:
  //     document.dispatchEvent(new CustomEvent('proofly:mode', { detail: { mode: 'wm' } }));
  document.addEventListener("proofly:mode", (e) => {
    const mode = e?.detail?.mode;
    if (mode) window.viewerSetMode(mode);
  });

  // [+] Легкі «авто-гачки», якщо в розмітці є стандартні ідентифікатори:
  //     — відкриття інструменту водяного знака → режим 'wm'
  //     — повернення на вкладку моделі → режим 'stl'
  const wmOpenBtn =
    document.querySelector('#tool-watermark, [data-tool="watermark"], [data-tab="watermark"], .tool-watermark');
  if (wmOpenBtn) {
    wmOpenBtn.addEventListener("click", () => window.viewerSetMode("wm"));
  }

  const modelTabBtn =
    document.querySelector('#tab-model, [data-tab="model"], .tab-model');
  if (modelTabBtn) {
    modelTabBtn.addEventListener("click", () => window.viewerSetMode("stl"));
  }

  // [+] Якщо UI керує показом панелей класом .active — можна пасивно підлаштуватися:
  //     (нічого не ламає, просто намагається тримати режим у синхроні)
  const wmPanel =
    document.querySelector('#panel-watermark, .panel-watermark, [data-panel="watermark"]');
  if (wmPanel) {
    const obs = new MutationObserver(() => {
      const visible = wmPanel.offsetParent !== null || wmPanel.classList.contains("active");
      window.viewerSetMode(visible ? "wm" : "stl");
    });
    obs.observe(wmPanel, { attributes: true, attributeFilter: ["class", "style"] });
  }

  // Готово: інтерфейс працює на одній сторінці, модулі розділені.
})();
