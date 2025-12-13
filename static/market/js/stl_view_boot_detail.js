// static/market/js/stl_view_boot_detail.js
// Viewer для сторінки детального перегляду моделі (без редактора, без гізмо)

import { initViewer } from "/static/js/stl_viewer.js";

document.addEventListener("DOMContentLoaded", async () => {
  const viewerEl = document.getElementById("viewer");
  const statusEl = document.getElementById("status");

  if (!viewerEl) return;

  let ctx;
  try {
    ctx = await initViewer({
      containerId: "viewer",
      statusId: "status",
    });
  } catch (e) {
    console.error("initViewer error", e);
    if (statusEl) statusEl.textContent = "Помилка 3D-перегляду.";
    return;
  }

  // ======== Завантаження моделі з data-src ========
  const src = viewerEl.dataset.src || "";
  if (src) loadFromUrl(ctx, src);

  // ======== Кнопки тулбара ========
  const buttons = document.querySelectorAll("[data-viewer-action]");
  let spinOn = false;
  let wireOn = false;

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const action = btn.dataset.viewerAction;

      switch (action) {
        case "reset":
          ctx.resetCamera();
          break;

        case "wire":
          wireOn = !wireOn;
          ctx.setWireframe(wireOn);
          break;

        case "spin":
          spinOn = !spinOn;
          ctx.controls.autoRotate = spinOn;
          break;

        case "light":
          setLight(ctx);
          break;

        case "dark":
          setDark(ctx);
          break;
      }
    });
  });
});

// ======== Loader для різних форматів ========
function loadFromUrl(ctx, src) {
  const ext = src.split(".").pop().toLowerCase();
  const { stlLoader, objLoader, plyLoader, gltfLoader } = ctx;

  const done = () => ctx.statusEl && (ctx.statusEl.textContent = "");
  const fail = () => ctx.statusEl && (ctx.statusEl.textContent = "Помилка завантаження");

  ctx.statusEl.textContent = "Завантаження…";

  if (ext === "stl") {
    stlLoader.load(src, (g) => { ctx.addGeometry(g); done(); }, undefined, fail);
  } else if (ext === "obj") {
    objLoader.load(src, (o) => { ctx.addObject(o); done(); }, undefined, fail);
  } else if (ext === "ply") {
    plyLoader.load(src, (g) => {
      g.computeVertexNormals();
      ctx.addGeometry(g);
      done();
    }, undefined, fail);
  } else if (ext === "gltf" || ext === "glb") {
    gltfLoader.load(src, (g) => { ctx.addObject(g.scene); done(); }, undefined, fail);
  } else {
    fail();
  }
}

// ======== Лайт / дарк режими ========
function setLight(ctx) {
  ctx.scene.background = new ctx.THREE.Color(0x111111);
  ctx.dirLight.intensity = 1.2;
}

function setDark(ctx) {
  ctx.scene.background = new ctx.THREE.Color(0x000000);
  ctx.dirLight.intensity = 0.6;
}
