// static/js/stl_viewer.js
// Створює сцену Three.js, рендер, камеру, групи та лоадери.
// Експортує initViewer(), що повертає контекст ctx з усіма потрібними методами.

// ✅ Imports via global import map from base.html (three@0.160.0)
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TransformControls } from "three/addons/controls/TransformControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OBJLoader } from "three/addons/loaders/OBJLoader.js";
import { PLYLoader } from "three/addons/loaders/PLYLoader.js";

/* =========================================================
   TiledGrid — "блендерний" стіл без краю:
   розмножує стандартний GridHelper плитками навколо (0,0,0)
   у світових координатах (нічого не “пливе”).
   ========================================================= */
class TiledGrid extends THREE.Group {
  constructor({
    tileSize     = 10,     // перший аргумент GridHelper (реальний розмір плитки)
    divisions    = 10,     // другий аргумент GridHelper (к-сть клітинок у плитці)
    tilesRadius  = 8,      // радіус у плитках (покриє (2R+1)^2 плиток)
    colorCenter  = 0x3a4153,
    colorGrid    = 0x262b39,
    y            = 0
  } = {}) {
    super();
    for (let ix = -tilesRadius; ix <= tilesRadius; ix++) {
      for (let iz = -tilesRadius; iz <= tilesRadius; iz++) {
        const gh = new THREE.GridHelper(tileSize, divisions, colorCenter, colorGrid);
        gh.position.set(ix * tileSize, y, iz * tileSize);
        this.add(gh);
      }
    }
  }
}

