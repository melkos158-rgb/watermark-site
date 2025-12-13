// static/js/stl_watermark.js
// Відповідає за попередній перегляд 3D-водяного знаку та "запікання" в геометрію.

import * as THREE from "https://unpkg.com/three@0.159.0/build/three.module.js";
import { STLLoader } from "https://unpkg.com/three@0.159.0/examples/jsm/loaders/STLLoader.js";
import { FontLoader } from "https://unpkg.com/three@0.159.0/examples/jsm/loaders/FontLoader.js";
import { TextGeometry } from "https://unpkg.com/three@0.159.0/examples/jsm/geometries/TextGeometry.js";


const FONT_URL = "https://cdn.jsdelivr.net/npm/three@0.159/examples/fonts/helvetiker_regular.typeface.json";

export function initWatermark(ctx, { autoBindButtons = true } = {}) {
  if (!ctx || !ctx.scene || !ctx.modelRoot || !ctx.watermarkGroup) {
    throw new Error("initWatermark: invalid viewer ctx");
  }

  const $ = (id) => document.getElementById(id);
  const { modelRoot, watermarkGroup, statusEl } = ctx;

  // ── Ліниве завантаження шрифту
  const fontLoader = new FontLoader();
  let font = null;
  let fontPromise = null;

  function ensureFont() {
    if (font) return Promise.resolve(font);
    if (fontPromise) return fontPromise;
    fontPromise = new Promise((resolve, reject) => {
      fontLoader.load(
        FONT_URL,
        (f) => {
          font = f;
          resolve(font);
        },
        undefined,
        (err) => reject(err)
      );
    });
    return fontPromise;
  }

  function clearGroup(grp) {
    while (grp.children.length) {
      const m = grp.children.pop();
      m.geometry?.dispose?.();
      m.material?.dispose?.();
    }
  }

  // ── Побудова попереднього перегляду водяного знаку
  async function previewWatermark({
    text = ($("wmText")?.value ?? "Brand"),
    size = Number($("wmSize")?.value ?? 12),
    depth = Number($("wmDepth")?.value ?? 3),
    angleDeg = Number($("wmAngle")?.value ?? 0),
    offsetPercent = Number($("wmOffset")?.value ?? 4),
  } = {}) {
    if (!modelRoot.children.length) {
      alert("Спершу завантаж модель.");
      return false;
    }
    try {
      const f = await ensureFont();
      clearGroup(watermarkGroup);

      const tg = new TextGeometry((text || "Brand").trim() || "Brand", {
        font: f,
        size: Math.max(1, size),
        height: Math.max(0.5, depth),
        curveSegments: 8,
        bevelEnabled: false,
      });
      tg.computeBoundingBox();

      const mat = new THREE.MeshStandardMaterial({
        color: 0xff4488,
        transparent: true,
        opacity: 0.65,
      });
      const mesh = new THREE.Mesh(tg, mat);

      // Розміщення по краю bbox моделі
      const mbox = new THREE.Box3().setFromObject(modelRoot);
      const msize = mbox.getSize(new THREE.Vector3());
      const margin = msize.length() * (Math.max(0, offsetPercent) / 100);

      const angle = (angleDeg || 0) * Math.PI / 180;
      mesh.rotation.set(0, 0, angle);

      // Верхня площина, відступ від мін/мін по XZ
      mesh.position.set(mbox.min.x + margin, mbox.max.y + 0.1, mbox.min.z + margin);

      watermarkGroup.add(mesh);
      if (statusEl) statusEl.textContent = "Попередній перегляд знаку активний (рожевий обʼєкт).";
      return true;
    } catch (e) {
      console.warn("Шрифт не завантажився:", e);
      alert("Шрифт ще вантажиться або не завантажився. Спробуй ще раз.");
      return false;
    }
  }

  // ── Запікання: просте «злиття» вершин (без CSG)
  function bakeWatermark() {
    if (!watermarkGroup.children.length) {
      alert("Немає превʼю знаку. Натисни «Попередній перегляд».");
      return false;
    }
    // Знаходимо перший меш моделі
    const base = modelRoot.children.find((o) => o.isMesh);
    if (!base || !base.geometry) {
      alert("Немає геометрії моделі.");
      return false;
    }
    const wm = watermarkGroup.children[0];
    wm.updateMatrixWorld(true);

    const baseGeo = base.geometry.clone();
    const wmGeo = wm.geometry.clone().applyMatrix4(wm.matrixWorld);

    const aPos = baseGeo.getAttribute("position");
    const bPos = wmGeo.getAttribute("position");

    const pos = new Float32Array(aPos.count * 3 + bPos.count * 3);
    pos.set(aPos.array, 0);
    pos.set(bPos.array, aPos.count * 3);

    const merged = new THREE.BufferGeometry();
    merged.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    merged.computeVertexNormals();

    base.geometry.dispose();
    base.geometry = merged;

    clearGroup(watermarkGroup);
    if (statusEl) statusEl.textContent = "Знак запечено у геометрію.";
    return true;
  }

  // ── Необовʼязкове автопривʼязування кнопок
  if (autoBindButtons) {
    const btnPrev = $("btnPreview");
    const btnBake = $("btnBake");

    btnPrev?.addEventListener("click", () => previewWatermark());
    btnBake?.addEventListener("click", () => bakeWatermark());
  }

  // Повертаємо API модуля
  return {
    ensureFont,
    previewWatermark,
    bakeWatermark,
  };
}
