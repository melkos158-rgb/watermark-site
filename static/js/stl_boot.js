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
    transMod,           // ДОДАНО: трансформації (center/floor/scale/rotate/mirror + прив'язки кнопок)
  ] = await Promise.all([
    import("./stl_viewer.js"),       // сцена, камера, лоадери
    import("./stl_watermark.js"),    // водяний знак + "запекти"
    import("./stl_exporters.js"),    // експорт STL/OBJ/GLTF/PLY
    import("./stl_ui.js"),           // вкладки, кнопки, модалка, хендлери
    import("./stl_transform.js"),    // ДОДАНО: обгортка трансформів/центр/масштаб/обертання/дзеркало
  ]);

  // 1) Ініціалізуємо 3D-контекст (scene, camera, renderer, groups, helpers)
  const ctx = await viewerMod.initViewer({
    containerId: "viewer",
    statusId: "status",
  });

  // ---- ВАЖЛИВО: дати доступ UI/автоприв'язкам одразу після створення ctx
  window.viewerCtx = ctx;
  window.__STL_CTX = ctx; // сумісність з автоприв’язками у stl_ui.js

  // [+] зробимо початковий режим "stl" (зі столом)
  if (typeof ctx.setViewerMode === "function") {
    ctx.setViewerMode("stl");
  }

  // 2) Підключаємо функціональні модулі, передаючи їм спільний контекст
  wmMod.initWatermark(ctx);

  // ЯВНО: авто-підв’язка кнопок експорту (приховані ID типу #btnExpGLB тощо)
  const exporters = expMod.initExporters(ctx, { autoBindButtons: true });

  // Експонуємо API експорту глобально — щоб модалка могла викликати напряму
  window.__EXPORTERS = exporters;

  // Примітка: initUI в твоєму файлі без аргументів — зайвий аргумент не завадить
  uiMod.initUI?.(ctx);

  // 2.1) ДОДАНО: ініт трансформ-панелі (центрування/масштаб/обертання/дзеркало)
  // autoBindButtons=true підчепить кнопки з id/класами з лівої панелі
  if (typeof transMod.initTransform === "function") {
    transMod.initTransform(ctx, { autoBindButtons: true });
  }

  // [+] Експонуємо зручні гачки — без зміни інших модулів
  //     - window.viewerSetMode('stl'|'wm'): швидкий перемикач режимів
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

  // 3) ДОДАНО: прив’язка вертикального тулбара у #viewer (Move/Rotate/Scale/Fit + Snap)
  bindGizmoToolbar(ctx);

  // 4) ДОДАНО: пряма прив’язка кнопок модалки експорту до API експортерів (fallback)
  bindExportModalDirect();

  // Готово: інтерфейс працює на одній сторінці, модулі розділені.

  // ───────────────────────────────────────────────────────────────────────────
  // ВНУТРІШНІ ХЕЛПЕРИ (без зміни публічного API)
  function bindGizmoToolbar(ctx) {
    const $ = (id) => document.getElementById(id);
    const btnMove   = $("tool-move");
    const btnRotate = $("tool-rotate");
    const btnScale  = $("tool-scale");
    const btnFit    = $("tool-fit");
    const snapInput = $("tb-snap-input");

    function setActive(btn){
      [btnMove, btnRotate, btnScale].forEach(b => b?.classList.remove("active"));
      btn?.classList.add("active");
    }

    btnMove  ?.addEventListener("click", () => { ctx.transform.setMode?.("translate"); setActive(btnMove);   });
    btnRotate?.addEventListener("click", () => { ctx.transform.setMode?.("rotate");    setActive(btnRotate); });
    btnScale ?.addEventListener("click", () => { ctx.transform.setMode?.("scale");     setActive(btnScale);  });
    btnFit   ?.addEventListener("click", () => { ctx.transform.focus?.(); });

    snapInput?.addEventListener("change", (e) => {
      const v = parseFloat(e.target.value);
      if (Number.isFinite(v) && v > 0) ctx.transform.setSnap?.(v);
      else ctx.transform.setSnap?.(null);
    });

    // Гарячі клавіші як у Blender
    window.addEventListener("keydown", (ev) => {
      if (ev.repeat) return;
      const k = ev.key.toLowerCase();
      if (k === "g") { ctx.transform.setMode?.("translate"); setActive(btnMove); }
      if (k === "r") { ctx.transform.setMode?.("rotate");    setActive(btnRotate); }
      if (k === "s") { ctx.transform.setMode?.("scale");     setActive(btnScale);  }
      if (k === "f") { ctx.transform.focus?.(); }
    });
  }

  // Пряме керування експортом із модалки (напряму, без прихованих кнопок)
  function bindExportModalDirect() {
    const modal = document.getElementById("exportModal");
    if (!modal) return;

    const call = (kind) => {
      const ex = window.__EXPORTERS;
      if (!ex) return;
      try {
        if (kind === "ascii")  return ex.exportSTL(false);
        if (kind === "binary") return ex.exportSTL(true);
        if (kind === "glb")    return ex.exportGLB();
        if (kind === "gltf")   return ex.exportGLTF();
        if (kind === "obj")    return ex.exportOBJ();
        if (kind === "ply")    return ex.exportPLY();
      } catch (err) {
        console.error("Export failed:", err);
      }
    };

    modal.addEventListener("click", (e) => {
      const b = e.target.closest("[data-export]");
      if (!b) return;
      e.preventDefault();
      const kind = b.getAttribute("data-export");
      // даємо модалці сховатися, потім викликаємо експорт
      setTimeout(() => call(kind), 40);
    }, { passive: false });
  }
})();
