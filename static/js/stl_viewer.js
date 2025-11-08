// static/js/stl_viewer.js
// Створює сцену Three.js, рендер, камеру, групи та лоадери.
// Експортує initViewer(), що повертає контекст ctx з усіма потрібними методами.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader }     from "stl/loader";
import { GLTFLoader }    from "gltf/loader";
import { OBJLoader }     from "obj/loader";
import { PLYLoader }     from "ply/loader";

export async function initViewer({ containerId = "viewer", statusId = "status" } = {}) {
  const $ = (id) => document.getElementById(id);
  const container = $(containerId);
  if (!container) throw new Error(`Container #${containerId} not found`);
  const statusEl = $(statusId);

  // ── СЦЕНА
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x111111);

  // ── КАМЕРА
  const camera = new THREE.PerspectiveCamera(50, 1, 0.01, 1000);
  camera.position.set(1.2, 0.9, 1.8);

  // ── РЕНДЕР
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  container.appendChild(renderer.domElement);

  // ── КОНТРОЛИ
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  // ── СВІТЛО/СІТКА
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const dir = new THREE.DirectionalLight(0xffffff, 0.9);
  dir.position.set(2, 2, 2);
  scene.add(dir);

  const grid = new THREE.GridHelper(10, 10, 0x3a4153, 0x262b39);
  grid.position.y = 0; // FIX: сітка рівно на 0
  scene.add(grid);

  // ── ГРУПИ ДЛЯ МОДЕЛІ ТА ВОДЯНОГО ЗНАКУ
  const modelRoot = new THREE.Group();
  const watermarkGroup = new THREE.Group();
  scene.add(modelRoot);
  scene.add(watermarkGroup);

  // ── МАТЕРІАЛИ
  const baseMaterial = new THREE.MeshStandardMaterial({
    color: 0x9aa7c7,
    roughness: 0.85,
    metalness: 0.05,
  });
  const wireMaterial = new THREE.MeshBasicMaterial({ color: 0xffffff, wireframe: true });
  let wireframeOn = false;

  // ── РЕСАЙЗ
  function resize() {
    const w = container.clientWidth || container.parentElement?.clientWidth || 800;
    const h = container.clientHeight || Math.max(420, Math.round(w * 0.62));
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(container);
  window.addEventListener("resize", resize);
  resize();

  // ── КАМЕРА → ПІД МОДЕЛЬ
  function fitCameraToObject(object, zoom = 1.6) {
    const box = new THREE.Box3().setFromObject(object);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z) || 1;
    const fov = camera.fov * (Math.PI / 180);
    let camZ = Math.abs(maxDim / (2 * Math.tan(fov / 2))) * zoom;
    camZ = Math.max(camZ, 0.1);
    camera.position.set(center.x + camZ * 0.7, center.y + camZ * 0.5, center.z + camZ);
    camera.near = camZ / 100;
    camera.far = camZ * 100;
    camera.updateProjectionMatrix();
    controls.target.copy(center);
    controls.update();
  }

  function resetCamera() {
    if (modelRoot.children.length) fitCameraToObject(modelRoot, 1.6);
    else {
      camera.position.set(1.2, 0.9, 1.8);
      controls.target.set(0, 0, 0);
      controls.update();
    }
  }

  // ── ЛОАДЕРИ
  const stlLoader = new STLLoader();
  const gltfLoader = new GLTFLoader();
  const objLoader = new OBJLoader();
  const plyLoader = new PLYLoader();

  // ── УТИЛІТИ
  function clearGroup(grp) {
    while (grp.children.length) {
      const m = grp.children.pop();
      m.geometry?.dispose?.();
      m.material?.dispose?.();
    }
  }

  function clearAll() {
    clearGroup(modelRoot);
    clearGroup(watermarkGroup);
    if (statusEl) statusEl.textContent = "";
  }

  function addGeometry(geometry) {
    geometry.computeVertexNormals?.();
    const mesh = new THREE.Mesh(geometry, wireframeOn ? wireMaterial : baseMaterial);
    modelRoot.add(mesh);
    fitCameraToObject(modelRoot, 1.6);
    return mesh;
  }

  function addObject(obj) {
    obj.traverse((n) => {
      if (n.isMesh) {
        n.material = wireframeOn ? wireMaterial : baseMaterial.clone();
        n.material.side = THREE.DoubleSide;
        n.geometry?.computeVertexNormals?.();
      }
    });
    modelRoot.add(obj);

    // Вирівняти по центру та "на стіл"
    const box = new THREE.Box3().setFromObject(modelRoot);
    const center = box.getCenter(new THREE.Vector3());
    const minY = box.min.y;
    modelRoot.position.sub(center);
    modelRoot.position.y -= minY;

    fitCameraToObject(modelRoot, 1.6);
  }

  async function loadAnyFromFile(file) {
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    const url = URL.createObjectURL(file);
    const done = () => URL.revokeObjectURL(url);

    const onError = (err) => {
      console.error("Load error:", err);
      alert("Не вдалося прочитати файл. Підтримка: STL, OBJ, PLY, glTF/GLB.");
      done();
    };

    try {
      if (ext === "stl") {
        stlLoader.load(
          url,
          (geom) => {
            clearAll();
            addGeometry(geom);
            done();
          },
          undefined,
          onError
        );
      } else if (ext === "obj") {
        objLoader.load(
          url,
          (obj) => {
            clearAll();
            addObject(obj);
            done();
          },
          undefined,
          onError
        );
      } else if (ext === "ply") {
        plyLoader.load(
          url,
          (geom) => {
            geom.computeVertexNormals();
            clearAll();
            addGeometry(geom);
            done();
          },
          undefined,
          onError
        );
      } else if (ext === "gltf" || ext === "glb") {
        gltfLoader.load(
          url,
          (gltf) => {
            clearAll();
            addObject(gltf.scene);
            done();
          },
          undefined,
          onError
        );
      } else {
        alert("Формат не підтримується (доступні: STL, OBJ, PLY, glTF/GLB).");
        done();
      }
    } catch (e) {
      onError(e);
    }
  }

  function setWireframe(on) {
    wireframeOn = !!on;
    modelRoot.traverse((o) => {
      if (o.isMesh) o.material = wireframeOn ? wireMaterial : baseMaterial;
    });
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // ▼▼▼ ДОДАНО: режими перегляду "stl" (зі столом) і "wm" (без стола + 360°) ▼▼▼

  // внутрішній стан режиму та годинник для плавної анімації
  let viewerMode = "stl";              // 'stl' | 'wm'
  const clock = new THREE.Clock();
  let spinFlag = false;                // додаткове обертання групи водяного знака
  controls.autoRotate = false;         // початково вимкнено
  controls.autoRotateSpeed = 1.2;

  /** Центрує об’єкт у (0,0,0) по XZ без посадки на підлогу */
  function centerObject(object) {
    object.updateWorldMatrix(true, true);                     // FIX: актуальні матриці
    const box = new THREE.Box3().setFromObject(object);
    const center = box.getCenter(new THREE.Vector3());
    // Центруємо лише X та Z, Y не чіпаємо
    object.position.x -= center.x;
    object.position.z -= center.z;
  }

  /** Опускає об’єкт, щоб мінімальний Y = 0 (поставити "на стіл") */
  function dropToFloor(object) {
    object.updateWorldMatrix(true, true);                     // FIX: актуальні матриці
    const box = new THREE.Box3().setFromObject(object);
    const dy = box.min.y - 0;
    if (Math.abs(dy) > 0.0005) {
      object.position.y -= dy;                                // підняти/опустити щоб minY == 0
    }
  }

  /** Зручна утиліта: і центр, і посадка на підлогу */
  function centerAndDropToFloor(object) {
    centerObject(object);
    dropToFloor(object);
  }

  /** Публічний перемикач режимів перегляду */
  function setViewerMode(mode /* 'stl' | 'wm' */) {
    viewerMode = mode === "wm" ? "wm" : "stl";

    if (viewerMode === "stl") {
      grid.visible = true;             // показуємо "стіл"
      controls.autoRotate = false;     // ручне керування
      spinFlag = false;                // не крутимо watermarkGroup
    } else {
      grid.visible = false;            // прибираємо "стіл"
      controls.autoRotate = true;      // камера повільно крутиться
      controls.autoRotateSpeed = 1.2;
      spinFlag = true;                 // і ще трохи крутимо watermarkGroup
      // переконаймося, що watermark по центру (без посадки на підлогу)
      centerObject(watermarkGroup);
      fitCameraToObject(watermarkGroup, 1.4);
    }
  }

  // ▲▲▲ КІНЕЦЬ БЛОКУ ДОДАВАННЯ РЕЖИМІВ ▲▲▲
  // ─────────────────────────────────────────────────────────────────────────────

  // ── РЕНДЕР-ЛУП
  (function loop() {
    requestAnimationFrame(loop);
    // додано плавний спін для 'wm'
    const delta = clock.getDelta();
    if (spinFlag) watermarkGroup.rotation.y += delta * 0.6;

    controls.update();
    renderer.render(scene, camera);
  })();

  // ── ПОВЕРТАЄМО КОНТЕКСТ ДЛЯ ІНШИХ МОДУЛІВ
  const ctx = {
    // DOM
    container,
    statusEl,

    // Three.js
    scene,
    camera,
    renderer,
    controls,
    modelRoot,
    watermarkGroup,
    grid,
    dirLight: dir,

    // Materials / state
    baseMaterial,
    wireMaterial,
    get wireframeOn() { return wireframeOn; },

    // Loaders
    stlLoader,
    gltfLoader,
    objLoader,
    plyLoader,

    // Helpers
    resize,
    fitCameraToObject,
    resetCamera,
    clearAll,
    addGeometry,
    addObject,
    loadAnyFromFile,
    setWireframe,

    // ▼ нові утиліти / API для інших модулів
    centerObject,
    dropToFloor,
    centerAndDropToFloor,
    setViewerMode,        // головне: перемикач "stl" ↔ "wm"
    get viewerMode() { return viewerMode; },
  };

  return ctx;
}
