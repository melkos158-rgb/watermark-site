// Cleaned: No open_upload or modal logic remains
// If on /market/upload, do nothing (do not open modal, do not redirect)
if (window.location.pathname.startsWith("/market/upload")) {
  // Dedicated upload page, do not auto-open modal or redirect
} else {
  // ...existing (now removed) open_upload/modal logic would go here if needed for /market
}
import './upload_manager.js';
// static/market/js/uploader.js
// =====================================================
// Завантаження моделі через форму модалки + UX покращення
// =====================================================
import { uploadModel } from "./api.js";

document.addEventListener("DOMContentLoaded", () => {
  // If on /market/upload, do nothing (skip modal/init logic)
  if (window.location.pathname.startsWith('/market/upload')) return;
  const form = document.getElementById("upload-form");
  if (!form) return;

  const mainFileI = form.querySelector('input[name="file"]');     
  const coverI    = form.querySelector('input[name="cover"]');    
  const filesI    = form.querySelector('input[name="files"]');    
  const imagesI   = form.querySelector('input[name="images"]');   

  // Drag&Drop для всіх блоків .drop
  form.querySelectorAll(".drop").forEach(drop => {
    drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("hover"); });
    drop.addEventListener("dragleave", () => { drop.classList.remove("hover"); });
    drop.addEventListener("drop", (e) => {
      e.preventDefault(); drop.classList.remove("hover");
      const input = drop.querySelector('input[type="file"]');
      if (input) input.files = e.dataTransfer.files;
    });
  });

  // Попередній перегляд обкладинки
  const coverPreview = document.createElement("img");
  coverPreview.className = "cover-preview";
  if (coverI && coverI.parentNode) coverI.parentNode.appendChild(coverPreview);

  if (coverI) {
    coverI.addEventListener("change", () => {
      if (!coverI.files.length) { coverPreview.src = ""; coverPreview.style.display = "none"; return; }
      const file = coverI.files[0];
      coverPreview.src = URL.createObjectURL(file);
      coverPreview.style.display = "block";
    });
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const uploadEndpoint = form.dataset.uploadEndpoint || "/api/market/upload";
    const draftEndpoint = form.dataset.draftEndpoint || "/api/market/items/draft";
    const fd = new FormData(form);

    // ── Нормалізація полів під upload ───────────────────────────
    const hasMain = !!(mainFileI?.files?.length);
    const hasOld  = !!(filesI?.files?.length);
    if (!hasMain && hasOld) {
      fd.delete("files");
      fd.set("file", filesI.files[0]);
    }

    const hasCoverNew = !!(coverI?.files?.length);
    const hasCoverOld = !!(imagesI?.files?.length);
    if (!hasCoverNew && hasCoverOld) {
      fd.delete("images");
      fd.set("cover", imagesI.files[0]);
    }

    const mainFilePresent =
      (mainFileI && mainFileI.files && mainFileI.files.length) ||
      (fd.get("file") instanceof File);

    if (!mainFilePresent) {
      alert("⚠️ Додай хоча б один STL/OBJ/GLTF/ZIP файл перед завантаженням.");
      return;
    }

    const submitBtn = form.querySelector('button[type="submit"]');
    const prevText = submitBtn ? submitBtn.textContent : "";
    const progress = createProgressBar(form);

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = "⏳ Завантаження...";
    }

    try {
      // 1) Створити draft
      const draftRes = await fetch(draftEndpoint, { method: "POST", body: fd, credentials: "same-origin" });
      const draftJson = await draftRes.json();
      if (!draftRes.ok) throw new Error(draftJson?.error || "Draft failed");

      // 2) Upload
      const uploadRes = await fetch(uploadEndpoint, { method: "POST", body: fd, credentials: "same-origin" });
      const uploadJson = await uploadRes.json();
      if (!uploadRes.ok) throw new Error(uploadJson?.error || "Upload failed");

      // 3) Redirect
      const itemId = uploadJson?.item_id || uploadJson?.id;
      if (itemId) window.location.href = `/item/${itemId}`;
      else window.location.href = "/market";
    } catch (err) {
      console.error(err);
      alert("❌ Помилка під час завантаження.");
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = prevText;
      }
      progress.remove();
    }
  });
});

// =====================================================
// Допоміжні функції
// =====================================================

// Відображення progress bar
function createProgressBar(form) {
  const barWrap = document.createElement("div");
  barWrap.className = "upload-progress";
  barWrap.innerHTML = `<div class="bar"><div class="fill"></div></div><div class="percent">0%</div>`;
  form.appendChild(barWrap);
  return barWrap;
}

// Завантаження з індикатором прогресу
function uploadWithProgress(fd, barWrap) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/market/upload", true);
    xhr.withCredentials = true;

    xhr.upload.onprogress = (e) => {
      if (!e.lengthComputable) return;
      const p = Math.round((e.loaded / e.total) * 100);
      barWrap.querySelector(".fill").style.width = p + "%";
      barWrap.querySelector(".percent").textContent = p + "%";
    };

    xhr.onload = () => {
      try {
        const res = JSON.parse(xhr.responseText || "{}");
        if (xhr.status >= 200 && xhr.status < 300) resolve(res);
        else reject(res);
      } catch (e) { reject(e); }
    };

    xhr.onerror = () => reject(new Error("network"));
    xhr.send(fd);
  });
}

// =====================================================
// CSS (інжектується автоматично)
// =====================================================
const css = `
.upload-progress {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: var(--muted);
}
.upload-progress .bar {
  width: 100%;
  height: 6px;
  border-radius: 4px;
  background: var(--line);
  overflow: hidden;
}
.upload-progress .fill {
  width: 0%;
  height: 100%;
  background: var(--accent);
  transition: width 0.2s linear;
}
.upload-progress .percent {
  text-align: right;
}
.cover-preview {
  display: none;
  margin-top: 6px;
  width: 100%;
  max-height: 180px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid var(--line);
}
`;
const style = document.createElement("style");
style.textContent = css;
document.head.appendChild(style);
