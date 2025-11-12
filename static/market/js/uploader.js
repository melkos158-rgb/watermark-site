// static/market/js/uploader.js
// Завантаження моделі через форму модалки
import { uploadModel } from "./api.js";

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("upload-form");
  if (!form) return;

  // Підтримуємо і нові, і старі назви інпутів
  const mainFileI = form.querySelector('input[name="file"]');     // нове
  const coverI    = form.querySelector('input[name="cover"]');    // нове
  const filesI    = form.querySelector('input[name="files"]');    // старе (multi)
  const imagesI   = form.querySelector('input[name="images"]');   // старе (multi)

  // Drag&drop на весь блок .drop
  form.querySelectorAll(".drop").forEach(drop=>{
    drop.addEventListener("dragover", (e)=>{ e.preventDefault(); drop.classList.add("hover"); });
    drop.addEventListener("dragleave",(e)=>{ drop.classList.remove("hover"); });
    drop.addEventListener("drop", (e)=>{
      e.preventDefault(); drop.classList.remove("hover");
      const input = drop.querySelector('input[type="file"]');
      if (input) input.files = e.dataTransfer.files;
    });
  });

  form.addEventListener("submit", async (e)=>{
    e.preventDefault();
    const fd = new FormData(form);

    // ── Нормалізація полів під /api/market/upload ───────────────────────────
    // 1) Головний файл: беремо з name="file", або зі старого name="files"[0]
    const hasMain = !!(mainFileI?.files?.length);
    const hasOld  = !!(filesI?.files?.length);
    if (!hasMain && hasOld) {
      // якщо в FormData випадково вже є "files", приберемо щоб не плутати бек
      fd.delete("files");
      fd.set("file", filesI.files[0]);
    }

    // 2) Обкладинка: name="cover" або зі старого name="images"[0]
    const hasCoverNew = !!(coverI?.files?.length);
    const hasCoverOld = !!(imagesI?.files?.length);
    if (!hasCoverNew && hasCoverOld) {
      fd.delete("images");
      fd.set("cover", imagesI.files[0]);
    }

    // Перевірка наявності головного файлу
    const mainFilePresent =
      (mainFileI && mainFileI.files && mainFileI.files.length) ||
      (fd.get("file") instanceof File);

    if (!mainFilePresent) {
      alert("Додай хоча б один STL/OBJ/GLTF/ZIP файл");
      return;
    }

    // ── UX: блокуємо кнопку під час аплоаду ─────────────────────────────────
    const submitBtn = form.querySelector('button[type="submit"]');
    const prevText = submitBtn ? submitBtn.textContent : "";
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "Завантаження…"; }

    try {
      const res = await uploadModel(fd);
      // Очікуємо { ok: true, url: "/market/<slug>" }
      if (res?.url) {
        location.href = res.url;
      } else {
        alert("Завантажено. Оновлюю сторінку.");
        location.reload();
      }
    } catch (err) {
      console.error(err);
      alert("Помилка завантаження.");
    } finally {
      if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = prevText; }
    }
  });
});
