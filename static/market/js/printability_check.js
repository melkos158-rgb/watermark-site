// static/market/js/printability_check.js
// Аналіз друкованості STL/OBJ моделей (фронтенд)

(function () {
  const runBtn = document.getElementById("printability-run");
  const selectItem = document.getElementById("printability-item-select");
  const fileInput = document.getElementById("printability-file");
  const materialEl = document.getElementById("printability-material");
  const layerHeightEl = document.getElementById("printability-layer-height");
  const supportsEl = document.getElementById("printability-supports");

  const statusEl = document.getElementById("printability-status");
  const summaryEl = document.getElementById("printability-summary");
  const issuesEl = document.getElementById("printability-issues");
  const tipsEl = document.getElementById("printability-tips");

  if (!runBtn) return;

  function setStatus(text, isError = false) {
    statusEl.textContent = text;
    statusEl.style.color = isError ? "#ff6b6b" : "#9fb0d4";
  }

  function clearResults() {
    summaryEl.innerHTML = "";
    issuesEl.innerHTML = "";
    tipsEl.innerHTML = "";
  }

  function createIssueBlock(issue) {
    const div = document.createElement("div");
    div.className = "printability-issue";

    const title = document.createElement("div");
    title.className = "printability-issue-title";
    title.textContent = issue.title;

    const desc = document.createElement("div");
    desc.className = "printability-issue-desc";
    desc.textContent = issue.description || "";

    if (issue.value != null) {
      const val = document.createElement("div");
      val.className = "printability-issue-value";
      val.textContent = `Значення: ${issue.value}`;
      div.appendChild(val);
    }

    div.appendChild(title);
    div.appendChild(desc);

    return div;
  }

  async function runAnalysis() {
    clearResults();
    setStatus("Аналізуємо модель… ⏳");

    const itemId = selectItem?.value?.trim() || "";
    const file = fileInput.files[0] || null;

    if (!itemId && !file) {
      setStatus("Вибери STL або завантаж файл", true);
      return;
    }

    const material = materialEl.value;
    const layerHeight = layerHeightEl.value;
    const supports = supportsEl.value;

    const formData = new FormData();
    formData.append("material", material);
    formData.append("layer_height", layerHeight);
    formData.append("supports", supports);

    if (itemId) formData.append("item_id", itemId);
    if (file) formData.append("file", file);

    try {
      const res = await fetch("/api/market/printability", {
        method: "POST",
        body: formData
      });

      if (!res.ok) {
        throw new Error("Помилка сервера");
      }

      const data = await res.json();

      // ===== Summary =====
      summaryEl.innerHTML = `
        <div class="printability-summary-block">
          <h3>${data.summary || "Результати аналізу"}</h3>
        </div>
      `;

      // ===== Issues =====
      if (Array.isArray(data.issues) && data.issues.length > 0) {
        data.issues.forEach(issue => {
          issuesEl.appendChild(createIssueBlock(issue));
        });
      } else {
        issuesEl.innerHTML = `
          <p class="muted small">Серйозних проблем не виявлено 🎉</p>
        `;
      }

      // ===== Tips =====
      if (Array.isArray(data.tips) && data.tips.length > 0) {
        tipsEl.innerHTML = `
          <h3>Рекомендації</h3>
          <ul class="printability-tips-list">
            ${data.tips.map(t => `<li>${t}</li>`).join("")}
          </ul>
        `;
      }

      setStatus("Готово ✔");
    } catch (err) {
      console.error(err);
      setStatus("Помилка аналізу 😢", true);
    }
  }

  runBtn.addEventListener("click", runAnalysis);
})();
