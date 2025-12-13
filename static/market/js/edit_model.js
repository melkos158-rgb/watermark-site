// =============================================================
//  EDIT MODEL — FIXED ENDPOINTS + FIXED FILE FIELD NAMES
//  Works with your current Flask routes:
//   - autosave: POST /api/item/<id>/update   (JSON)
//   - save all (files + fields): POST /api/item/<id>/update (multipart)
//   - delete (API exists): POST /api/item/<id>/delete
//
//  IMPORTANT: your backend expects file keys:
//   - cover image:   "cover" (or "cover_file")
//   - gallery images:"gallery_files"
//   - main model:    "stl_file" (or "file" / "files")
// =============================================================

document.addEventListener("DOMContentLoaded", async () => {
  console.log("%c[edit_model.js] loaded (FIXED)", "color:#8aff8a;font-weight:700");

  // --------------------------------------------------------------------
  // DOM
  // --------------------------------------------------------------------
  const form = document.querySelector(".edit-form");
  if (!form) return;

  const itemId = form.dataset.itemId;
  const autosaveStatus = document.getElementById("editAutosaveStatus");
  const coverPreviewEl = document.querySelector(".edit-cover-preview img");

  // Your template uses:
  //  - input[name="gallery_files"] for images
  //  - input[name="stl_file"]      for model
  const fileInputImages = document.querySelector("input[name='gallery_files']");
  const fileInputStl = document.querySelector("input[name='stl_file']");

  // --------------------------------------------------------------------
  // API endpoints (MATCH BACKEND)
  // --------------------------------------------------------------------
  const UPDATE_URL = `/api/item/${itemId}/update`; // exists in your market.py
  const UPLOAD_URL = `/api/item/${itemId}/update`; // we reuse update for multipart save

  // --------------------------------------------------------------------
  // Helpers
  // --------------------------------------------------------------------
  const delay = (ms) => new Promise((res) => setTimeout(res, ms));

  function setStatus(text, color = "#8c92b3") {
    if (!autosaveStatus) return;
    autosaveStatus.textContent = text;
    autosaveStatus.style.color = color;
  }

  function toast(text, type = "info") {
    const box = document.createElement("div");
    box.className = `toast toast-${type}`;
    box.textContent = text;
    document.body.appendChild(box);
    requestAnimationFrame(() => box.classList.add("show"));
    setTimeout(() => box.classList.remove("show"), 2300);
    setTimeout(() => box.remove(), 2800);
  }

  // dynamic injected styles for toast
  (() => {
    const css = `
      .toast{
        position:fixed;left:50%;bottom:25px;
        transform:translateX(-50%) translateY(40px);
        background:#0d0f18;border:1px solid #333;
        padding:10px 18px;border-radius:12px;
        opacity:0;transition:all .35s;z-index:3000;font-size:14px;
      }
      .toast.show{opacity:1;transform:translateX(-50%) translateY(0);}
      .toast-info{color:#cfe2ff;border-color:#6ea8fe;}
      .toast-ok{color:#98ffb5;border-color:#34d27a;}
      .toast-err{color:#ffb4b4;border-color:#d9534f;}
    `;
    const s = document.createElement("style");
    s.textContent = css;
    document.head.appendChild(s);
  })();

  function qs(name) {
    return form.querySelector(`[name="${name}"]`);
  }

  // --------------------------------------------------------------------
  // Debounce autosave
  // --------------------------------------------------------------------
  let autosaveTimer = null;

  function autosaveDebounced(name, value) {
    clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(() => autosaveField(name, value), 400);
  }

  async function autosaveField(name, value) {
    try {
      setStatus("Зберігаємо...", "#ffc26b");

      const res = await fetch(UPDATE_URL, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [name]: value }),
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) throw new Error(data.error || "Autosave failed");

      setStatus(`Збережено ✓ (${new Date().toLocaleTimeString()})`, "#35c46b");
      toast("Збережено", "ok");
    } catch (err) {
      console.error(err);
      toast("Помилка автозбереження", "err");
      setStatus("Помилка збереження", "#ff6b6b");
    }
  }

  // --------------------------------------------------------------------
  // Track dirty and autosave (text fields)
  // --------------------------------------------------------------------
  document.querySelectorAll(".edit-input, .edit-textarea").forEach((el) => {
    const initial = el.value;

    el.addEventListener("input", () => {
      el.classList.add("is-dirty");
      el.classList.remove("is-saved");
      setStatus("Є незбережені зміни...", "#ffb347");
      if (el.name) autosaveDebounced(el.name, el.value);
    });

    el.addEventListener("change", () => {
      if (el.value === initial) el.classList.remove("is-dirty");
    });
  });

  // --------------------------------------------------------------------
  // Auto-resize textarea
  // --------------------------------------------------------------------
  const ta = document.querySelector(".edit-textarea");
  if (ta) {
    const fit = () => {
      ta.style.height = "auto";
      ta.style.height = ta.scrollHeight + "px";
    };
    ta.addEventListener("input", fit);
    fit();
  }

  // --------------------------------------------------------------------
  // Preview NEW images before uploading
  // --------------------------------------------------------------------
  if (fileInputImages) {
    fileInputImages.addEventListener("change", () => {
      const f = fileInputImages.files && fileInputImages.files[0];
      if (!f) return;

      const url = URL.createObjectURL(f);
      if (coverPreviewEl) coverPreviewEl.src = url;

      toast(`Фото вибране (${fileInputImages.files.length})`, "info");
    });
  }

  // ✅ FIX 3: Live preview for cover file
  function wireImagePreview(inputEl, imgEl) {
    if (!inputEl || !imgEl) return;
    inputEl.addEventListener("change", () => {
      const f = inputEl.files && inputEl.files[0];
      if (!f) return;
      const url = URL.createObjectURL(f);
      imgEl.src = url;
      imgEl.onload = () => URL.revokeObjectURL(url);
      toast("Нова обкладинка завантажена", "ok");
    });
  }

  // ✅ FIX 3: Live preview for gallery files
  function wireGalleryPreview(inputEl, wrapEl) {
    if (!inputEl || !wrapEl) return;
    inputEl.addEventListener("change", () => {
      wrapEl.innerHTML = "";
      const files = Array.from(inputEl.files || []);
      if (!files.length) return;

      files.forEach((f) => {
        const thumb = document.createElement("div");
        thumb.className = "gallery-thumb";
        thumb.style.cssText = "display:inline-block;width:80px;height:60px;margin:4px;border-radius:8px;overflow:hidden;border:1px solid #333;";

        const img = document.createElement("img");
        img.style.cssText = "width:100%;height:100%;object-fit:cover;";
        const url = URL.createObjectURL(f);
        img.src = url;
        img.onload = () => URL.revokeObjectURL(url);

        thumb.appendChild(img);
        wrapEl.appendChild(thumb);
      });

      toast(`${files.length} фото вибрано`, "ok");
    });
  }

  // Wire up previews
  const coverInput = document.querySelector("input[name='cover'], input[name='cover_file']");
  wireImagePreview(coverInput || fileInputImages, coverPreviewEl);
  
  const galleryWrap = document.getElementById("newGalleryPreview");
  wireGalleryPreview(fileInputImages, galleryWrap);

  // --------------------------------------------------------------------
  // STL preview before upload
  // --------------------------------------------------------------------
  if (fileInputStl) {
    fileInputStl.addEventListener("change", async () => {
      const f = fileInputStl.files && fileInputStl.files[0];
      if (!f) return;

      if (!f.name.toLowerCase().match(/\.(stl|obj|ply|gltf|glb)$/)) {
        toast("Невірний формат STL", "err");
        return;
      }

      toast("Попередній перегляд STL...", "info");

      const viewer = document.getElementById("editStlViewer");
      if (!viewer) return;

      try {
        const { initViewer } = await import("/static/js/stl_viewer.js");
        const ctx = await initViewer({ containerId: "editStlViewer" });
        ctx.loadAnyFromFile(f);
        toast("STL завантажено у preview ✓", "ok");
      } catch (err) {
        console.error(err);
        toast("Помилка preview STL", "err");
      }
    });
  }

  // --------------------------------------------------------------------
  // Build FormData that MATCHES BACKEND expected keys
  // --------------------------------------------------------------------
  function buildMultipartForBackend() {
    const fd = new FormData();

    // send text fields (match your api_item_update keys)
    const title = qs("title")?.value ?? "";
    const price = qs("price")?.value ?? "";
    const tags = qs("tags")?.value ?? "";
    const description = qs("description")?.value ?? "";
    const category = qs("category")?.value ?? "";

    fd.append("title", title);
    fd.append("price", price);
    fd.append("tags", tags);
    fd.append("description", description);
    fd.append("category", category);

    // FILES:
    // new_images (template) -> backend wants gallery_files (+ optional cover)
    const imgs = fileInputImages?.files ? Array.from(fileInputImages.files) : [];
    if (imgs.length) {
      // 1) set first image as "cover" (so cover updates)
      fd.append("cover", imgs[0]);
      // 2) all images as gallery_files
      imgs.slice(0, 5).forEach((f) => fd.append("gallery_files", f));
    }

    // stl (template) -> backend wants stl_file
    const stl = fileInputStl?.files && fileInputStl.files[0] ? fileInputStl.files[0] : null;
    if (stl) {
      fd.append("stl_file", stl);
    }

    return fd;
  }

  // --------------------------------------------------------------------
  // Submit handler (save all: fields + files)
  // --------------------------------------------------------------------
  let submitting = false;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (submitting) return;
    submitting = true;

    setStatus("Завантажуємо файли...", "#ffc26b");
    toast("Йде завантаження...", "info");

    const fd = buildMultipartForBackend();

    try {
      const res = await fetch(UPLOAD_URL, {
        method: "POST",
        body: fd,
        credentials: "same-origin",
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) throw new Error(data.error || "Upload failed");

      setStatus("Файли успішно збережено ✓", "#35c46b");
      toast("Зміни застосовано", "ok");
    } catch (err) {
      console.error(err);
      setStatus("Помилка при завантаженні файлів", "#ff6b6b");
      toast("Помилка збереження", "err");
    }

    submitting = false;
  });

  // --------------------------------------------------------------------
  // Hotkey CTRL + S
  // --------------------------------------------------------------------
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key.toLowerCase() === "s") {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  // --------------------------------------------------------------------
  // INIT 3D viewer (existing STL)
  // --------------------------------------------------------------------
  const viewerWrap = document.getElementById("editStlViewer");
  if (viewerWrap) {
    const stlUrl = viewerWrap.dataset.stlUrl;

    if (stlUrl) {
      try {
        const { initViewer } = await import("/static/js/stl_viewer.js");
        const ctx = await initViewer({ containerId: "editStlViewer" });

        const resp = await fetch(stlUrl);
        const blob = await resp.blob();
        const nameGuess = stlUrl.split("/").pop() || "model.stl";
        const file = new File([blob], nameGuess);
        ctx.loadAnyFromFile(file);

        console.log("3D preview loaded");
      } catch (err) {
        console.error("viewer init error:", err);
      }
    }
  }

  // --------------------------------------------------------------------
  setStatus("Готово до редагування ✓", "#35c46b");
});

// =============================================================
//  DELETE MODEL FUNCTION
// =============================================================
window.deleteModel = async function(btn) {
  const itemId = btn.dataset.itemId;
  if (!itemId) {
    alert("Помилка: не знайдено ID моделі");
    return;
  }

  if (!confirm("Точно видалити? Дію не можна скасувати.")) {
    return;
  }

  btn.disabled = true;
  btn.textContent = "Видалення...";

  try {
    const res = await fetch(`/api/item/${itemId}/delete`, {
      method: "POST",
      credentials: "same-origin",
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok || data.ok === false) {
      throw new Error(data.error || "Помилка видалення");
    }

    // Success - redirect to my items
    window.location.href = "/market?owner=me";
  } catch (err) {
    console.error(err);
    alert(`Помилка видалення: ${err.message}`);
    btn.disabled = false;
    btn.textContent = "🗑 Видалити модель";
  }
};
