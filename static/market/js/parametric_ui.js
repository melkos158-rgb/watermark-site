// static/market/js/parametric_ui.js
// UI для параметричних STL моделей

(function () {
  const presetsConfig = {
    box: {
      label: "Універсальний бокс",
      fields: [
        {
          name: "width",
          label: "Ширина (мм)",
          type: "number",
          min: 10,
          max: 300,
          step: 1,
          default: 60
        },
        {
          name: "depth",
          label: "Глибина (мм)",
          type: "number",
          min: 10,
          max: 300,
          step: 1,
          default: 80
        },
        {
          name: "height",
          label: "Висота (мм)",
          type: "number",
          min: 10,
          max: 300,
          step: 1,
          default: 40
        },
        {
          name: "wall_thickness",
          label: "Товщина стінки (мм)",
          type: "number",
          min: 0.8,
          max: 5,
          step: 0.2,
          default: 2
        },
        {
          name: "bottom_thickness",
          label: "Товщина дна (мм)",
          type: "number",
          min: 0.8,
          max: 5,
          step: 0.2,
          default: 2
        }
      ]
    },
    stand: {
      label: "Підставка для телефону",
      fields: [
        {
          name: "phone_width",
          label: "Ширина телефону (мм)",
          type: "number",
          min: 50,
          max: 90,
          step: 1,
          default: 75
        },
        {
          name: "thickness",
          label: "Товщина телефону (мм)",
          type: "number",
          min: 6,
          max: 15,
          step: 0.5,
          default: 10
        },
        {
          name: "tilt_angle",
          label: "Кут нахилу (°)",
          type: "number",
          min: 30,
          max: 80,
          step: 1,
          default: 60
        },
        {
          name: "base_depth",
          label: "Глибина бази (мм)",
          type: "number",
          min: 40,
          max: 120,
          step: 1,
          default: 70
        }
      ]
    },
    tag: {
      label: "Бірка/брелок з текстом",
      fields: [
        {
          name: "text",
          label: "Текст",
          type: "text",
          maxLength: 20,
          default: "PROOFLY"
        },
        {
          name: "width",
          label: "Ширина (мм)",
          type: "number",
          min: 20,
          max: 100,
          step: 1,
          default: 50
        },
        {
          name: "height",
          label: "Висота (мм)",
          type: "number",
          min: 10,
          max: 50,
          step: 1,
          default: 20
        },
        {
          name: "hole_diameter",
          label: "Діаметр отвору (мм)",
          type: "number",
          min: 2,
          max: 10,
          step: 0.5,
          default: 4
        },
        {
          name: "text_depth",
          label: "Глибина тиснення тексту (мм)",
          type: "number",
          min: 0.3,
          max: 2,
          step: 0.1,
          default: 0.8
        }
      ]
    }
  };

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function qsa(sel, root) {
    return Array.from((root || document).querySelectorAll(sel));
  }

  const presetsContainer = qs("#parametric-presets");
  const fieldsContainer = qs("#parametric-fields");
  const presetKeyInput = qs("#parametric-preset-key");
  const generateBtn = qs("#parametric-generate");
  const statusEl = qs("#parametric-status");
  const resultEl = qs("#parametric-result");
  const formEl = qs("#parametric-form");

  if (!presetsContainer || !fieldsContainer || !generateBtn || !formEl) {
    // Не на цій сторінці — тихо виходимо
    return;
  }

  function setStatus(text, isError) {
    if (!statusEl) return;
    statusEl.textContent = text || "";
    statusEl.style.color = isError ? "#ff6b6b" : "#9fb0d4";
  }

  function clearResult() {
    if (resultEl) {
      resultEl.innerHTML = "";
    }
  }

  function renderFields(presetKey) {
    const cfg = presetsConfig[presetKey];
    if (!cfg) {
      fieldsContainer.innerHTML =
        '<p class="muted">Невідомий шаблон. Обери інший.</p>';
      return;
    }

    presetKeyInput.value = presetKey;
    generateBtn.disabled = false;

    const fragments = [];

    cfg.fields.forEach((field) => {
      const id = `parametric-${presetKey}-${field.name}`;

      let inputHtml = "";
      if (field.type === "text") {
        inputHtml = `
          <input
            id="${id}"
            name="${field.name}"
            type="text"
            class="inp"
            ${field.maxLength ? `maxlength="${field.maxLength}"` : ""}
            value="${field.default != null ? String(field.default) : ""}"
          >
        `;
      } else {
        inputHtml = `
          <input
            id="${id}"
            name="${field.name}"
            type="number"
            class="inp"
            ${field.min != null ? `min="${field.min}"` : ""}
            ${field.max != null ? `max="${field.max}"` : ""}
            ${field.step != null ? `step="${field.step}"` : "step=\"any\""}
            value="${field.default != null ? String(field.default) : ""}"
          >
        `;
      }

      fragments.push(`
        <div class="field">
          <label for="${id}">${field.label}</label>
          ${inputHtml}
        </div>
      `);
    });

    fieldsContainer.innerHTML = fragments.join("");
  }

  function onPresetClick(e) {
    const btn = e.target.closest(".preset-card");
    if (!btn) return;

    const key = btn.getAttribute("data-preset-key");
    if (!key || !presetsConfig[key]) return;

    // Візуально активний
    qsa(".preset-card", presetsContainer).forEach((b) =>
      b.classList.toggle("active", b === btn)
    );

    clearResult();
    setStatus("", false);
    renderFields(key);
  }

  async function onGenerateClick() {
    const presetKey = presetKeyInput.value;
    if (!presetKey || !presetsConfig[presetKey]) {
      setStatus("Спочатку обери шаблон", true);
      return;
    }

    const cfg = presetsConfig[presetKey];
    const payload = {
      preset_key: presetKey,
      params: {}
    };

    // Зчитуємо поля
    let invalid = false;
    cfg.fields.forEach((field) => {
      const el = formEl.elements[field.name];
      if (!el) return;

      let val = el.value;
      if (field.type === "number") {
        const num = Number(val);
        if (Number.isNaN(num)) {
          invalid = true;
          el.classList.add("error");
          return;
        }
        el.classList.remove("error");
        payload.params[field.name] = num;
      } else {
        val = String(val || "").trim();
        if (!val && field.required) {
          invalid = true;
          el.classList.add("error");
          return;
        }
        el.classList.remove("error");
        payload.params[field.name] = val;
      }
    });

    if (invalid) {
      setStatus("Перевір правильність параметрів", true);
      return;
    }

    setStatus("Генеруємо STL… ⏳", false);
    clearResult();
    generateBtn.disabled = true;

    try {
      const res = await fetch("/api/market/parametric/generate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        throw new Error("Bad status " + res.status);
      }

      const data = await res.json();
      const url = data.stl_url || data.url;
      const info = data.info || "";
      const previewNote = data.preview_note || "";
      const volume = data.volume_cm3;
      const size = data.size_mm;

      if (!url) {
        setStatus("Бек не повернув посилання на STL 😢", true);
        return;
      }

      let html = `
        <div class="parametric-result-box">
          <h3>STL згенеровано ✔</h3>
          <p>
            <a href="${url}" class="btn primary" download>
              Завантажити STL
            </a>
          </p>
      `;

      if (info) {
        html += `<p class="muted small">${info}</p>`;
      }

      if (volume != null || size != null) {
        html += `<ul class="muted small">`;
        if (volume != null) {
          html += `<li>Об'єм: ${volume.toFixed ? volume.toFixed(1) : volume} см³</li>`;
        }
        if (Array.isArray(size) && size.length === 3) {
          html += `<li>Габарити: ${size[0].toFixed ? size[0].toFixed(1) : size[0]} × ${
            size[1].toFixed ? size[1].toFixed(1) : size[1]
          } × ${size[2].toFixed ? size[2].toFixed(1) : size[2]} мм</li>`;
        }
        html += `</ul>`;
      }

      if (previewNote) {
        html += `<p class="muted small">${previewNote}</p>`;
      }

      html += `</div>`;

      resultEl.innerHTML = html;
      setStatus("Готово ✔", false);
    } catch (err) {
      console.error("parametric: generate error", err);
      setStatus("Помилка генерації STL 😢", true);
    } finally {
      generateBtn.disabled = false;
    }
  }

  function init() {
    presetsContainer.addEventListener("click", onPresetClick);
    generateBtn.addEventListener("click", onGenerateClick);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