export async function initViewer({ containerId = "viewer", statusId = "status" } = {}) {
  const $ = (id) => document.getElementById(id);
  const container = $(containerId);
  if (!container) throw new Error(`Container #${containerId} not found`);
  const statusEl = $(statusId);

  // ── ERROR OVERLAY (fallback UI якщо модель не завантажилась)
  const errorOverlay = document.createElement('div');
  errorOverlay.style.cssText = 'position:absolute;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.85);color:#fff;display:none;align-items:center;justify-content:center;flex-direction:column;z-index:1000;';
  errorOverlay.innerHTML = '<div style="text-align:center;padding:20px;"><h3 style="margin:0 0 12px 0;">Модель недоступна</h3><p style="margin:0 0 16px 0;opacity:0.8;">Не вдалося завантажити 3D-файл</p><button onclick="location.reload()" style="padding:10px 20px;cursor:pointer;background:#1a73e8;color:#fff;border:none;border-radius:6px;font-size:14px;">Оновити сторінку</button></div>';
  container.style.position = 'relative';
  container.appendChild(errorOverlay);

  function showError(msg) {
    console.error('[Viewer Error]:', msg);
    errorOverlay.style.display = 'flex';
    if (statusEl) statusEl.textContent = 'Помилка завантаження';
  }


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
  
  // ✅ Страховий пояс від NaN/0 дистанції (запобігає "чорному екрану")
  controls.addEventListener('change', () => {
    const d = camera.position.distanceTo(controls.target);
    if (!isFinite(d) || d < (controls.minDistance || 0.01)) {
      // Повертаємо камеру в адекватний стан
      const dir = camera.position.clone().sub(controls.target).normalize();
      const safeDist = controls.minDistance || 1;
      camera.position.copy(controls.target).add(dir.multiplyScalar(safeDist));
      camera.updateProjectionMatrix();
      controls.update();
    }
  });

  // [ДОДАНО] TransformControls (ґізмо як у Blender)
  const tctrl = new TransformControls(camera, renderer.domElement);
  scene.add(tctrl);
  tctrl.addEventListener("dragging-changed", (e) => { controls.enabled = !e.value; });
  let selectedObj = null;
  let currentSnap = null;

  // ── СВІТЛО/СІТКА
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const dir = new THREE.DirectionalLight(0xffffff, 0.9);
  dir.position.set(2, 2, 2);
  scene.add(dir);

  // ▸ Плиткова сітка без країв (вигляд як у твоєму GridHelper)
  const grid = new TiledGrid({
    tileSize:    10,
    divisions:   10,
    tilesRadius: 8,
    colorCenter: 0x3a4153,
    colorGrid:   0x262b39,
    y: 0
  });
  grid.userData.lockScale = true; // ← блокувати будь-яке масштабування "столу"
  scene.add(grid);

  // [+] авто-масштаб стола під модель — ВИМКНЕНО (no-op)
  const GRID_BASE_SIZE = 10; // лишив константу, щоб не ламати імпорти/пошук
  function resizeGridToModel(/* margin = 1.3 */) {
    if (!grid) return;
    // Фіксуємо стіл у стандартному стані
    grid.scale.set(1, 1, 1);
    grid.position.set(0, 0, 0);
  }

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
    
    // ✅ Правильні near/far для запобігання зникненню моделі
    const sizeLength = size.length();
    const safe = Math.max(sizeLength, 1);
    camera.near = safe / 1000;  // дуже малий near щоб не різало
    camera.far = safe * 1000;   // дуже великий far щоб не зникало
    camera.updateProjectionMatrix();
    
    controls.target.copy(center);
    
    // ✅ OrbitControls clamp (найважливіше) - запобігає "чорному екрану"
    controls.minDistance = safe * 0.15;  // щоб не влетіти в модель
    controls.maxDistance = safe * 10;    // щоб не відлетіти в космос
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
    // важливо: скинути трансформи, щоб нова модель не успадковувала старі зсуви
    modelRoot.position.set(0, 0, 0);
    modelRoot.rotation.set(0, 0, 0);
    modelRoot.scale.set(1, 1, 1);
    watermarkGroup.position.set(0, 0, 0);
    watermarkGroup.rotation.set(0, 0, 0);
    watermarkGroup.scale.set(1, 1, 1);
    if (statusEl) statusEl.textContent = "";
    resizeGridToModel(1.3);

    // [ДОДАНО] також відчепимо ґізмо і скинемо вибір
    detachTransform();
  }

  /**
   * ✅ Load 3D model from URL (STL, OBJ, PLY, glTF/GLB)
   * This is the main function for loading models in the viewer
   */
  async function loadModel(url) {
    if (!url) {
      console.warn('[VIEWER] loadModel: empty URL');
      return;
    }

    // ✅ CRITICAL: Clear previous model to prevent memory leaks
    clearAll();

    // ✅ Detect format from URL (strip query params)
    const cleanUrl = url.split('?')[0];
    const ext = cleanUrl.split('.').pop()?.toLowerCase() || '';
    
    console.log('[VIEWER] Loading model:', url, '| format:', ext);
    
    if (statusEl) statusEl.textContent = 'Loading model...';
    
    const onError = (err) => {
      console.error('[VIEWER] Load error:', err);
      showError(err?.message || 'Не вдалося завантажити модель');
      if (statusEl) statusEl.textContent = 'Помилка завантаження';
    };

    try {
      if (ext === 'stl') {
        stlLoader.load(
          url,
          (geom) => {
            addGeometry(geom);
            console.log('[VIEWER] ✅ STL loaded successfully');
            if (statusEl) statusEl.textContent = '';
          },
          undefined,
          onError
        );
      } else if (ext === 'obj') {
        objLoader.load(
          url,
          (obj) => {
            addObject(obj);
            console.log('[VIEWER] ✅ OBJ loaded successfully');
            if (statusEl) statusEl.textContent = '';
          },
          undefined,
          onError
        );
      } else if (ext === 'ply') {
        plyLoader.load(
          url,
          (geom) => {
            geom.computeVertexNormals();
            addGeometry(geom);
            console.log('[VIEWER] ✅ PLY loaded successfully');
            if (statusEl) statusEl.textContent = '';
          },
          undefined,
          onError
        );
      } else if (ext === 'gltf' || ext === 'glb') {
        gltfLoader.load(
          url,
          (gltf) => {
            addObject(gltf.scene);
            console.log('[VIEWER] ✅ glTF/GLB loaded successfully');
            if (statusEl) statusEl.textContent = '';
          },
          undefined,
          onError
        );
      } else {
        console.warn('[VIEWER] Unknown format:', ext, '- trying STL loader as fallback');
        // Fallback: try STL loader
        stlLoader.load(
          url,
          (geom) => {
            addGeometry(geom);
            console.log('[VIEWER] ✅ Loaded successfully (fallback STL)');
            if (statusEl) statusEl.textContent = '';
          },
          undefined,
          onError
        );
      }
    } catch (e) {
      onError(e);
    }
  }

  // ─────────────────────────────────────────────────────────────
  // АВТООРІЄНТАЦІЯ: шукаємо стабільну позу (найбільша площа контакту)
  // ─────────────────────────────────────────────────────────────
  function autoOrientUpright(object) {
    // Кандидати поворотів (рад): 0, ±90° навколо X/Z, 180°, та комбінації
    const deg = (a) => THREE.MathUtils.degToRad(a);
    const candidates = [
      new THREE.Euler(0, 0, 0),
      new THREE.Euler(deg(90), 0, 0),
      new THREE.Euler(deg(-90), 0, 0),
      new THREE.Euler(deg(180), 0, 0),
      new THREE.Euler(0, 0, deg(90)),
      new THREE.Euler(0, 0, deg(-90)),
      new THREE.Euler(0, 0, deg(180)),
      new THREE.Euler(deg(90), 0, deg(90)),
      new THREE.Euler(deg(-90), 0, deg(90)),
      new THREE.Euler(deg(90), 0, deg(-90)),
      new THREE.Euler(deg(-90), 0, deg(-90)),
    ];

    // Підрахунок «скору опори» для поточного стану об’єкта
    const tmpV = new THREE.Vector3();
    const meshes = [];
    object.traverse((n) => { if (n.isMesh && n.geometry?.attributes?.position) meshes.push(n); });

    function supportScore() {
      let minY = Infinity, maxY = -Infinity;
      // 1) знайдемо minY/maxY
      for (const m of meshes) {
        const pos = m.geometry.attributes.position;
        for (let i = 0; i < pos.count; i++) {
          tmpV.fromBufferAttribute(pos, i).applyMatrix4(m.matrixWorld);
          if (tmpV.y < minY) minY = tmpV.y;
          if (tmpV.y > maxY) maxY = tmpV.y;
        }
      }
      const height = Math.max(1e-6, maxY - minY);
      const tol = Math.max(0.0005, height * 0.01); // 1% висоти або 0.0005

      // 2) рахуємо вершини, що торкаються «підлоги», та їх розкид по XZ
      let count = 0;
      let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;

      for (const m of meshes) {
        const pos = m.geometry.attributes.position;
        for (let i = 0; i < pos.count; i++) {
          tmpV.fromBufferAttribute(pos, i).applyMatrix4(m.matrixWorld);
          if (tmpV.y <= minY + tol) {
            count++;
            if (tmpV.x < minX) minX = tmpV.x;
            if (tmpV.x > maxX) maxX = tmpV.x;
            if (tmpV.z < minZ) minZ = tmpV.z;
            if (tmpV.z > maxZ) maxZ = tmpV.z;
          }
        }
      }

      const spreadX = isFinite(minX) ? (maxX - minX) : 0;
      const spreadZ = isFinite(minZ) ? (maxZ - minZ) : 0;
      const areaRect = spreadX * spreadZ;

      // Переважуємо ширину опори, але враховуємо й кількість.
      // Коефіцієнт 100 робить пріоритет площі над просто кількістю вершин.
      return areaRect * 100 + count;
    }

    // Збережемо стан
    const savedRot = object.rotation.clone();

    // Перебір
    let bestEuler = savedRot.clone();
    object.updateWorldMatrix(true, true);
    let bestScore = supportScore();

    for (const e of candidates) {
      object.rotation.copy(e);
      object.updateWorldMatrix(true, true);
      const s = supportScore();
      if (s > bestScore) {
        bestScore = s;
        bestEuler = e.clone();
      }
    }

    // Застосовуємо кращий варіант
    object.rotation.copy(bestEuler);
    object.updateWorldMatrix(true, true);
  }

  function addGeometry(geometry) {
    geometry.computeVertexNormals?.();
    clearAll(); // щоб не тягнути старі трансформи
    const mesh = new THREE.Mesh(geometry, wireframeOn ? wireMaterial : baseMaterial);
    modelRoot.add(mesh);
    autoOrientUpright(modelRoot);
    centerAndDropToFloor(modelRoot);
    resizeGridToModel(1.3);
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
    clearAll(); // скинути трансформи перед новою моделлю
    modelRoot.add(obj);

    autoOrientUpright(modelRoot);
    centerAndDropToFloor(modelRoot);
    resizeGridToModel(1.3);
    fitCameraToObject(modelRoot, 1.6);
  }

  async function loadAnyFromFile(file) {
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    const url = URL.createObjectURL(file);
    const done = () => URL.revokeObjectURL(url);

    const onError = (err) => {
      console.error("Load error:", err);
      showError(err?.message || "Не вдалося прочитати файл");
      alert("Не вдалося прочитати файл. Підтримка: STL, OBJ, PLY, glTF/GLB.");
      done();
    };

    try {
      if (ext === "stl") {
        stlLoader.load(
          url,
          (geom) => { addGeometry(geom); done(); },
          undefined,
          onError
        );
      } else if (ext === "obj") {
        objLoader.load(
          url,
          (obj) => { addObject(obj); done(); },
          undefined,
          onError
        );
      } else if (ext === "ply") {
        plyLoader.load(
          url,
          (geom) => {
            geom.computeVertexNormals();
            addGeometry(geom);
            done();
          },
          undefined,
          onError
        );
      } else if (ext === "gltf" || ext === "glb") {
        gltfLoader.load(
          url,
          (gltf) => { addObject(gltf.scene); done(); },
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
    object.updateWorldMatrix(true, true);
    const box = new THREE.Box3().setFromObject(object);
    const center = box.getCenter(new THREE.Vector3());
    // Центруємо лише X та Z, Y не чіпаємо
    object.position.x -= center.x;
    object.position.z -= center.z;
  }

  /** Опускає об’єкт, щоб мінімальний Y = 0 (поставити "на стіл") */
  function dropToFloor(object) {
    object.updateWorldMatrix(true, true);
    const box = new THREE.Box3().setFromObject(object);
    const dy = box.min.y - 0;
    if (Math.abs(dy) > 0.0005) {
      object.position.y -= dy; // підняти/опустити щоб minY == 0
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
      resizeGridToModel(1.3);          // no-op — стіл фіксований
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
    // плавний спін для 'wm'
    const delta = clock.getDelta();
    if (spinFlag) watermarkGroup.rotation.y += delta * 0.6;

    controls.update();
    renderer.render(scene, camera);
  })();

  // ─────────────────────────────────────────────────────────────────────────────
  // ▼▼▼ ДОДАНО: API для ґізмо/трансформацій (як у Blender) ▼▼▼

  function attachTransform(obj3d) {
    if (!obj3d) return;
    selectedObj = obj3d;
    tctrl.attach(obj3d);
  }
  function detachTransform() {
    selectedObj = null;
    tctrl.detach();
  }
  function setMode(mode /* 'translate'|'rotate'|'scale' */) {
    const m = (mode === "rotate" || mode === "scale") ? mode : "translate";
    tctrl.setMode(m);
  }
  function setSpace(space /* 'world'|'local' */) {
    tctrl.setSpace(space === "local" ? "local" : "world");
  }
  function setGizmoSize(size = 1) {
    const s = Math.max(0.1, Math.min(5, Number(size) || 1));
    tctrl.setSize(s);
  }
  // step для move — у одиницях сцени (мм), для rotate — у градусах
  function setSnap(step /* number|null */) {
    currentSnap = (Number(step) && step > 0) ? Number(step) : null;
    if (currentSnap == null) {
      tctrl.setTranslationSnap(null);
      tctrl.setRotationSnap(null);
      tctrl.setScaleSnap(null);
      return;
    }
    tctrl.setTranslationSnap(currentSnap);
    tctrl.setRotationSnap(THREE.MathUtils.degToRad(currentSnap));
    tctrl.setScaleSnap(0); // масштаб без snap за замовчуванням
  }

  // зручно фокуситись на вибраному
  function focusSelection() {
    if (selectedObj) fitCameraToObject(selectedObj, 1.6);
    else if (modelRoot.children.length) fitCameraToObject(modelRoot, 1.6);
  }

  // ▲▲▲ КІНЕЦЬ ДОДАНОГО API ▲▲▲
  // ─────────────────────────────────────────────────────────────────────────────

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
    loadModel,           // ✅ Main model loader (by URL)
    loadAnyFromFile,
    setWireframe,

    // ▼ нові утиліти / API для інших модулів
    centerObject,
    dropToFloor,
    centerAndDropToFloor,
    setViewerMode,        // головне: перемикач "stl" ↔ "wm"
    resizeGridToModel,    // тепер no-op, щоб стіл не змінювався
    get viewerMode() { return viewerMode; },

    // ▼▼ API ґізмо
    transform: {
      controls: tctrl,
      get selected() { return selectedObj; },
      attach: attachTransform,
      detach: detachTransform,
      setMode,
      setSpace,
      setSize: setGizmoSize,
      setSnap,
      focus: focusSelection,
    },

    // ▼▼ Error handling
    showError,
  };

  // [ДОДАНО] потрібно для експортерів (new ctx.THREE.Group() тощо)
  ctx.THREE = THREE;

  // ✅ Dispatch ready event for external scripts
  // This allows viewer.js to know when ctx.loadModel is available
  setTimeout(() => {
    window.dispatchEvent(new CustomEvent('prooflyviewer:ready', { detail: { ctx } }));
    console.log('[stl_viewer] ✅ Viewer ready, event dispatched');
  }, 0);

  return ctx;
}
