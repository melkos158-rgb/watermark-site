// static/market/js/viewer.js
// Ініціалізація STL/3D viewer на сторінці detail.html

import { initViewer } from "/static/js/stl_viewer.js";

/**
 * Примусовий ресайз в'ювера під контейнер.
 * НЕ міняє initViewer, просто підганяє canvas/renderer під #viewer.
 */
function forceViewerFit(ctx, containerEl) {
  if (!ctx || !containerEl) return;

  // страхуємо стилі контейнера, щоб не було горизонтального “виносу вправо”
  containerEl.style.maxWidth = "100%";
  containerEl.style.overflow = "hidden";

  // знайдемо canvas
  const canvas =
    containerEl.querySelector("canvas") ||
    (ctx.renderer && ctx.renderer.domElement) ||
    null;

  if (canvas) {
    canvas.style.display = "block";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    canvas.style.maxWidth = "100%";
  }

  // Розмір беремо по контейнеру (а не по window)
  const rect = containerEl.getBoundingClientRect();
  const w = Math.max(1, Math.floor(rect.width));
  const h = Math.max(1, Math.floor(rect.height || containerEl.clientHeight || 1));

  // 1) Якщо в ctx є готовий resize/onResize/handleResize — використовуємо
  const resizeFn =
    ctx.resize ||
    ctx.onResize ||
    ctx.handleResize ||
    ctx.resizeToContainer ||
    null;

  try {
    if (typeof resizeFn === "function") {
      // деякі реалізації хочуть (w,h), деякі не хочуть нічого
      if (resizeFn.length >= 2) resizeFn.call(ctx, w, h);
      else resizeFn.call(ctx);
      return;
    }
  } catch (e) {
    // ідемо далі на ручний режим
  }

  // 2) Ручний режим: якщо є renderer + camera — підганяємо самі
  try {
    if (ctx.renderer && typeof ctx.renderer.setSize === "function") {
      ctx.renderer.setSize(w, h, false);
    }

    if (ctx.camera) {
      // perspective camera
      if ("aspect" in ctx.camera) {
        ctx.camera.aspect = w / h;
      }
      if (typeof ctx.camera.updateProjectionMatrix === "function") {
        ctx.camera.updateProjectionMatrix();
      }
    }
  } catch (e) {
    // останній шанс — просто триггернути window resize (якщо stl_viewer.js на нього підписаний)
    try {
      window.dispatchEvent(new Event("resize"));
    } catch (_) {}
  }
}

/**
 * Ставимо спостерігач за контейнером, щоб при зміні ширини/висоти
 * (шапка, сайдбар, DevTools, адаптив) — в'ювер не їхав вправо.
 */
function bindViewerAutoResize(ctx, containerEl) {
  if (!ctx || !containerEl) return;

  // перший ресайз одразу
  forceViewerFit(ctx, containerEl);

  // другий — через тік, щоб дочекатись layout після рендеру
  setTimeout(() => forceViewerFit(ctx, containerEl), 0);
  setTimeout(() => forceViewerFit(ctx, containerEl), 150);

  // ResizeObserver — найкращий варіант
  if ("ResizeObserver" in window) {
    const ro = new ResizeObserver(() => {
      forceViewerFit(ctx, containerEl);
    });
    ro.observe(containerEl);

    // щоб не губилось — сховаємо в ctx (не ламає API)
    try {
      ctx.__ro = ro;
    } catch (_) {}
  } else {
    // fallback
    window.addEventListener("resize", () => forceViewerFit(ctx, containerEl));
  }

  // ще один кейс: коли відкриті DevTools, ширина може мінятись без resize
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) forceViewerFit(ctx, containerEl);
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  const el = document.getElementById("viewer");
  if (!el) return;

  try {
    // Якщо маєш елемент статусу — додай id="status" у шаблоні
    const ctx = await initViewer({ containerId: "viewer", statusId: "status" });

    // Збережемо глобально (зручно для інших скриптів: favorites/reviews, тулбар і т.д.)
    window.MARKET_VIEWER = ctx;

    // ✅ HOTFIX: підганяємо вʼювер під контейнер і тримаємо ресайз
    bindViewerAutoResize(ctx, el);

    // Якщо у контейнера задано data-src — автоматично завантажуємо модель
    const src = el.dataset.src;
    if (src && ctx.loadModel) {
      try {
        await ctx.loadModel(src);
        // ще раз піджати після завантаження моделі (часто модель міняє bounds/camera)
        forceViewerFit(ctx, el);
        console.debug("Model auto-loaded:", src);
      } catch (err) {
        console.error("Auto-load model failed:", err);
      }
    }

    // -----------------------------
    // Тулбар над в’ювером
    // data-viewer-action="reset|spin|wire|grid|dark|light"
    // -----------------------------
    const toolbarButtons = document.querySelectorAll("[data-viewer-action]");
    if (toolbarButtons.length) {
      toolbarButtons.forEach((btn) => {
        const action = btn.dataset.viewerAction;
        if (!action) return;

        btn.addEventListener("click", () => {
          const v = window.MARKET_VIEWER || ctx;
          if (!v) return;

          try {
            switch (action) {
              case "reset":
                // Скидання камери / фрейму
                if (typeof v.resetCamera === "function") {
                  v.resetCamera();
                } else if (typeof v.frameObject === "function") {
                  v.frameObject();
                }
                // після reset інколи треба підтягнути розмір
                forceViewerFit(v, el);
                break;

              case "spin":
                // Автообертання моделі
                if (typeof v.toggleAutoRotate === "function") {
                  v.toggleAutoRotate();
                } else if (typeof v.setAutoRotate === "function") {
                  // простий toggle, якщо є сеттер
                  v._autoSpinOn = !v._autoSpinOn;
                  v.setAutoRotate(!!v._autoSpinOn);
                }
                break;

              case "wire":
                // Wireframe вкл/викл
                if (typeof v.toggleWireframe === "function") {
                  v.toggleWireframe();
                } else if (typeof v.setWireframe === "function") {
                  v._wireOn = !v._wireOn;
                  v.setWireframe(!!v._wireOn);
                }
                break;

              case "grid":
                // Сітка під моделлю
                if (typeof v.toggleGrid === "function") {
                  v.toggleGrid();
                } else if (typeof v.setGridVisible === "function") {
                  v._gridOn = !v._gridOn;
                  v.setGridVisible(!!v._gridOn);
                }
                break;

              case "dark":
                // Темна сцена / м’яке світло
                if (typeof v.setLightPreset === "function") {
                  v.setLightPreset("dark");
                } else if (typeof v.setEnvPreset === "function") {
                  v.setEnvPreset("dark");
                }
                break;

              case "light":
                // Яскрава сцена
                if (typeof v.setLightPreset === "function") {
                  v.setLightPreset("bright");
                } else if (typeof v.setEnvPreset === "function") {
                  v.setEnvPreset("bright");
                }
                break;

              default:
                console.debug("Unknown viewer action:", action);
            }
          } catch (err) {
            console.error("viewer toolbar action error:", action, err);
          }
        });
      });
    }
  } catch (e) {
    console.error("Viewer init error:", e);
  }
});
