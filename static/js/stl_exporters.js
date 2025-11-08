// static/js/stl_exporters.js
// Експортує модель у різні формати STL / GLB / GLTF / OBJ / PLY

import { STLExporter } from "stl/exporter";
import { GLTFExporter } from "gltf/exporter";
import { OBJExporter } from "obj/exporter";
import { PLYExporter } from "ply/exporter";

export function initExporters(ctx, { autoBindButtons = true } = {}) {
  if (!ctx || !ctx.modelRoot) throw new Error("initExporters: invalid viewer ctx");

  const $ = (id) => document.getElementById(id);
  const { modelRoot } = ctx;

  // ---------- Допоміжна функція
  function download(name, data, bin = false) {
    const blob = new Blob([data], {
      type: bin ? "application/octet-stream" : "text/plain",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  // ---------- Отримати єдину групу для експорту
  function getExportGroup() {
    if (!modelRoot.children.length) {
      alert("Нема моделі для експорту");
      return null;
    }
    const group = new ctx.THREE.Group();
    modelRoot.updateMatrixWorld(true);
    modelRoot.traverse((n) => {
      if (n.isMesh && n.geometry) {
        const g = n.geometry.clone();
        g.applyMatrix4(n.matrixWorld);
        group.add(new ctx.THREE.Mesh(g));
      }
    });
    if (!group.children.length) {
      alert("Нема геометрії для експорту");
      return null;
    }
    return group;
  }

  // ---------- Експортери
  const stlEx = new STLExporter();
  const gltfEx = new GLTFExporter();
  const objEx = new OBJExporter();
  const plyEx = new PLYExporter();

  function exportSTL(isBinary) {
    const mesh = modelRoot.children.find((o) => o.isMesh);
    if (!mesh) return alert("Немає моделі для експорту");
    if (isBinary) {
      const buf = stlEx.parse(mesh, { binary: true });
      download("model_binary.stl", buf, true);
    } else {
      const ascii = stlEx.parse(mesh, { binary: false });
      download("model_ascii.stl", ascii, false);
    }
  }

  function exportGLB() {
    const r = getExportGroup();
    if (!r) return;
    gltfEx.parse(
      r,
      (bin) => download("model.glb", bin, true),
      { binary: true, onlyVisible: true, trs: false }
    );
  }

  function exportGLTF() {
    const r = getExportGroup();
    if (!r) return;
    gltfEx.parse(
      r,
      (g) => download("model.gltf", JSON.stringify(g), false),
      { binary: false, embedImages: true }
    );
  }

  function exportOBJ() {
    const r = getExportGroup();
    if (!r) return;
    download("model.obj", objEx.parse(r), false);
  }

  function exportPLY() {
    const r = getExportGroup();
    if (!r) return;
    download("model.ply", plyEx.parse(r), false);
  }

  // ---------- Автоматичне підключення до кнопок
  if (autoBindButtons) {
    $("#btnExportAscii")?.addEventListener("click", () => exportSTL(false));
    $("#btnExportBinary")?.addEventListener("click", () => exportSTL(true));
    $("#btnExpGLB")?.addEventListener("click", exportGLB);
    $("#btnExpGLTF")?.addEventListener("click", exportGLTF);
    $("#btnExpOBJ")?.addEventListener("click", exportOBJ);
    $("#btnExpPLY")?.addEventListener("click", exportPLY);
  }

  // ---------- API модуля
  return {
    exportSTL,
    exportGLB,
    exportGLTF,
    exportOBJ,
    exportPLY,
  };
}
