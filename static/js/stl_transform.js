// static/js/stl_transform.js
// Масштабування, обертання, віддзеркалення, центрування моделі

import * as THREE from "three";


export function initTransform(ctx, { autoBindButtons = true } = {}) {
  if (!ctx || !ctx.modelRoot) throw new Error("initTransform: invalid ctx");

  const $ = (id) => document.getElementById(id);
  const { modelRoot, controls, fitCameraToObject, statusEl } = ctx;

  function _resizeGridSafe() {
    try { ctx.resizeGridToModel?.(1.3); } catch (_) {}
  }
  function _doubleSideMaterials(root) {
    try {
      root.traverse((n) => {
        if (n.isMesh && n.material && n.material.side !== THREE.DoubleSide) {
          n.material.side = THREE.DoubleSide;
        }
      });
    } catch (_) {}
  }

  function centerAndFloor() {
    if (!modelRoot.children.length) return alert("Нема моделі");
    // Якщо є утиліта з viewer — використовуємо її (точніше працює)
    if (ctx.centerAndDropToFloor) {
      ctx.centerAndDropToFloor(modelRoot);
    } else {
      const box = new THREE.Box3().setFromObject(modelRoot);
      const center = box.getCenter(new THREE.Vector3());
      const minY = box.min.y;
      modelRoot.position.sub(center);
      modelRoot.position.y -= minY;
    }
    modelRoot.updateMatrixWorld(true);
    fitCameraToObject(modelRoot, 1.6);
    _resizeGridSafe();
    if (statusEl) statusEl.textContent = "Модель відцентровано і опущено на стіл.";
  }

  function autoOrient() {
    if (!modelRoot.children.length) return alert("Нема моделі");
    modelRoot.rotation.set(0, 0, 0);
    modelRoot.updateMatrixWorld(true);
    centerAndFloor();
    if (statusEl) statusEl.textContent = "Автоматична орієнтація застосована.";
  }

  function applyScale() {
    const val = parseFloat($("#scalePct")?.value || "100");
    if (!val || val <= 0) return;
    const scale = val / 100;
    modelRoot.scale.set(scale, scale, scale);
    modelRoot.updateMatrixWorld(true);
    fitCameraToObject(modelRoot, 1.6);
    _resizeGridSafe();
    if (statusEl) statusEl.textContent = `Модель масштабовано ×${scale.toFixed(2)}`;
  }

  function rotate(axis, deg) {
    if (!modelRoot.children.length) return alert("Нема моделі");
    const rad = (deg * Math.PI) / 180;
    modelRoot.rotation[axis] += rad;
    modelRoot.updateMatrixWorld(true);
    _resizeGridSafe();
    if (statusEl) statusEl.textContent = `Обертання: ${axis.toUpperCase()} ${deg > 0 ? "+" : ""}${deg}°`;
  }

  function mirror(axis) {
    if (!modelRoot.children.length) return alert("Нема моделі");
    const scale = modelRoot.scale.clone();
    scale[axis] *= -1;
    modelRoot.scale.copy(scale);
    // Щоб не зникали грані при негативному масштабі — увімкнемо DoubleSide
    _doubleSideMaterials(modelRoot);
    modelRoot.updateMatrixWorld(true);
    _resizeGridSafe();
    if (statusEl) statusEl.textContent = `Віддзеркалено по осі ${axis.toUpperCase()}`;
  }

  // Автопідключення кнопок із панелі “Трансформ”
  if (autoBindButtons) {
    $("#btnCenter")?.addEventListener("click", centerAndFloor);
    $("#btnAutoOrient")?.addEventListener("click", autoOrient);
    $("#btnScaleApply")?.addEventListener("click", applyScale);

    document.querySelectorAll(".rot")?.forEach((b) => {
      const ds = b.dataset.rot || "";
      const [axis, val] = ds.split("-");
      const deg = parseFloat(val);
      if (!axis || !Number.isFinite(deg)) return;
      b.addEventListener("click", () => rotate(axis, deg));
    });

    document.querySelectorAll(".mirror")?.forEach((b) => {
      const axis = b.dataset.mirror;
      if (!axis) return;
      b.addEventListener("click", () => mirror(axis));
    });
  }

  return {
    centerAndFloor,
    autoOrient,
    applyScale,
    rotate,
    mirror,
  };
}
