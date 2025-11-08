// static/js/stl_viewer.js
// Створює сцену Three.js, рендер, камеру, групи та лоадери.
// Експортує initViewer(), що повертає контекст ctx з усіма потрібними методами.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TransformControls } from "three/addons/controls/TransformControls.js"; // [ДОДАНО]
import { STLLoader }     from "stl/loader";
import { GLTFLoader }    from "gltf/loader";
import { OBJLoader }     from "obj/loader";
import { PLYLoader }     from "ply/loader";

/* ===========================
   Infinite, Blender-style grid
   ===========================
   Без видимих країв; лінії малюються шейдером, fade у даль.
   Ім'я об'єкта — як у тебе: grid (підміна GridHelper), щоб не ламати існуючі функції.
*/
class InfiniteGrid extends THREE.Mesh {
  constructor({
    size1 = 10.0,      // крок дрібної сітки (напр. 10 мм)
    size2 = 100.0,     // товста лінія кожні 100 мм
    color1 = new THREE.Color(0x262b39),
    color2 = new THREE.Color(0x3a4153),
    fadeDistance = 2500.0, // доки видно сітку
    thickness1 = 1.0,      // товщина дрібних ліній (в пікселях)
    thickness2 = 1.6       // товщина товстих ліній
  } = {}) {
    const uniforms = {
      uCamPos: { value: new THREE.Vector3() },
      uSize1:  { value: size1 },
      uSize2:  { value: size2 },
      uColor1: { value: new THREE.Color(color1) },
      uColor2: { value: new THREE.Color(color2) },
      uFade:   { value: fadeDistance },
      uTh1:    { value: thickness1 },
      uTh2:    { value: thickness2 },
    };

    const vert = /* glsl */`
      varying vec3 vWorld;
      void main(){
        vec4 wp = modelMatrix * vec4(position,1.0);
        vWorld = wp.xyz;
        gl_Position = projectionMatrix * viewMatrix * wp;
      }
    `;

    const frag = /* glsl */`
      precision highp float;
      varying vec3 vWorld;
      uniform vec3 uCamPos;
      uniform float uSize1; uniform float uSize2;
      uniform vec3 uColor1; uniform vec3 uColor2;
      uniform float uFade;
      uniform float uTh1; uniform float uTh2;

      // відстань до найближчої лінії періодичної решітки з кроком s
      float gridDist(vec2 p, float s){
        vec2 g = abs(fract(p / s - 0.5) - 0.5) * s;
        return min(g.x, g.y);
      }

      void main(){
        // щоб сітка була "під ногами", підставляємо позицію камери
        vec2 p = (vWorld.xz + uCamPos.xz);

        float d1 = gridDist(p, uSize1);
        float d2 = gridDist(p, uSize2);

        float line1 = smoothstep(0.0, uTh1, uTh1 - d1);
        float line2 = smoothstep(0.0, uTh2, uTh2 - d2);

        vec3 col = mix(uColor1, uColor2, line2);
        col = mix(vec3(0.0), col, max(line1, line2));

        float dist = length(vWorld.xz - uCamPos.xz);
        float fade = 1.0 - smoothstep(uFade*0.7, uFade, dist);
        col *= fade;

        float alpha = max(line1, line2) * fade;
        if(alpha < 0.01) discard;

        gl_FragColor = vec4(col, alpha);
      }
    `;

    const mat = new THREE.ShaderMaterial({
      uniforms, vertexShader: vert, fragmentShader: frag,
      transparent: true, depthWrite: false
    });

    // геометрія велика, але шейдер робить її візуально нескінченною
    const geo = new THREE.PlaneGeometry(10000, 10000, 1, 1);
    super(geo, mat);
    this.rotation.x = -Math.PI / 2;

    this.onBeforeRender = (_r, _s, camera) => {
      mat.uniforms.uCamPos.value.copy(camera.position);
    };
  }
}

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
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    logarithmicDepthBuffer: true
  });
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  container.appendChild(renderer.domElement);

  // ── КОНТРОЛИ
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  // [ДОДАНО] TransformControls (ґізмо як у Blender)
  const tctrl = new TransformControls(camera, renderer.domElement);
  scene.add(tctrl);
  // під час перетягування блокуємо OrbitControls
  tctrl.addEventListener("dragging-changed", (e) => { controls.enabled = !e.value; });
  // внутрішній стан вибраного об’єкта та налаштувань
  let selectedObj = null;
  let currentSnap = null; // мм для move, градуси для rotate (див. setSnap нижче)

  // ── СВІТЛО/СІТКА
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const dir = new THREE.DirectionalLight(0xffffff, 0.9);
  dir.position.set(2, 2, 2);
  scene.add(dir);

  // ▸ ПІДМІНА GridHelper на нескінченну сітку (ім’я: grid — як раніше)
  const grid = new InfiniteGrid({
    size1: 10.0,     // дрібна клітинка 10 мм
    size2: 100.0,    // товста лінія 100 мм
    fadeDistance: 2500.0
  });
  grid.position.y = 0;
  scene.add(grid);

  // [+] авто-масштаб стола під модель (залишаємо як є — не ламає, просто scale буде майже непомітний)
  const GRID_BASE_SIZE = 10; // як у GridHelper(10, 10)
  function resizeGridToModel(margin = 1.3) {
    if (!modelRoot.children.length) {
      grid.scale.set(1, 1, 1);
      grid.position.set(0, 0, 0);
      return;
    }
    const box = new THREE.Box3().setFromObject(modelRoot);
    const size = box.getSize(new THREE.Vector3());
    const span = Math.max(size.x, size.z) * margin || GRID_BASE_SIZE;
    const scale = span / GRID_BASE_SIZE;
    grid.scale.set(scale, 1, scale);
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

  // автоорієнтація: приводить модель до Y-up (враховує Z-up і X-up)
  function autoOrientUpright(object) {
    object.updateWorldMatrix(true, true);
    const box  = new THREE.Box3().setFromObject(object);
    const size = box.getSize(new THREE.Vector3());

    // Вісь з найбільшим розміром трактуємо як "висоту" моделі
    const axes = [
      { axis: "x", v: size.x },
      { axis: "y", v: size.y },
      { axis: "z", v: size.z },
    ].sort((a, b) => b.v - a.v);
    const up = axes[0].axis; // 'x' | 'y' | 'z'

    if (up === "z") {
      // Z-up → покласти Z у Y
      object.rotation.x += -Math.PI / 2;
    } else if (up === "x") {
      // X-up → повернути X у Y
      object.rotation.z +=  Math.PI / 2;
    }
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
      resizeGridToModel(1.3);          // підганяємо стіл при поверненні
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
    loadAnyFromFile,
    setWireframe,

    // ▼ нові утиліти / API для інших модулів
    centerObject,
    dropToFloor,
    centerAndDropToFloor,
    setViewerMode,        // головне: перемикач "стл" ↔ "wm"
    resizeGridToModel,    // доступно ззовні при потребі
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
  };

  return ctx;
}
