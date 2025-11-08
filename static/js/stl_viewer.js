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

/* =========================================================
   InfiniteGridWorld — нескінченна сітка "як у Blender"
   — Прив’язана до світу (не до камери) → лінії не “пливуть”.
   — Без видимих країв (велика площина + fade).
   — Кольори в стилі твого GridHelper: 0x3a4153 / 0x262b39.
   ========================================================= */
class InfiniteGridWorld extends THREE.Mesh {
  constructor({
    size1 = 10.0,     // дрібна клітинка (наприклад, 10 мм)
    size2 = 100.0,    // товста лінія (кожні 100 мм)
    color1 = 0x262b39,
    color2 = 0x3a4153,
    fadeDistance = 2500.0, // доки видно сітку
    thickness1 = 1.0,      // товщина дрібних ліній у px
    thickness2 = 1.6       // товщина товстих ліній у px
  } = {}) {
    const uniforms = {
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

    // Сітка зафіксована у СВІТІ: p = vWorld.xz (без camera offset)
    const frag = /* glsl */`
      precision highp float;
      varying vec3 vWorld;
      uniform float uSize1; uniform float uSize2;
      uniform vec3  uColor1; uniform vec3  uColor2;
      uniform float uFade;
      uniform float uTh1; uniform float uTh2;

      float gridDist(vec2 p, float s){
        vec2 g = abs(fract(p / s - 0.5) - 0.5) * s;
        return min(g.x, g.y);
      }

      void main(){
        vec2 p = vWorld.xz;

        float d1 = gridDist(p, uSize1);
        float d2 = gridDist(p, uSize2);

        float line1 = smoothstep(0.0, uTh1, uTh1 - d1);
        float line2 = smoothstep(0.0, uTh2, uTh2 - d2);

        vec3 col = mix(vec3(0.0), uColor1, line1);   // дрібні лінії
        col = mix(col, uColor2, line2);              // товсті лінії пріоритетні

        // Радіальний fade від центру світу — щоб не було видно краю площини
        float dist = length(p);
        float fade = 1.0 - smoothstep(uFade*0.7, uFade, dist);
        float alpha = max(line1, line2) * fade;
        if(alpha < 0.01) discard;

        gl_FragColor = vec4(col * fade, alpha);
      }
    `;

    const mat = new THREE.ShaderMaterial({
      uniforms, vertexShader: vert, fragmentShader: frag,
      transparent: true, depthWrite: false
    });

    // Дуже велика площина — шейдер робить її візуально "нескінченною"
    const geo = new THREE.PlaneGeometry(100000, 100000, 1, 1);
    super(geo, mat);
    this.rotation.x = -Math.PI / 2;
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
  tctrl.addEventListener("dragging-changed", (e) => { controls.enabled = !e.value; });
  let selectedObj = null;
  let currentSnap = null;

  // ── СВІТЛО/СІТКА
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const dir = new THREE.DirectionalLight(0xffffff, 0.9);
  dir.position.set(2, 2, 2);
  scene.add(dir);

  // ▸ NESKІNCHENNA СІТКА зі стилем як у твоєму GridHelper
  const grid = new InfiniteGridWorld({
    size1: 10.0,      // 10 мм
    size2: 100.0,     // 100 мм
    color1: 0x262b39, // дрібні
    color2: 0x3a4153, // товсті
    fadeDistance: 2500.0
  });
  grid.position.y = 0;
  grid.userData.lockScale = true; // ← не даємо resizeGridToModel змінювати scale
  scene.add(grid);

  // [+] авто-масштаб стола під модель (АЛЕ ми це блокуємо, якщо lockScale=true)
  const GRID_BASE_SIZE = 10;
  function resizeGridToModel(margin = 1.3) {
    if (grid.userData?.lockScale) {      // ← додано: фіксований розмір сітки
      grid.scale.set(1, 1, 1);
      grid.position.set(0, 0, 0);
      return;
    }
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
    modelRoot.position.set(0, 0, 0);
    modelRoot.rotation.set(0, 0, 0);
    modelRoot.scale.set(1, 1, 1);
    watermarkGroup.position.set(0, 0, 0);
    watermarkGroup.rotation.set(0, 0, 0);
    watermarkGroup.scale.set(1, 1, 1);
    if (statusEl) statusEl.textContent = "";
    resizeGridToModel(1.3);
    detachTransform();
  }

  // автоорієнтація: приводить модель до Y-up (враховує Z-up і X-up)
  function autoOrientUpright(object) {
    object.updateWorldMatrix(true, true);
    const box  = new THREE.Box3().setFromObject(object);
    const size = box.getSize(new THREE.Vector3());
    const axes = [
      { axis: "x", v: size.x },
      { axis: "y", v: size.y },
      { axis: "z", v: size.z },
    ].sort((a, b) => b.v - a.v);
    const up = axes[0].axis;

    if (up === "z") object.rotation.x += -Math.PI / 2;
    else if (up === "x") object.rotation.z +=  Math.PI / 2;
    object.updateWorldMatrix(true, true);
  }

  function addGeometry(geometry) {
    geometry.computeVertexNormals?.();
    clearAll();
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
    clearAll();
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
        stlLoader.load(url, (geom) => { addGeometry(geom); done(); }, undefined, onError);
      } else if (ext === "obj") {
        objLoader.load(url, (obj) => { addObject(obj); done(); }, undefined, onError);
      } else if (ext === "ply") {
        plyLoader.load(url, (geom) => {
          geom.computeVertexNormals();
          addGeometry(geom);
          done();
        }, undefined, onError);
      } else if (ext === "gltf" || ext === "glb") {
        gltfLoader.load(url, (gltf) => { addObject(gltf.scene); done(); }, undefined, onError);
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
  // ▼▼▼ РЕЖИМИ: "stl" (зі столом) і "wm" (без стола + 360°) ▼▼▼
  let viewerMode = "stl";
  const clock = new THREE.Clock();
  let spinFlag = false;
  controls.autoRotate = false;
  controls.autoRotateSpeed = 1.2;

  function centerObject(object) {
    object.updateWorldMatrix(true, true);
    const box = new THREE.Box3().setFromObject(object);
    const center = box.getCenter(new THREE.Vector3());
    object.position.x -= center.x;
    object.position.z -= center.z;
  }

  function dropToFloor(object) {
    object.updateWorldMatrix(true, true);
    const box = new THREE.Box3().setFromObject(object);
    const dy = box.min.y - 0;
    if (Math.abs(dy) > 0.0005) object.position.y -= dy;
  }

  function centerAndDropToFloor(object) {
    centerObject(object);
    dropToFloor(object);
  }

  function setViewerMode(mode /* 'stl' | 'wm' */) {
    viewerMode = mode === "wm" ? "wm" : "stl";

    if (viewerMode === "stl") {
      grid.visible = true;
      resizeGridToModel(1.3);
      controls.autoRotate = false;
      spinFlag = false;
    } else {
      grid.visible = false;
      controls.autoRotate = true;
      controls.autoRotateSpeed = 1.2;
      spinFlag = true;
      centerObject(watermarkGroup);
      fitCameraToObject(watermarkGroup, 1.4);
    }
  }

  // ── РЕНДЕР-ЛУП
  (function loop() {
    requestAnimationFrame(loop);
    const delta = clock.getDelta();
    if (spinFlag) watermarkGroup.rotation.y += delta * 0.6;
    controls.update();
    renderer.render(scene, camera);
  })();

  // ─────────────────────────────────────────────────────────────────────────────
  // ▼▼▼ API ґізмо/трансформацій ▼▼▼
  function attachTransform(obj3d) { if (!obj3d) return; selectedObj = obj3d; tctrl.attach(obj3d); }
  function detachTransform() { selectedObj = null; tctrl.detach(); }
  function setMode(mode) { const m = (mode === "rotate" || mode === "scale") ? mode : "translate"; tctrl.setMode(m); }
  function setSpace(space) { tctrl.setSpace(space === "local" ? "local" : "world"); }
  function setGizmoSize(size = 1) { const s = Math.max(0.1, Math.min(5, Number(size) || 1)); tctrl.setSize(s); }
  function setSnap(step) {
    currentSnap = (Number(step) && step > 0) ? Number(step) : null;
    if (currentSnap == null) { tctrl.setTranslationSnap(null); tctrl.setRotationSnap(null); tctrl.setScaleSnap(null); return; }
    tctrl.setTranslationSnap(currentSnap);
    tctrl.setRotationSnap(THREE.MathUtils.degToRad(currentSnap));
    tctrl.setScaleSnap(0);
  }
  function focusSelection() {
    if (selectedObj) fitCameraToObject(selectedObj, 1.6);
    else if (modelRoot.children.length) fitCameraToObject(modelRoot, 1.6);
  }

  // ── ПОВЕРТАЄМО КОНТЕКСТ
  const ctx = {
    container, statusEl,
    scene, camera, renderer, controls,
    modelRoot, watermarkGroup, grid, dirLight: dir,
    baseMaterial, wireMaterial, get wireframeOn() { return wireframeOn; },
    stlLoader, gltfLoader, objLoader, plyLoader,
    resize, fitCameraToObject, resetCamera, clearAll,
    addGeometry, addObject, loadAnyFromFile, setWireframe,
    centerObject, dropToFloor, centerAndDropToFloor,
    setViewerMode, resizeGridToModel, get viewerMode() { return viewerMode; },
    transform: {
      controls: tctrl,
      get selected() { return selectedObj; },
      attach: attachTransform,
      detach: detachTransform,
      setMode, setSpace, setSize: setGizmoSize, setSnap, focus: focusSelection,
    },
  };
  return ctx;
}
