// Завантаження моделі через форму модалки
import { uploadModel } from "./api.js";

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("upload-form");
  if (!form) return;

  const filesI  = form.querySelector('input[name="files"]');
  const imagesI = form.querySelector('input[name="images"]');

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
    if (!filesI?.files?.length) { alert("Додай хоча б один STL/OBJ/GLTF/ZIP файл"); return; }
    try {
      const res = await uploadModel(fd);
      // Очікуємо { ok: true, url: "/market/<slug>" }
      if (res?.url) location.href = res.url;
      else { alert("Завантажено. Оновлюю сторінку."); location.reload(); }
    } catch (err) {
      console.error(err);
      alert("Помилка завантаження.");
    }
  });
});

