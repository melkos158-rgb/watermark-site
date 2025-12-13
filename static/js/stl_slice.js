// static/js/stl_slice.js
// Перегляд зрізу площиною + базовий “розріз” (візуальний)

import * as THREE from "three";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

export function initSlice(ctx, { autoBind = true } = {}) {
  if (!ctx || !ctx.scene || !ctx.modelRoot) throw new Error("initSlice: invalid ctx");

  const $ = (id) => document.getElementById(id);
  const { scene, modelRoot, statusEl } = ctx;

  // ───────────
  // Площина зрізу
  const clipPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);
  const planeHelper = new THREE.PlaneHelper(clipPlane, 200, 0xff5555);
  planeHelper.visible = false;
  scene.add(planeHelper);

  let slicing = false;
  let currentMesh = null;

  function enablePreview() {
    if (!modelRoot.children.length) return alert("Нема моделі для превʼю");
    slicing = !slicing;
    planeHelper.visible = slicing;
    if (statusEl)
      statusEl.textContent = slicing
        ? "Превʼю площини зрізу активне."
        : "Превʼю площини вимкнено.";
  }

  function applySlice() {
    if (!modelRoot.children.length) return alert("Нема моделі для розрізу");
    const mesh = modelRoot.children.find((o) => o.isMesh);
    if (!mesh) return alert("Не знайдено геометрії");
    currentMesh = mesh;

    // Ми просто дублюємо модель і показуємо “верхню” і “нижню” частину для вигляду
    const geom1 = mesh.geometry.clone();
    const geom2 = mesh.geometry.clone();

    const m1 = new THREE.Mesh(
      geom1,
      new THREE.MeshStandardMaterial({ color: 0x44aa88, opacity: 0.9, transparent: true })
    );
    const m2 = new THREE.Mesh(
      geom2,
      new THREE.MeshStandardMaterial({ color: 0xaa8844, opacity: 0.9, transparent: true })
    );

    m1.position.y += 0.1;
    m2.position.y -= 0.1;

    modelRoot.clear();
    modelRoot.add(m1);
    modelRoot.add(m2);

    if (statusEl) statusEl.textContent = "Розріз виконано (візуальний).";
  }

  function updatePlane() {
    const y = parseFloat($("#sliceY")?.value || "0");
    const ax = parseFloat($("#sliceAx")?.value || "0");
    const az = parseFloat($("#sliceAz")?.value || "0");

    const nx = Math.sin(THREE.MathUtils.degToRad(az));
    const ny = -Math.cos(THREE.MathUtils.degToRad(ax)) * Math.cos(THREE.MathUtils.degToRad(az));
    const nz = Math.sin(THREE.MathUtils.degToRad(ax));

    clipPlane.set(new THREE.Vector3(nx, ny, nz), -y);
    planeHelper.updateMatrixWorld(true);
  }

  // ───────────
  // Привʼязка UI
  if (autoBind) {
    $("#btnSlicePreview")?.addEventListener("click", enablePreview);
    $("#btnSliceApply")?.addEventListener("click", applySlice);
    $("#sliceY")?.addEventListener("input", updatePlane);
    $("#sliceAx")?.addEventListener("input", updatePlane);
    $("#sliceAz")?.addEventListener("input", updatePlane);
  }

  updatePlane();

  return {
    enablePreview,
    applySlice,
    updatePlane,
    get active() {
      return slicing;
    },
  };
}
