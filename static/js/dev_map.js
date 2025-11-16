/* ==========================================================
   DEV MAP — Глобальна карта файлів Proofly
   Рендер вузлів, стрілок, масштаб, панорамування, деталі,
   перетягування окремих вузлів
   ========================================================== */

(function () {
  const tree = window.__DEV_TREE__ || null;
  if (!tree) {
    console.error("DEV_MAP: no tree data");
    return;
  }

  const canvas = document.getElementById("devmap-canvas");
  const wrapper = document.getElementById("devmap-wrapper");

  // Права панель
  const detail_title = document.getElementById("dm-detail-title");
  const detail_path = document.getElementById("dm-detail-path");
  const detail_type = document.getElementById("dm-detail-type");
  const detail_feature = document.getElementById("dm-detail-feature");
  const detail_status = document.getElementById("dm-detail-status-text");
  const detail_ai = document.getElementById("dm-detail-ai-text");

  // Масштаб та переміщення ВСЬОГО полотна
  let scale = 1;
  let offsetX = 50;
  let offsetY = 50;
  let panDragging = false;
  let panStartX = 0;
  let panStartY = 0;

  // Дані по вузлах та стрілках
  const nodePositions = {};        // id → {x,y,width,height,node,el}
  const edges = [];                // {fromId,toId,svg,line}

  /* ===========================
     МАСШТАБУВАННЯ ВСІЄЇ КАРТИ
     =========================== */
  wrapper.addEventListener("wheel", (e) => {
    e.preventDefault();
    const zoomSpeed = 0.08;
    scale += e.deltaY < 0 ? zoomSpeed : -zoomSpeed;
    scale = Math.max(0.3, Math.min(scale, 2.5));
    updateTransform();
  });

  /* Перетягування ВСІЄЇ карти (фон) */
  wrapper.addEventListener("mousedown", (e) => {
    // Якщо клікнули по вузлу – перетягування вузла обробляється окремо
    if (e.target.classList.contains("dm-node")) return;
    panDragging = true;
    panStartX = e.clientX;
    panStartY = e.clientY;
  });

  window.addEventListener("mouseup", () => {
    panDragging = false;
    draggingNode = null;
  });

  window.addEventListener("mousemove", (e) => {
    if (panDragging) {
      offsetX += e.clientX - panStartX;
      offsetY += e.clientY - panStartY;
      panStartX = e.clientX;
      panStartY = e.clientY;
      updateTransform();
    }
    if (draggingNode) {
      dragNodeMove(e);
    }
  });

  function updateTransform() {
    canvas.style.transform = `translate(${offsetX}px, ${offsetY}px) scale(${scale})`;
  }

  /* Кнопки масштабування */
  const btnIn = document.getElementById("dm-zoom-in");
  const btnOut = document.getElementById("dm-zoom-out");
  const btnReset = document.getElementById("dm-zoom-reset");
  const btnCenter = document.getElementById("dm-center");

  btnIn && (btnIn.onclick = () => {
    scale = Math.min(2.5, scale + 0.1);
    updateTransform();
  });

  btnOut && (btnOut.onclick = () => {
    scale = Math.max(0.3, scale - 0.1);
    updateTransform();
  });

  btnReset && (btnReset.onclick = () => {
    scale = 1;
    updateTransform();
  });

  btnCenter && (btnCenter.onclick = () => {
    offsetX = 50;
    offsetY = 50;
    scale = 1;
    updateTransform();
  });

  /* =================================================
     РЕНДЕР ДЕРЕВА — РЕКУРСИВНО
     ================================================= */

  function renderTree(root, x, y) {
    createNode(root, x, y);

    const children = root.children || [];
    const gapY = 150;
    const gapX = 250;

    let childX = x - ((children.length - 1) * gapX) / 2;

    children.forEach((child) => {
      renderTree(child, childX, y + gapY);
      createEdge(root.id, child.id);
      childX += gapX;
    });
  }

  /* Створити вузол */
  let draggingNode = null;
  let nodeStartX = 0;
  let nodeStartY = 0;
  let mouseStartX = 0;
  let mouseStartY = 0;

  function createNode(node, x, y) {
    const el = document.createElement("div");
    el.className = `dm-node dm-${node.status}`;
    el.style.left = x + "px";
    el.style.top = y + "px";
    el.textContent = node.label;
    el.dataset.id = node.id;

    canvas.appendChild(el);

    nodePositions[node.id] = {
      x: x,
      y: y,
      width: el.offsetWidth,
      height: el.offsetHeight,
      node: node,
      el: el
    };

    // Клік → деталі
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      showDetails(node);
    });

    // Перетягування конкретного вузла
    el.addEventListener("mousedown", (e) => {
      e.stopPropagation(); // не запускаємо панорамування
      draggingNode = nodePositions[node.id];
      nodeStartX = draggingNode.x;
      nodeStartY = draggingNode.y;
      mouseStartX = e.clientX;
      mouseStartY = e.clientY;
    });
  }

  function dragNodeMove(e) {
    const dx = (e.clientX - mouseStartX) / scale;
    const dy = (e.clientY - mouseStartY) / scale;

    draggingNode.x = nodeStartX + dx;
    draggingNode.y = nodeStartY + dy;

    const el = draggingNode.el;
    el.style.left = draggingNode.x + "px";
    el.style.top = draggingNode.y + "px";

    repositionEdges();
  }

  /* Малювання стрілки (зберігаємо, щоб оновлювати) */
  function createEdge(fromId, toId) {
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.classList.add("dm-edge");

    const line = document.createElementNS(svgNS, "line");
    svg.appendChild(line);

    canvas.appendChild(svg);

    edges.push({ fromId, toId, svg, line });
    repositionEdge(edges[edges.length - 1]);
  }

  function repositionEdges() {
    edges.forEach(repositionEdge);
  }

  function repositionEdge(edge) {
    const p1 = nodePositions[edge.fromId];
    const p2 = nodePositions[edge.toId];
    if (!p1 || !p2) return;

    const x1 = p1.x + p1.width / 2;
    const y1 = p1.y + p1.height;
    const x2 = p2.x + p2.width / 2;
    const y2 = p2.y;

    const left = Math.min(x1, x2);
    const top = Math.min(y1, y2);
    const width = Math.abs(x2 - x1);
    const height = Math.abs(y2 - y1);

    const svg = edge.svg;
    const line = edge.line;

    svg.style.left = left + "px";
    svg.style.top = top + "px";
    svg.style.width = width + "px";
    svg.style.height = height + "px";

    line.setAttribute("x1", x1 < x2 ? 0 : width);
    line.setAttribute("y1", y1 < y2 ? 0 : height);
    line.setAttribute("x2", x2 < x1 ? 0 : width);
    line.setAttribute("y2", y2 < y1 ? 0 : height);
  }

  /* =================================================
     ПРАВА ПАНЕЛЬ — деталі вузла
     ================================================= */

  function showDetails(node) {
    detail_title.textContent = node.label;
    detail_path.textContent = node.label;
    detail_type.textContent = node.type;
    detail_feature.textContent = node.feature || "(немає)";
    detail_status.textContent =
      node.status === "ok"
        ? "🟢 Все ок"
        : node.status === "fix"
        ? "🔵 Потрібна правка"
        : node.status === "error"
        ? "🔴 Проблема"
        : "⚪ Не підключено";

    const aiText =
`Файл: ${node.label}
Тип: ${node.type}
Статус: ${node.status}

Опис проблеми / правки:
(впиши тут свої слова і кинь у чат)

Додаткова інформація:
${node.notes || "(немає)"} 
`;

    detail_ai.textContent = aiText;
  }

  /* =================================================
     ЗАПУСК РЕНДЕРА
     ================================================= */

  renderTree(tree, 500, 20);
  repositionEdges();
  updateTransform();
})();
