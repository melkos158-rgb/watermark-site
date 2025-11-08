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

  // 2) Підключаємо функціональні модулі, передаючи їм спільний контекст
  wmMod.initWatermark(ctx);
  expMod.initExporters(ctx);
  uiMod.initUI(ctx);

  // Готово: інтерфейс працює на одній сторінці, модулі розділені.
})();
