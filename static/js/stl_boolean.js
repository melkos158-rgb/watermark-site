// static/js/stl_boolean.js
// Демонстраційний модуль Boolean-операцій: додає куб/циліндр/сферу та показує базові поєднання

import * as THREE from "https://unpkg.com/three@0.159.0/build/three.module.js";


export function initBoolean(ctx, { autoBindButtons = true } = {}) {
  if (!ctx || !ctx.scene || !ctx.modelRoot) throw new Error("initBoolean: invalid ctx");

  const $ = (id) => document.getElementById(id);
  const { scene, modelRoot, baseMaterial, wireMaterial, statusEl } = ctx;

  // ── Список створених допоміжних об’єктів (примітивів)
  const tempPrimitives = [];

  function clearTemps() {
    tempPrimitives.forEach((m) => {
      scene.remove(m);
      m.geometry?.dispose?.();
      m.material?.dispose?.();
    });
    tempPrimitives.length = 0;
  }

  function addPrimitive(type = "box") {
    let geom;
    switch (type) {
      case "box":
        geom = new THREE.BoxGeometry(20, 20, 20);
        break;
      case "cyl":
        geom = new THREE.CylinderGeometry(10, 10, 30, 32);
        break;
      case "sph":
        geom = new THREE.SphereGeometry(15, 32, 24);
        break;
      default:
        geom = new THREE.BoxGeometry(20, 20, 20);
    }
    const mesh = new THREE.Mesh(geom, new THREE.MeshStandardMaterial({
      color: 0x44aaff,
      opacity: 0.5,
      transparent: true,
    }));
    mesh.position.y = 20;
    mesh.userData.isTemp = true;
    scene.add(mesh);
    tempPrimitives.push(mesh);
    if (statusEl) statusEl.textContent = `Додано примітив: ${type}`;
  }

  // ── Псевдо Boolean (поки що просто об’єднання)
  function combine(type = "union") {
    if (!modelRoot.children.length || !tempPrimitives.length) {
      alert("Потрібна модель і хоча б один примітив");
      return;
    }
    const base = modelRoot.children.find((o) => o.isMesh);
    const temp = tempPrimitives[0];
    base.updateMatrixWorld(true);
    temp.updateMatrixWorld(true);

    const g1 = base.geometry.clone().applyMatrix4(base.matrixWorld);
    const g2 = temp.geometry.clone().applyMatrix4(temp.matrixWorld);

    const pos = new Float32Array(
      g1.getAttribute("position").array.length + g2.getAttribute("position").array.length
    );
    pos.set(g1.getAttribute("position").array, 0);
    pos.set(g2.getAttribute("position").array, g1.getAttribute("position").array.length);

    const merged = new THREE.BufferGeometry();
    merged.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    merged.computeVertexNormals();

    base.geometry.dispose();
    base.geometry = merged;
    clearTemps();

    if (statusEl) statusEl.textContent = `Boolean ${type} виконано (спрощено, без CSG)`;
  }

  if (autoBindButtons) {
    document.querySelectorAll(".btn.prim")?.forEach((b) => {
      b.addEventListener("click", () => addPrimitive(b.dataset.prim));
    });

    $("#btnUnion")?.addEventListener("click", () => combine("union"));
    $("#btnSubtract")?.addEventListener("click", () => combine("subtract"));
    $("#btnIntersect")?.addEventListener("click", () => combine("intersect"));
  }

  return { addPrimitive, combine, clearTemps };
}
