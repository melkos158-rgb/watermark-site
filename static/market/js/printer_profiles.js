// static/js/printer_profiles.js
// Керування профілями принтерів для Proofly STL Market.
// Працює разом із printer_profiles.html та backend'ом printer_profiles.py.
//
// Очікувані API (ми їх реалізуємо у printer_profiles.py):
//   GET    /api/printers                 -> { ok, items:[...] }
//   POST   /api/printers                 -> { ok, item }
//   PUT    /api/printers/<id>            -> { ok, item }
//   DELETE /api/printers/<id>            -> { ok:true }
//   GET    /api/printers/active          -> { ok, item: {...} | null }
//   POST   /api/printers/<id>/activate   -> { ok, item }
//
// Формат елемента:
//   {
//     id, name, model, type, firmware,
//     bed_x, bed_y, bed_z,
//     filament_diameter, nozzle_diameter,
//     temp_nozzle, temp_bed,
//     max_print_speed, max_travel_speed,
//     materials, notes,
//     is_active
//   }

export function initPrinterProfiles({
  listId = "pp-list",
  listEmptyId = "pp-list-empty",
  searchId = "pp-search",
  filterTypeId = "pp-filter-type",
  btnNewId = "pp-btn-new",
  formId = "pp-form",
  statusId = "pp-status",
  activeContainerId = "pp-active",
  compatContainerId = "pp-compat",
  presetsContainerId = "pp-presets",
} = {}) {
  const $ = (id) => (id ? document.getElementById(id) : null);

  const listEl = $(listId);
  const listEmptyEl = $(listEmptyId);
  const searchEl = $(searchId);
  const filterTypeEl = $(filterTypeId);
  const btnNew = $(btnNewId);
  const form = $(formId);
  const statusEl = $(statusId);
  const activeEl = $(activeContainerId);
  const compatEl = $(compatContainerId);
  const presetsEl = $(presetsContainerId);

  if (!listEl || !form) {
    console.error("[PrinterProfiles] Не знайдено list або form елементи.");
    return;
  }

  // Поля форми
  const field = (id) => document.getElementById(id);
  const fId = field("pp-id");
  const fName = field("pp-name");
  const fModel = field("pp-model");
  const fType = field("pp-type");
  const fFirmware = field("pp-firmware");
  const fBedX = field("pp-bed-x");
  const fBedY = field("pp-bed-y");
  const fBedZ = field("pp-bed-z");
  const fFilamentDia = field("pp-filament-dia");
  const fNozzleDia = field("pp-nozzle-dia");
  const fTempNozzle = field("pp-temp-nozzle");
  const fTempBed = field("pp-temp-bed");
  const fMaxPrintSpeed = field("pp-max-print-speed");
  const fMaxTravelSpeed = field("pp-max-travel-speed");
  const fMaterials = field("pp-materials");
  const fNotes = field("pp-notes");

  const btnSave = field("pp-btn-save");
  const btnDuplicate = field("pp-btn-duplicate");
  const btnDelete = field("pp-btn-delete");
  const formTitleEl = document.getElementById("pp-form-title");

  // СТАН
  let allProfiles = [];
  let activeId = null;
  let currentSelectedId = null;
  let isLoading = false;

  // Пресети (front-only, без бекенда)
  const PRESETS = [
    {
      key: "bambu_a1",
      label: "Bambu Lab A1 mini",
      name: "Bambu A1 mini",
      model: "Bambu Lab A1 mini",
      type: "bambu",
      firmware: "Bambu OS",
      bed_x: 180,
      bed_y: 180,
      bed_z: 180,
      filament_diameter: 1.75,
      nozzle_diameter: 0.4,
      temp_nozzle: 215,
      temp_bed: 60,
      max_print_speed: 500,
      max_travel_speed: 1000,
      materials: "PLA, PETG, TPU",
      notes: "AMS (опціонально), автоматичне калібрування, закрита камера.",
    },
    {
      key: "ender3_v2",
      label: "Creality Ender-3 V2",
      name: "Ender-3 V2",
      model: "Creality Ender-3 V2",
      type: "cartesian",
      firmware: "Marlin",
      bed_x: 220,
      bed_y: 220,
      bed_z: 250,
      filament_diameter: 1.75,
      nozzle_diameter: 0.4,
      temp_nozzle: 200,
      temp_bed: 60,
      max_print_speed: 120,
      max_travel_speed: 250,
      materials: "PLA, PETG",
      notes: "Бюджетний хіт, потребує тюнінгу; можна докрутити direct drive та auto bed level.",
    },
    {
      key: "prusa_mk4",
      label: "Prusa MK4",
      name: "Prusa MK4",
      model: "Original Prusa MK4",
      type: "cartesian",
      firmware: "Prusa Firmware",
      bed_x: 250,
      bed_y: 210,
      bed_z: 220,
      filament_diameter: 1.75,
      nozzle_diameter: 0.4,
      temp_nozzle: 215,
      temp_bed: 60,
      max_print_speed: 200,
      max_travel_speed: 300,
      materials: "PLA, PETG, ASA, Flex",
      notes: "Надійна робоча конячка, авто bed level, швидкий друк.",
    },
  ];

  // ======== УТИЛІТИ ========

  function setStatus(msg, kind = "info") {
    if (!statusEl) return;
    const color =
      kind === "error"
        ? "#f97373"
        : kind === "success"
        ? "#4ade80"
        : "#e5e7eb";
    statusEl.textContent = msg || "";
    statusEl.style.color = color;
  }

  function apiFetch(url, options = {}) {
    const opts = {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      credentials: "same-origin",
      ...options,
    };
    return fetch(url, opts).then(async (res) => {
      let data;
      try {
        data = await res.json();
      } catch (e) {
        throw new Error("Invalid JSON from server");
      }
      if (!res.ok || data.ok === false) {
        const msg = (data && data.error) || `HTTP ${res.status}`;
        throw new Error(msg);
      }
      return data;
    });
  }

  function toNumber(val) {
    if (val === "" || val === null || typeof val === "undefined") return null;
    const n = Number(val);
    return Number.isFinite(n) ? n : null;
  }

  function escapeHtml(str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ======== РОБОТА З ФОРМОЮ ========

  function clearForm() {
    if (formTitleEl) formTitleEl.textContent = "Параметри профілю";
    fId.value = "";
    fName.value = "";
    fModel.value = "";
    fType.value = "";
    fFirmware.value = "";
    fBedX.value = "";
    fBedY.value = "";
    fBedZ.value = "";
    fFilamentDia.value = "";
    fNozzleDia.value = "";
    fTempNozzle.value = "";
    fTempBed.value = "";
    fMaxPrintSpeed.value = "";
    fMaxTravelSpeed.value = "";
    fMaterials.value = "";
    fNotes.value = "";
    currentSelectedId = null;
    updateActivePanel();
    updateCompatPanel();
  }

  function fillForm(profile) {
    if (!profile) return;
    if (formTitleEl) {
      formTitleEl.textContent = `Редагування: ${profile.name || "профіль"}`;
    }
    fId.value = profile.id || "";
    fName.value = profile.name || "";
    fModel.value = profile.model || "";
    fType.value = profile.type || "";
    fFirmware.value = profile.firmware || "";
    fBedX.value = profile.bed_x ?? "";
    fBedY.value = profile.bed_y ?? "";
    fBedZ.value = profile.bed_z ?? "";
    fFilamentDia.value = profile.filament_diameter ?? "";
    fNozzleDia.value = profile.nozzle_diameter ?? "";
    fTempNozzle.value = profile.temp_nozzle ?? "";
    fTempBed.value = profile.temp_bed ?? "";
    fMaxPrintSpeed.value = profile.max_print_speed ?? "";
    fMaxTravelSpeed.value = profile.max_travel_speed ?? "";
    fMaterials.value = profile.materials || "";
    fNotes.value = profile.notes || "";
  }

  function formToProfile() {
    return {
      id: fId.value || null,
      name: fName.value.trim(),
      model: fModel.value.trim(),
      type: fType.value || "",
      firmware: fFirmware.value.trim(),
      bed_x: toNumber(fBedX.value),
      bed_y: toNumber(fBedY.value),
      bed_z: toNumber(fBedZ.value),
      filament_diameter: toNumber(fFilamentDia.value),
      nozzle_diameter: toNumber(fNozzleDia.value),
      temp_nozzle: toNumber(fTempNozzle.value),
      temp_bed: toNumber(fTempBed.value),
      max_print_speed: toNumber(fMaxPrintSpeed.value),
      max_travel_speed: toNumber(fMaxTravelSpeed.value),
      materials: fMaterials.value.trim(),
      notes: fNotes.value.trim(),
    };
  }

  // ======== РЕНДЕР СПИСКУ ========

  function renderList() {
    const q = (searchEl && searchEl.value.trim().toLowerCase()) || "";
    const typeFilter = filterTypeEl && filterTypeEl.value ? filterTypeEl.value : "";

    const filtered = allProfiles.filter((p) => {
      const hay = (
        (p.name || "") +
        " " +
        (p.model || "") +
        " " +
        (p.materials || "") +
        " " +
        (p.type || "")
      ).toLowerCase();
      if (q && !hay.includes(q)) return false;
      if (typeFilter && p.type !== typeFilter) return false;
      return true;
    });

    listEl.innerHTML = "";
    if (filtered.length === 0) {
      if (listEmptyEl) listEmptyEl.style.display = "block";
      return;
    }
    if (listEmptyEl) listEmptyEl.style.display = "none";

    for (const p of filtered) {
      const item = document.createElement("div");
      item.className = "pp-item";
      if (p.id === activeId) {
        item.classList.add("active");
      }

      const matShort = (p.materials || "")
        .split(",")
        .map((m) => m.trim())
        .filter(Boolean)
        .slice(0, 3)
        .join(", ");

      const size =
        p.bed_x && p.bed_y && p.bed_z
          ? `${p.bed_x}×${p.bed_y}×${p.bed_z} мм`
          : "—";

      const typeLabel =
        p.type === "corexy"
          ? "CoreXY"
          : p.type === "cartesian"
          ? "Cartesian"
          : p.type === "delta"
          ? "Delta"
          : p.type === "bambu"
          ? "Bambu / закритий"
          : p.type === "resin"
          ? "Resin"
          : "—";

      item.innerHTML = `
        <div>
          <div class="pp-item-name">${escapeHtml(p.name || "(без назви)")}</div>
          <div class="pp-item-meta">
            ${escapeHtml(p.model || "")}
            ${typeLabel !== "—" ? " · " + escapeHtml(typeLabel) : ""}
          </div>
        </div>
        <div class="pp-item-tags">
          <span class="pp-tag-pill">📏 ${escapeHtml(size)}</span>
          ${
            matShort
              ? `<span class="pp-tag-pill">🧵 ${escapeHtml(matShort)}</span>`
              : ""
          }
        </div>
        <div class="pp-item-actions">
          ${
            p.id === activeId
              ? '<span style="font-size:11px;opacity:.9;">Активний</span>'
              : '<button type="button" class="pp-btn secondary pp-btn-set-active" data-id="' +
                String(p.id) +
                '">Зробити активним</button>'
          }
        </div>
      `;

      item.addEventListener("click", (ev) => {
        // якщо натиснули на кнопку "Зробити активним", обробимо окремо
        const target = ev.target;
        if (
          target &&
          target.classList &&
          target.classList.contains("pp-btn-set-active")
        ) {
          const pid = target.getAttribute("data-id");
          if (pid) {
            setActive(pid);
          }
          ev.stopPropagation();
          return;
        }

        currentSelectedId = p.id;
        fillForm(p);
        updateActivePanel(); // покажемо в правій панелі як вибраний/активний
        updateCompatPanel();
        renderList(); // щоб підсвітити active і обраний
      });

      listEl.appendChild(item);
    }
  }

  // ======== АКТИВНИЙ ПРОФІЛЬ / СУМІСНІСТЬ ========

  function findProfileById(id) {
    if (!id) return null;
    return allProfiles.find((p) => String(p.id) === String(id)) || null;
  }

  function updateActivePanel() {
    if (!activeEl) return;

    const profile = findProfileById(activeId) || findProfileById(currentSelectedId);
    if (!profile) {
      activeEl.innerHTML =
        '<div style="opacity:.7;font-size:13px;">Ще нічого не обрано. Клікни на профіль у списку або створюй новий.</div>';
      return;
    }

    const size =
      profile.bed_x && profile.bed_y && profile.bed_z
        ? `${profile.bed_x} × ${profile.bed_y} × ${profile.bed_z} мм`
        : "—";

    const nozzle = profile.nozzle_diameter ? `${profile.nozzle_diameter} мм` : "—";
    const filament = profile.filament_diameter
      ? `${profile.filament_diameter} мм`
      : "1.75 мм (типово)";
    const materials = (profile.materials || "")
      .split(",")
      .map((m) => m.trim())
      .filter(Boolean);

    const isActive = profile.id === activeId;

    activeEl.innerHTML = `
      <div style="font-size:15px;font-weight:600;margin-bottom:2px;">
        ${escapeHtml(profile.name || "(без назви)")}${
      isActive ? ' <span style="font-size:11px;color:#4ade80;">(активний)</span>' : ""
    }
      </div>
      <div style="font-size:12px;opacity:.8;margin-bottom:8px;">
        ${escapeHtml(profile.model || "")}
        ${
          profile.type
            ? " · " +
              escapeHtml(
                profile.type === "corexy"
                  ? "CoreXY"
                  : profile.type === "cartesian"
                  ? "Cartesian"
                  : profile.type === "delta"
                  ? "Delta"
                  : profile.type === "bambu"
                  ? "Bambu / закритий"
                  : profile.type === "resin"
                  ? "Resin"
                  : profile.type
              )
            : ""
        }
      </div>
      <div class="pp-compat">
        <span><strong>Стіл:</strong> ${escapeHtml(size)}</span>
        <span><strong>Філамент:</strong> ${escapeHtml(filament)}</span>
        <span><strong>Сопло:</strong> ${escapeHtml(nozzle)}</span>
      </div>
      ${
        materials.length
          ? `<div style="margin-top:8px;font-size:12px;">
                <strong>Матеріали:</strong>
                ${materials
                  .map(
                    (m) =>
                      `<span class="pp-tag-pill" style="margin-right:4px;">${escapeHtml(
                        m
                      )}</span>`
                  )
                  .join("")}
             </div>`
          : ""
      }
      <div style="margin-top:10px;">
        ${
          isActive
            ? '<span style="font-size:12px;opacity:.8;">Цей профіль вже активний.</span>'
            : `<button type="button" class="pp-btn secondary" id="pp-btn-make-active">Зробити активним</button>`
        }
      </div>
    `;

    // Повісимо handler на кнопку "Зробити активним" у правій панелі, якщо є
    const btnMakeActive = document.getElementById("pp-btn-make-active");
    if (btnMakeActive) {
      btnMakeActive.addEventListener("click", () => {
        if (profile.id) setActive(profile.id);
      });
    }
  }

  function updateCompatPanel() {
    if (!compatEl) return;
    const profile = findProfileById(activeId) || findProfileById(currentSelectedId);
    if (!profile) {
      compatEl.innerHTML = "";
      return;
    }

    const sizeOk =
      profile.bed_x && profile.bed_y && profile.bed_z
        ? profile.bed_x >= 150 && profile.bed_y >= 150 && profile.bed_z >= 150
        : null;
    const fastPrinter =
      profile.max_print_speed && profile.max_print_speed >= 250 ? true : false;
    const flexibleReady =
      (profile.materials || "").toLowerCase().includes("tpu") ||
      (profile.materials || "").toLowerCase().includes("flex");

    const hints = [];

    if (sizeOk === true) {
      hints.push("⚡ Підійде для більшості фігурок, масок та functional parts.");
    } else if (sizeOk === false) {
      hints.push(
        "⚠ Невеликий робочий обʼєм — уважно дивись на габарити STL перед друком."
      );
    }

    if (fastPrinter) {
      hints.push("🚀 Принтер розрахований на високі швидкості — ідеально під серійний друк.");
    }

    if (flexibleReady) {
      hints.push("🧵 Підтримує гнучкі матеріали (TPU / Flex) — можна продавати сумісні моделі.");
    }

    if (hints.length === 0) {
      hints.push("ℹ Зберігай профіль — надалі ми додамо глибшу аналітику сумісності з STL.");
    }

    compatEl.innerHTML = hints
      .map((h) => `<div style="font-size:12px;opacity:.9;">${escapeHtml(h)}</div>`)
      .join("");
  }

  // ======== API: ЗАВАНТАЖЕННЯ / ЗБЕРЕЖЕННЯ ========

  function loadAll() {
    isLoading = true;
    setStatus("Завантаження профілів принтерів…");
    return apiFetch("/api/printers")
      .then((data) => {
        allProfiles = data.items || [];
        activeId =
          (allProfiles.find((p) => p.is_active) || {}).id || null;
        renderList();
        updateActivePanel();
        updateCompatPanel();
        if (!allProfiles.length) {
          setStatus("Додай свій перший профіль принтера.");
        } else {
          setStatus(`Завантажено профілів: ${allProfiles.length}`, "success");
        }
      })
      .catch((err) => {
        console.error(err);
        setStatus(`Помилка завантаження: ${err.message}`, "error");
      })
      .finally(() => {
        isLoading = false;
      });
  }

  function saveProfile() {
    if (isLoading) return;
    const p = formToProfile();

    if (!p.name) {
      setStatus("Вкажи назву профілю.", "error");
      fName.focus();
      return;
    }

    const hasId = !!p.id;
    const url = hasId ? `/api/printers/${encodeURIComponent(p.id)}` : "/api/printers";
    const method = hasId ? "PUT" : "POST";

    isLoading = true;
    setStatus(hasId ? "Оновлення профілю…" : "Створення нового профілю…");

    apiFetch(url, {
      method,
      body: JSON.stringify(p),
    })
      .then((data) => {
        const saved = data.item;
        if (!saved) throw new Error("Порожня відповідь від серверу.");

        // або оновлюємо в масиві, або додаємо
        const idx = allProfiles.findIndex((x) => String(x.id) === String(saved.id));
        if (idx >= 0) {
          allProfiles[idx] = saved;
        } else {
          allProfiles.push(saved);
        }

        currentSelectedId = saved.id;
        if (formTitleEl) {
          formTitleEl.textContent = `Редагування: ${saved.name || "профіль"}`;
        }
        fillForm(saved);
        renderList();
        updateActivePanel();
        updateCompatPanel();

        setStatus(hasId ? "Профіль оновлено." : "Профіль створено.", "success");
      })
      .catch((err) => {
        console.error(err);
        setStatus(`Помилка збереження: ${err.message}`, "error");
      })
      .finally(() => {
        isLoading = false;
      });
  }

  function deleteProfile() {
    const id = fId.value;
    if (!id) {
      setStatus("Немає що видаляти — профіль ще не збережений.", "error");
      return;
    }
    if (!window.confirm("Точно видалити цей профіль принтера?")) {
      return;
    }

    isLoading = true;
    setStatus("Видалення профілю…");
    apiFetch(`/api/printers/${encodeURIComponent(id)}`, {
      method: "DELETE",
    })
      .then(() => {
        allProfiles = allProfiles.filter((p) => String(p.id) !== String(id));
        if (activeId && String(activeId) === String(id)) {
          activeId = null;
        }
        clearForm();
        renderList();
        updateActivePanel();
        updateCompatPanel();
        setStatus("Профіль видалено.", "success");
      })
      .catch((err) => {
        console.error(err);
        setStatus(`Помилка видалення: ${err.message}`, "error");
      })
      .finally(() => {
        isLoading = false;
      });
  }

  function setActive(id) {
    if (!id) return;
    isLoading = true;
    setStatus("Встановлення активного профілю…");
    apiFetch(`/api/printers/${encodeURIComponent(id)}/activate`, {
      method: "POST",
      body: JSON.stringify({}),
    })
      .then((data) => {
        const active = data.item;
        activeId = active.id;

        // Оновимо is_active у списку
        allProfiles = allProfiles.map((p) => ({
          ...p,
          is_active: String(p.id) === String(activeId),
        }));

        renderList();
        updateActivePanel();
        updateCompatPanel();
        setStatus("Активний профіль оновлено.", "success");
      })
      .catch((err) => {
        console.error(err);
        setStatus(`Помилка встановлення активного профілю: ${err.message}`, "error");
      })
      .finally(() => {
        isLoading = false;
      });
  }

  // ======== ПРЕСЕТИ ========

  function renderPresets() {
    if (!presetsEl) return;
    presetsEl.innerHTML = "";
    PRESETS.forEach((preset) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "pp-chip";
      chip.textContent = preset.label;
      chip.addEventListener("click", () => {
        clearForm();
        if (formTitleEl) {
          formTitleEl.textContent = `Новий профіль (пресет: ${preset.label})`;
        }
        fName.value = preset.name;
        fModel.value = preset.model;
        fType.value = preset.type;
        fFirmware.value = preset.firmware;
        fBedX.value = preset.bed_x;
        fBedY.value = preset.bed_y;
        fBedZ.value = preset.bed_z;
        fFilamentDia.value = preset.filament_diameter;
        fNozzleDia.value = preset.nozzle_diameter;
        fTempNozzle.value = preset.temp_nozzle;
        fTempBed.value = preset.temp_bed;
        fMaxPrintSpeed.value = preset.max_print_speed;
        fMaxTravelSpeed.value = preset.max_travel_speed;
        fMaterials.value = preset.materials;
        fNotes.value = preset.notes;
        setStatus(
          `Пресет "${preset.label}" завантажено. Скоригуй за потреби й натисни "Зберегти".`,
          "info"
        );
      });
      presetsEl.appendChild(chip);
    });
  }

  // ======== ПОДІЇ ========

  if (btnNew) {
    btnNew.addEventListener("click", () => {
      clearForm();
      if (formTitleEl) formTitleEl.textContent = "Новий профіль принтера";
      setStatus("Створення нового профілю.", "info");
    });
  }

  if (btnSave) {
    btnSave.addEventListener("click", (ev) => {
      ev.preventDefault();
      saveProfile();
    });
  }

  if (btnDuplicate) {
    btnDuplicate.addEventListener("click", (ev) => {
      ev.preventDefault();
      const p = formToProfile();
      // дублікат — це новий профіль без id
      fId.value = "";
      if (p.name) {
        fName.value = `${p.name} (копія)`;
      }
      if (formTitleEl) formTitleEl.textContent = "Новий профіль (копія)";
      setStatus("Скопійовано у форму як новий профіль. Збережи його.", "info");
    });
  }

  if (btnDelete) {
    btnDelete.addEventListener("click", (ev) => {
      ev.preventDefault();
      deleteProfile();
    });
  }

  if (searchEl) {
    searchEl.addEventListener("input", () => {
      renderList();
    });
  }

  if (filterTypeEl) {
    filterTypeEl.addEventListener("change", () => {
      renderList();
    });
  }

  // Ініціалізація
  renderPresets();
  clearForm();
  loadAll();

  // Повертаємо невелике API
  return {
    reload: loadAll,
    getProfiles: () => allProfiles.slice(),
    getActiveId: () => activeId,
  };
}
