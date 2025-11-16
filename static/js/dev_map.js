// static/js/dev_map.js
// Dev Map — автоматичне дерево файлів з можливістю перетягування карти.
// Беремо window.__DEV_TREE__ із бекенду і малюємо дерево:
// root зверху, діти нижче. Орфани (непідключені файли) йдуть окремою гілкою.

(function () {
  const tree = window.__DEV_TREE__;
  if (!tree) {
    console.warn("Dev Map: __DEV_TREE__ is empty");
    return;
  }

  const wrapper = document.getElementById("devmap-wrapper");
  const canvas = document.getElementById("devmap-canvas");

  if (!wrapper || !canvas) {
    console.warn("Dev Map: wrapper/canvas not found");
    return;
  }

  // Права панель
  const detailTitle = document.getElementById("dm-detail-title");
  const detailPath = document.getElementById("dm-detail-path");
  const detailType = document.getElementById("dm-detail-type");
  const detailFeature = document.getElementById("dm-detail-feature");
  const detailStatus = document.getElementById("dm-detail-status-text");
  const detailAiText = document.getElementById("dm-detail-ai-text");

  // Кнопки зуму
  const btnZoomIn = document.getElementById("dm-zoom-in");
  const btnZoomOut = document.getElementById("dm-zoom-out");
  const btnZoomReset = document.getElementById("dm-zoom-reset");
  const btnCenter = document.getElementById("dm-center");

  // Параметри лейауту дерева (зроблено компактніше)
  const NODE_WIDTH = 120;   // умовна ширина ноди
  const NODE_HEIGHT = 40;   // умовна висота (для розрахунку відступів по Y)
  const GAP_X = 24;         // горизонтальний відступ між нодами
  const GAP_Y = 60;         // вертикальний відступ між рівнями

  // Масштаб
  let currentScale = 1;
  const MIN_SCALE = 0.3;
  const MAX_SCALE = 2.0;
  const SCALE_STEP = 0.1;

  // Позиції та DOM-ноди
  const nodePositions = {};  // id -> { x, y, width, height, el, node }
  const edges = [];          // { fromId, toId, el, path }

  // ==== АВТО-ЛЕЙАУТ ДЕРЕВА =================================================

  function computeLayout(root) {
    let leafIndex = 0;

    function dfs(node, depth) {
      node._depth = depth;
      const children = Array.isArray(node.children) ? node.children : [];

      if (!children.length) {
        node._x = leafIndex;
        leafIndex += 1;
      } else {
        children.forEach(child => dfs(child, depth + 1));
        let minX = children[0]._x;
        let maxX = children[0]._x;
        for (let i = 1; i < children.length; i++) {
          if (children[i]._x < minX) minX = children[i]._x;
          if (children[i]._x > maxX) maxX = children[i]._x;
        }
        node._x = (minX + maxX) / 2;
      }
    }

    dfs(root, 0);
  }

  function assignPixelPositions(root) {
    let minX = Infinity;
    let maxX = -Infinity;
    let maxDepth = 0;

    function visit(node) {
      const x = node._x * (NODE_WIDTH + GAP_X);
      const y = node._depth * (NODE_HEIGHT + GAP_Y);

      node._px = x;
      node._py = y;

      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (node._depth > maxDepth) maxDepth = node._depth;

      const children = Array.isArray(node.children) ? node.children : [];
      children.forEach(visit);
    }

    visit(root);

    const shiftX = minX < 0 ? -minX + GAP_X : GAP_X;
    const shiftY = GAP_Y;

    function applyShift(node) {
      node.x = node._px + shiftX;
      node.y = node._py + shiftY;

      const children = Array.isArray(node.children) ? node.children : [];
      children.forEach(applyShift);
    }

    applyShift(root);

    const width = (maxX - minX) + 2 * GAP_X + NODE_WIDTH;
    const height = (maxDepth + 1) * (NODE_HEIGHT + GAP_Y) + 2 * GAP_Y;

    canvas.style.width = Math.max(width, wrapper.clientWidth) + "px";
    canvas.style.height = Math.max(height, wrapper.clientHeight) + "px";
  }

  // ==== РЕНДЕР НОД І СТРІЛОК ===============================================

  function createNode(node) {
    const el = document.createElement("div");
    el.classList.add("dm-node");

    const status = node.status || "ok";
    el.classList.add("dm-" + status);

    el.dataset.id = node.id;
    el.textContent = node.label || node.path || "???";

    el.style.position = "absolute";
    el.style.left = node.x + "px";
    el.style.top = node.y + "px";

    el.addEventListener("click", () => {
      setActiveNode(node.id);
      showDetails(node);
    });

    canvas.appendChild(el);

    const rect = el.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;

    nodePositions[node.id] = {
      x: node.x,
      y: node.y,
      width,
      height,
      el,
      node
    };
  }

  function renderNodes(root) {
    function walk(node) {
      createNode(node);
      const children = Array.isArray(node.children) ? node.children : [];
      children.forEach(walk);
    }
    walk(root);
  }

  // --- Стрілки -------------------------------------------------------------

  const NODE_MARGIN = 8; // щоб лінії не входили в прямокутники

  function createEdge(fromId, toId) {
    const from = nodePositions[fromId];
    const to = nodePositions[toId];
    if (!from || !to) return;

    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.classList.add("dm-edge");
    svg.style.position = "absolute";

    const path = document.createElementNS(svgNS, "path");
    svg.appendChild(path);

    canvas.appendChild(svg);

    const edge = { fromId, toId, el: svg, path };
    edges.push(edge);
    repositionEdge(edge);
  }

  function repositionEdge(edge) {
    const from = nodePositions[edge.fromId];
    const to = nodePositions[edge.toId];
    if (!from || !to) return;

    const x1 = from.x + from.width / 2;
    const y1 = from.y + from.height;
    const x2 = to.x + to.width / 2;
    const y2 = to.y;

    const startX = x1;
    const startY = y1 + NODE_MARGIN;
    const endX = x2;
    const endY = y2 - NODE_MARGIN;

    const pad = 8;
    const left = Math.min(startX, endX) - pad;
    const top = Math.min(startY, endY) - pad;
    const right = Math.max(startX, endX) + pad;
    const bottom = Math.max(startY, endY) + pad;
    const width = right - left;
    const height = bottom - top;

    edge.el.style.left = left + "px";
    edge.el.style.top = top + "px";
    edge.el.setAttribute("width", width);
    edge.el.setAttribute("height", height);

    const sx = startX - left;
    const sy = startY - top;
    const ex = endX - left;
    const ey = endY - top;

    // Пряма тонка лінія (без "ковбаски")
    edge.path.setAttribute("d", `M ${sx} ${sy} L ${ex} ${ey}`);
  }

  function renderEdges(root) {
    function walk(node) {
      const children = Array.isArray(node.children) ? node.children : [];
      children.forEach(child => {
        createEdge(node.id, child.id);
        walk(child);
      });
    }
    walk(root);
  }

  // ==== ПРАВА ПАНЕЛЬ =======================================================

  function showDetails(node) {
    if (!node) return;

    if (detailTitle) detailTitle.textContent = node.label || node.path || node.id;
    if (detailPath) detailPath.textContent = node.path || "";
    if (detailType) detailType.textContent = node.type || "";
    if (detailFeature) detailFeature.textContent = node.feature || "";
    if (detailStatus) detailStatus.textContent = node.status || "ok";

    if (detailAiText) {
      const lines = [];
      lines.push(`Файл: ${node.path || node.label || node.id}`);
      lines.push(`Тип: ${node.type || "unknown"}`);
      lines.push(`Статус: ${node.status || "ok"}`);
      if (node.feature) lines.push(`Фіча: ${node.feature}`);
      if (node.notes) lines.push(`Нотатки: ${node.notes}`);
      lines.push("");
      lines.push("Опиши тут, що треба зробити з цим файлом, і кинь цей текст в чат ChatGPT:");
      lines.push("");
      lines.push("- Поточна проблема / задача:");
      lines.push("- Що треба змінити / додати:");
      lines.push("- Що вже є в цьому файлі:");

      detailAiText.value = lines.join("\n");
    }
  }

  function setActiveNode(nodeId) {
    Object.values(nodePositions).forEach(info => {
      info.el.classList.remove("dm-node-active");
    });
    const info = nodePositions[nodeId];
    if (info) {
      info.el.classList.add("dm-node-active");
    }
  }

  // ==== ЗУМ / ПЕРЕТЯГУВАННЯ КАРТИ =========================================

  function applyScale() {
    canvas.style.transformOrigin = "0 0";
    canvas.style.transform = `scale(${currentScale})`;
  }

  function zoomIn() {
    currentScale = Math.min(MAX_SCALE, currentScale + SCALE_STEP);
    applyScale();
  }

  function zoomOut() {
    currentScale = Math.max(MIN_SCALE, currentScale - SCALE_STEP);
    applyScale();
  }

  function zoomReset() {
    currentScale = 1;
    applyScale();
  }

  function centerView() {
    const rect = canvas.getBoundingClientRect();
    const w = rect.width * currentScale;
    const h = rect.height * currentScale;

    const cw = wrapper.clientWidth;
    const ch = wrapper.clientHeight;

    wrapper.scrollLeft = Math.max(0, (w - cw) / 2);
    wrapper.scrollTop = Math.max(0, (h - ch) / 2);
  }

  if (btnZoomIn) btnZoomIn.addEventListener("click", zoomIn);
  if (btnZoomOut) btnZoomOut.addEventListener("click", zoomOut);
  if (btnZoomReset) btnZoomReset.addEventListener("click", () => {
    zoomReset();
    centerView();
  });
  if (btnCenter) btnCenter.addEventListener("click", centerView);

  // Zoom колесиком миші
  wrapper.addEventListener("wheel", (e) => {
    e.preventDefault(); // щоб не скролило сторінку
    const delta = e.deltaY;
    if (delta > 0) {
      currentScale = Math.max(MIN_SCALE, currentScale - SCALE_STEP);
    } else {
      currentScale = Math.min(MAX_SCALE, currentScale + SCALE_STEP);
    }
    applyScale();
  }, { passive: false });

  // ---- Drag-перетягування карти (панорамування) ---------------------------

  let isPanning = false;
  let panStartX = 0;
  let panStartY = 0;
  let panScrollLeft = 0;
  let panScrollTop = 0;

  function onPanMouseDown(e) {
    // ЛКМ
    if (e.button !== 0) return;

    // Якщо клік по ноді — даємо можливість клікати, а не тягати карту
    if (e.target.closest(".dm-node")) return;

    isPanning = true;
    panStartX = e.clientX;
    panStartY = e.clientY;
    panScrollLeft = wrapper.scrollLeft;
    panScrollTop = wrapper.scrollTop;

    wrapper.style.cursor = "grabbing";

    document.addEventListener("mousemove", onPanMouseMove);
    document.addEventListener("mouseup", onPanMouseUp);
  }

  function onPanMouseMove(e) {
    if (!isPanning) return;
    const dx = e.clientX - panStartX;
    const dy = e.clientY - panStartY;

    wrapper.scrollLeft = panScrollLeft - dx;
    wrapper.scrollTop = panScrollTop - dy;
  }

  function onPanMouseUp() {
    isPanning = false;
    wrapper.style.cursor = "default";
    document.removeEventListener("mousemove", onPanMouseMove);
    document.removeEventListener("mouseup", onPanMouseUp);
  }

  wrapper.addEventListener("mousedown", onPanMouseDown);

  // ==== СТАРТ =============================================================

  function init() {
    computeLayout(tree);
    assignPixelPositions(tree);

    renderNodes(tree);
    renderEdges(tree);

    applyScale();
    centerView();

    if (tree.id) {
      setActiveNode(tree.id);
      showDetails(tree);
    }
  }

  init();
})();
