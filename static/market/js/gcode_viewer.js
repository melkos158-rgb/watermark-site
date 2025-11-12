// static/js/gcode_viewer.js
// Простий, але потужний G-code viewer для Proofly STL Market.
// 2D-превʼю шарів, базові метрики, анімація друку.
//
// Використання в HTML (приклад):
// <canvas id="gcode-canvas"></canvas>
// <input type="file" id="gcode-file" accept=".gcode" />
// <input type="text" id="gcode-url" />
// <button id="gcode-load-url">Load</button>
// <input type="range" id="gcode-layer" min="0" max="0" value="0" />
// <span id="gcode-layer-label"></span>
// <div id="gcode-stats"></div>
// <button id="gcode-play">▶️</button>
// <button id="gcode-pause">⏸️</button>
// <button id="gcode-reset">⟲</button>
// <select id="gcode-color-mode">
//   <option value="byLayer">By layer</option>
//   <option value="bySpeed">By speed</option>
//   <option value="byExtrusion">By extrusion</option>
// </select>
//
// В JS:
// import { initGCodeViewer } from "/static/js/gcode_viewer.js";
// document.addEventListener("DOMContentLoaded", () => {
//   initGCodeViewer();
// });

export function initGCodeViewer({
  canvasId = "gcode-canvas",
  fileInputId = "gcode-file",
  urlInputId = "gcode-url",
  urlButtonId = "gcode-load-url",
  layerSliderId = "gcode-layer",
  layerLabelId = "gcode-layer-label",
  statsContainerId = "gcode-stats",
  playButtonId = "gcode-play",
  pauseButtonId = "gcode-pause",
  resetButtonId = "gcode-reset",
  colorModeSelectId = "gcode-color-mode",
  statusId = "gcode-status",
} = {}) {
  const $ = (id) => (id ? document.getElementById(id) : null);

  const canvas = $(canvasId);
  const fileInput = $(fileInputId);
  const urlInput = $(urlInputId);
  const urlButton = $(urlButtonId);
  const layerSlider = $(layerSliderId);
  const layerLabel = $(layerLabelId);
  const statsContainer = $(statsContainerId);
  const playBtn = $(playButtonId);
  const pauseBtn = $(pauseButtonId);
  const resetBtn = $(resetButtonId);
  const colorModeSelect = $(colorModeSelectId);
  const statusEl = $(statusId);

  if (!canvas) {
    console.error(`[GCODE] Canvas #${canvasId} not found`);
    return;
  }

  const ctx = canvas.getContext("2d");
  if (!ctx) {
    console.error("[GCODE] 2D context not available");
    return;
  }

  // ====== ВНУТРІШНІ СТАНИ ======

  let model = null; // {layers: [], bbox: {...}, stats:{...}}
  let currentLayerIndex = 0;

  // Анімація
  let animReq = null;
  let animPlaying = false;
  let animProgress = 0; // 0..1

  // Для адаптивного ресайзу
  function resizeCanvas() {
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }

  window.addEventListener("resize", resizeCanvas);
  resizeCanvas();

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text;
  }

  // ====== PARSER G-CODE ======

  /**
   * Дуже спрощений парсер G-code:
   * - підтримка G0/G1 з X/Y/Z/E/F
   * - абсолютні координати
   * - визначає "екструзію" по збільшенню E
   */
  class GCodeParser {
    constructor() {
      this.layers = []; // масив шарів: [{z, segments:[{x1,y1,x2,y2, e, f}]}]
      this.currentZ = 0;
      this.currentE = 0;
      this.currentF = 0;
      this.currentX = 0;
      this.currentY = 0;
      this.bbox = {
        minX: Infinity,
        minY: Infinity,
        maxX: -Infinity,
        maxY: -Infinity,
        minZ: Infinity,
        maxZ: -Infinity,
      };
    }

    parse(text) {
      const lines = text.split(/\r?\n/);
      for (let raw of lines) {
        const line = raw.split(";")[0].trim(); // обрізаємо коментар
        if (!line) continue;

        const parts = line.split(/\s+/);
        const cmd = parts[0].toUpperCase();

        if (cmd === "G0" || cmd === "G1") {
          this._handleMove(parts);
        }
        // Інші команди поки ігноруємо
      }

      // Перетворюємо map шарів на масив
      const layerArr = Object.values(
        this.layers.reduce((acc, layer) => {
          if (!acc[layer.index]) acc[layer.index] = layer;
          return acc;
        }, {})
      );

      // В нашій структурі зручно тримати їх як масив з полями {z, segments}
      const layersSorted = this.layers
        .filter((l) => l && l.segments && l.segments.length > 0)
        .sort((a, b) => a.z - b.z);

      return {
        layers: layersSorted,
        bbox: this.bbox,
      };
    }

    _getOrCreateLayer(z) {
      // шукаємо шар з таким Z
      let layer = this.layers.find((l) => l && Math.abs(l.z - z) < 0.0001);
      if (!layer) {
        layer = { z, segments: [] };
        this.layers.push(layer);
      }
      return layer;
    }

    _handleMove(parts) {
      let x = this.currentX;
      let y = this.currentY;
      let z = this.currentZ;
      let e = this.currentE;
      let f = this.currentF;

      for (let token of parts.slice(1)) {
        const code = token[0].toUpperCase();
        const valStr = token.slice(1);
        const val = parseFloat(valStr);
        if (isNaN(val)) continue;
        switch (code) {
          case "X":
            x = val;
            break;
          case "Y":
            y = val;
            break;
          case "Z":
            z = val;
            break;
          case "E":
            e = val;
            break;
          case "F":
            f = val;
            break;
        }
      }

      // якщо є реальне переміщення
      const moved =
        x !== this.currentX || y !== this.currentY || z !== this.currentZ;

      const extruding = e > this.currentE + 1e-6; // простий чекап

      if (moved && extruding) {
        const layer = this._getOrCreateLayer(z);
        layer.segments.push({
          x1: this.currentX,
          y1: this.currentY,
          x2: x,
          y2: y,
          z,
          e,
          f,
          de: e - this.currentE,
        });

        // оновлення bbox
        this._expandBBox(x, y, z);
        this._expandBBox(this.currentX, this.currentY, this.currentZ);
      }

      this.currentX = x;
      this.currentY = y;
      this.currentZ = z;
      this.currentE = e;
      this.currentF = f;
    }

    _expandBBox(x, y, z) {
      if (x < this.bbox.minX) this.bbox.minX = x;
      if (y < this.bbox.minY) this.bbox.minY = y;
      if (z < this.bbox.minZ) this.bbox.minZ = z;
      if (x > this.bbox.maxX) this.bbox.maxX = x;
      if (y > this.bbox.maxY) this.bbox.maxY = y;
      if (z > this.bbox.maxZ) this.bbox.maxZ = z;
    }
  }

  // ====== РЕНДЕРЕР ======

  function calcStats(parsed) {
    let segmentsCount = 0;
    let totalLength = 0;
    let totalExtrusion = 0;
    let minF = Infinity;
    let maxF = 0;

    for (const layer of parsed.layers) {
      for (const seg of layer.segments) {
        segmentsCount++;
        const dx = seg.x2 - seg.x1;
        const dy = seg.y2 - seg.y1;
        const len = Math.sqrt(dx * dx + dy * dy);
        totalLength += len;
        totalExtrusion += seg.de || 0;
        if (seg.f > 0) {
          if (seg.f < minF) minF = seg.f;
          if (seg.f > maxF) maxF = seg.f;
        }
      }
    }

    if (!isFinite(minF)) minF = 0;

    return {
      layersCount: parsed.layers.length,
      segmentsCount,
      totalLength, // mm
      totalExtrusion,
      minF,
      maxF,
    };
  }

  function updateStats(stats) {
    if (!statsContainer) return;
    if (!stats) {
      statsContainer.innerHTML =
        '<span style="opacity:.7">Завантаж G-code, щоб побачити статистику.</span>';
      return;
    }

    const lengthMm = stats.totalLength.toFixed(1);
    const extrusionMm3 = stats.totalExtrusion.toFixed(2);
    const layers = stats.layersCount;
    const segs = stats.segmentsCount;

    statsContainer.innerHTML = `
      <div class="gcode-stats-grid">
        <div><strong>Шарів:</strong> ${layers}</div>
        <div><strong>Сегментів:</strong> ${segs}</div>
        <div><strong>Загальна довжина траєкторій:</strong> ${lengthMm} мм</div>
        <div><strong>Сумарна екструзія (умовно):</strong> ${extrusionMm3}</div>
        <div><strong>Швидкість (мін/макс):</strong> ${stats.minF} / ${
      stats.maxF
    } mm/хв</div>
      </div>
    `;
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();

    if (!model || !model.layers || model.layers.length === 0) {
      // напис "No G-code loaded"
      ctx.fillStyle = "#64748b";
      ctx.font = "14px system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("Завантаж G-code, щоб побачити превʼю", canvas.width / 2, canvas.height / 2);
      ctx.restore();
      return;
    }

    const colorMode = colorModeSelect ? colorModeSelect.value : "byLayer";

    const { bbox } = model;
    const w = bbox.maxX - bbox.minX;
    const h = bbox.maxY - bbox.minY;

    // Мінімальні відступи
    const padding = 20;
    const viewW = canvas.width - padding * 2;
    const viewH = canvas.height - padding * 2;

    const scale = Math.min(
      viewW / (w || 1),
      viewH / (h || 1)
    );

    // Центруємо
    const offsetX = padding + viewW / 2;
    const offsetY = padding + viewH / 2;

    function worldToScreenX(x) {
      return offsetX + (x - (bbox.minX + w / 2)) * scale;
    }

    // У G-code Y зліва-направо, але ми можемо інвертувати, щоб виглядало "як на столі"
    function worldToScreenY(y) {
      return offsetY - (y - (bbox.minY + h / 2)) * scale;
    }

    // Для анімації: скільки сегментів показуємо (0..1)
    let maxSegments = Infinity;
    if (animPlaying) {
      const totalSegs = model.totalSegments || 1;
      maxSegments = Math.floor(totalSegs * animProgress);
    }

    let segCounter = 0;

    // Малюємо всі шари до поточного, але поточний — яскравіший
    const maxLayerIndex = currentLayerIndex;

    for (let li = 0; li < model.layers.length; li++) {
      const layer = model.layers[li];
      const isCurrent = li === maxLayerIndex;

      for (const seg of layer.segments) {
        segCounter++;
        if (segCounter > maxSegments) break;

        const x1 = worldToScreenX(seg.x1);
        const y1 = worldToScreenY(seg.y1);
        const x2 = worldToScreenX(seg.x2);
        const y2 = worldToScreenY(seg.y2);

        const width = isCurrent ? 1.8 : 1;
        let strokeStyle = "#475569"; // дефолтно – сіренький

        if (colorMode === "byLayer") {
          // простий градієнт від синього до рожевого
          const t = li / Math.max(model.layers.length - 1, 1);
          strokeStyle = layerColor(t, isCurrent);
        } else if (colorMode === "bySpeed") {
          strokeStyle = speedColor(seg.f || 0, model.stats.minF, model.stats.maxF, isCurrent);
        } else if (colorMode === "byExtrusion") {
          strokeStyle = extrusionColor(seg.de || 0, model.stats.maxDe, isCurrent);
        }

        ctx.lineWidth = width;
        ctx.strokeStyle = strokeStyle;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }
      if (segCounter > maxSegments) break;
    }

    ctx.restore();
  }

  function layerColor(t, current) {
    // t: 0..1
    const s = current ? 80 : 55;
    const l = current ? 60 : 45;
    const hue = 210 + t * 110; // від синього до рожевого
    return `hsl(${hue}, ${s}%, ${l}%)`;
  }

  function speedColor(f, minF, maxF, current) {
    if (maxF <= minF) {
      return current ? "#22c55e" : "#16a34a";
    }
    const t = (f - minF) / (maxF - minF + 1e-6);
    const hue = 120 + (1 - t) * 60; // повільно – зелений, швидко – жовто-оранжевий
    const s = current ? 80 : 65;
    const l = current ? 55 : 45;
    return `hsl(${hue}, ${s}%, ${l}%)`;
  }

  function extrusionColor(de, maxDe, current) {
    if (maxDe <= 0) return current ? "#38bdf8" : "#0ea5e9";
    const t = Math.min(de / maxDe, 1);
    const hue = 200 - t * 80; // чим більше екструзія, тим тепліший колір
    const s = current ? 85 : 70;
    const l = current ? 55 : 45;
    return `hsl(${hue}, ${s}%, ${l}%)`;
  }

  // ====== ЛОАДЕРИ ======

  async function loadFromFile(file) {
    if (!file) return;
    setStatus("Читання G-code з файлу…");
    const text = await file.text();
    handleGCodeLoaded(text);
    setStatus(`G-code завантажено з файлу: ${file.name}`);
  }

  async function loadFromUrl(url) {
    if (!url) return;
    setStatus("Завантаження G-code з URL…");
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const text = await res.text();
      handleGCodeLoaded(text);
      setStatus(`G-code завантажено з ${url}`);
    } catch (e) {
      console.error(e);
      setStatus("Помилка завантаження G-code з URL");
    }
  }

  function handleGCodeLoaded(text) {
    const parser = new GCodeParser();
    const parsed = parser.parse(text);

    const stats = calcStats(parsed);
    // шукаємо максимальне de (для колірної шкали)
    let maxDe = 0;
    for (const layer of parsed.layers) {
      for (const s of layer.segments) {
        if ((s.de || 0) > maxDe) maxDe = s.de;
      }
    }

    let totalSegments = 0;
    for (const layer of parsed.layers) {
      totalSegments += layer.segments.length;
    }

    model = {
      layers: parsed.layers,
      bbox: parsed.bbox,
      stats: { ...stats, maxDe },
      totalSegments,
    };

    currentLayerIndex = model.layers.length - 1;
    animProgress = 1;
    animPlaying = false;

    // оновлюємо UI
    if (layerSlider) {
      layerSlider.min = "0";
      layerSlider.max = Math.max(model.layers.length - 1, 0).toString();
      layerSlider.value = currentLayerIndex.toString();
    }
    updateLayerLabel();
    updateStats(model.stats);
    draw();
  }

  function updateLayerLabel() {
    if (!layerLabel) return;
    if (!model) {
      layerLabel.textContent = "- / -";
    } else {
      const total = model.layers.length;
      const z = total ? model.layers[currentLayerIndex].z.toFixed(2) : "-";
      layerLabel.textContent = `${currentLayerIndex + 1} / ${total} (Z = ${z} мм)`;
    }
  }

  // ====== АНІМАЦІЯ ======

  function startAnimation() {
    if (!model) return;
    animPlaying = true;
    if (!animReq) {
      lastTimestamp = null;
      animReq = requestAnimationFrame(tick);
    }
  }

  function pauseAnimation() {
    animPlaying = false;
  }

  function resetAnimation() {
    animPlaying = false;
    animProgress = 0;
    draw();
  }

  let lastTimestamp = null;

  function tick(timestamp) {
    animReq = requestAnimationFrame(tick);

    if (!animPlaying) {
      lastTimestamp = timestamp;
      return;
    }

    if (!lastTimestamp) lastTimestamp = timestamp;
    const dt = (timestamp - lastTimestamp) / 1000; // sec
    lastTimestamp = timestamp;

    // 7 секунд на повний прохід (можна покрутити)
    const speed = 1 / 7;
    animProgress += dt * speed;
    if (animProgress > 1) {
      animProgress = 1;
      animPlaying = false;
    }
    draw();
  }

  animReq = requestAnimationFrame(tick);

  // ====== ПОДІЇ UI ======

  if (fileInput) {
    fileInput.addEventListener("change", (e) => {
      const file = e.target.files && e.target.files[0];
      if (file) loadFromFile(file);
    });
  }

  if (urlButton && urlInput) {
    urlButton.addEventListener("click", () => {
      const url = urlInput.value.trim();
      if (url) loadFromUrl(url);
    });
  }

  if (layerSlider) {
    layerSlider.addEventListener("input", () => {
      if (!model) return;
      const idx = Math.max(
        0,
        Math.min(parseInt(layerSlider.value, 10) || 0, model.layers.length - 1)
      );
      currentLayerIndex = idx;
      updateLayerLabel();
      draw();
    });
  }

  if (colorModeSelect) {
    colorModeSelect.addEventListener("change", () => {
      draw();
    });
  }

  if (playBtn) {
    playBtn.addEventListener("click", () => {
      if (!model) return;
      if (animProgress >= 1) animProgress = 0;
      startAnimation();
    });
  }

  if (pauseBtn) {
    pauseBtn.addEventListener("click", () => {
      pauseAnimation();
    });
  }

  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      resetAnimation();
    });
  }

  // Початковий стан
  setStatus("G-code viewer готовий. Завантаж файл або встав URL.");
  updateStats(null);
  draw();

  // Повертаємо невеликий API (раптом захочеш юзати з інших скриптів)
  return {
    loadFromFile,
    loadFromUrl,
    redraw: draw,
    getModel: () => model,
  };
}
