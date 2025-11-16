/* ==========================================================
   DEV MAP — Глобальна карта файлів Proofly
   Рендер вузлів, стрілок, масштаб, панорамування, деталі
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

  // Масштаб та переміщення
  let scale = 1;
  let offsetX = 50;
  let offsetY = 50;
  let dragging = false;
  let startX = 0;
  let startY = 0;

  /* ===========================
     МАСШТАБУВАННЯ
     =========================== */
  wrapper.addEventListener("wheel", (e) => {
    e.preventDefault();
    const zoomSpeed = 0.08;
    scale += e.deltaY < 0 ? zoomSpeed : -zoomSpeed;
    scale = Math.max(0.3, Math.min(scale, 2.5));
    updateTransform();
  });

  /* Перетягування полотна */
  wrapper.addEventListener("mousedown", (e) => {
    dragging = true;
    startX = e.clientX;
    startY = e.clientY;
  });

  window.addEventListener("mouseup", () => (dragging = false));

  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    offsetX += e.clientX - startX;
    offsetY += e.clientY - startY;
    startX = e.clientX;
    startY = e.clientY;
    updateTransform();
  });

  function updateTransform() {
    canvas.style.transform = `translate(${offsetX}px, ${offsetY}px) scale(${scale})`;
  }

  /* Кнопки масштабування */
  document.getElementById("dm-zoom-in").onclick = () => {
    scale = Math.min(2.5, scale + 0.1);
    updateTransform();
  };

  document.getElementById("dm-zoom-out").onclick = () => {
    scale = Math.max(0.3, scale - 0.1);
    updateTransform();
  };

  document.getElementById("dm-zoom-reset").onclick = () => {
    scale = 1;
    updateTransform();
  };

  document.getElementById("dm-center").onclick = () => {
    offsetX = 50;
    offsetY = 50;
    scale = 1;
    updateTransform();
  };

  /* =================================================
     РЕНДЕР ДЕРЕВА — РЕКУРСИВНО
     ================================================= */

  let nodePositions = {}; // id → {x,y,width,height}

  function renderTree(root, x, y) {
    createNode(root, x, y);

    const children = root.children || [];
    const gapY = 150;
    const gapX = 250;

    let childX = x - ((children.length - 1) * gapX) / 2;

    children.forEach((child) => {
      renderTree(child, childX, y + gapY);
      drawArrow(root.id, child.id);
      childX += gapX;
    });
  }

  /* Створити вузол */
  function createNode(node, x, y) {
    const el = document.createElement("div");
    el.className = `dm-node dm-${node.status}`;
    el.style.left = x + "px";
    el.style.top = y + "px";
    el.textContent = node.label;
    el.dataset.id = node.id;

    canvas.appendChild(el);

    // Зберегти позицію
    nodePositions[node.id] = {
      x: x,
      y: y,
      width: el.offsetWidth,
      height: el.offsetHeight,
      node: node
    };

    // Клік → показати деталі
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      showDetails(node);
    });
  }

  /* Малювання стрілки */
  function drawArrow(fromId, toId) {
    const p1 = nodePositions[fromId];
    const p2 = nodePositions[toId];
    if (!p1 || !p2) return;

    const x1 = p1.x + p1.width / 2;
    const y1 = p1.y + p1.height;
    const x2 = p2.x + p2.width / 2;
    const y2 = p2.y;

    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.classList.add("dm-edge");

    svg.style.left = Math.min(x1, x2) + "px";
    svg.style.top = Math.min(y1, y2) + "px";
    svg.style.width = Math.abs(x2 - x1) + "px";
    svg.style.height = Math.abs(y2 - y1) + "px";

    const line = document.createElementNS(svgNS, "line");
    line.setAttribute("x1", x1 < x2 ? 0 : Math.abs(x1 - x2));
    line.setAttribute("y1", y1 < y2 ? 0 : Math.abs(y1 - y2));
    line.setAttribute("x2", x2 < x1 ? 0 : Math.abs(x2 - x1));
    line.setAttribute("y2", y2 < y1 ? 0 : Math.abs(y2 - y1));
    svg.appendChild(line);

    canvas.appendChild(svg);
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
  updateTransform();
})();
