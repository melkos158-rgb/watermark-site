// static/market/js/ai_tools.js
// Фронтенд для AI-інструментів (генерація назв, описів, тегів, переклад)

(function () {
  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  async function callAI(endpoint, payload, outputEl) {
    if (!outputEl) return;

    outputEl.classList.remove("error");
    outputEl.textContent = "Генеруємо… ⏳";

    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload || {}),
      });

      if (!res.ok) {
        throw new Error("Bad status " + res.status);
      }

      const data = await res.json();
      const text = data.result || data.text || data.output;

      if (!text) {
        outputEl.textContent = "AI не повернув текст 😅";
        return;
      }

      outputEl.textContent = text;
    } catch (err) {
      console.error("AI tools error:", err);
      outputEl.classList.add("error");
      outputEl.textContent =
        "Сталася помилка при зверненні до AI. Спробуй ще раз пізніше.";
    }
  }

  function init() {
    const nameInput = qs("#ai-name-input");
    const nameOutput = qs("#ai-name-output");
    const btnName = qs("#ai-generate-name");

    const descInput = qs("#ai-desc-input");
    const descOutput = qs("#ai-desc-output");
    const btnDesc = qs("#ai-generate-desc");

    const tagsInput = qs("#ai-tags-input");
    const tagsOutput = qs("#ai-tags-output");
    const btnTags = qs("#ai-generate-tags");

    const translateInput = qs("#ai-translate-input");
    const translateLang = qs("#ai-translate-lang");
    const translateOutput = qs("#ai-translate-output");
    const btnTranslate = qs("#ai-translate-btn");

    // Якщо ми не на сторінці ai_tools.html — нічого не робимо
    if (
      !nameInput &&
      !descInput &&
      !tagsInput &&
      !translateInput
    ) {
      return;
    }

    // ===== Генерація назви =====
    if (btnName && nameInput && nameOutput) {
      btnName.addEventListener("click", () => {
        const prompt = (nameInput.value || "").trim();
        if (!prompt) {
          nameOutput.textContent = "Спочатку опиши модель 😉";
          return;
        }
        callAI("/api/ai/generate_name", { prompt }, nameOutput);
      });
    }

    // ===== Генерація опису =====
    if (btnDesc && descInput && descOutput) {
      btnDesc.addEventListener("click", () => {
        const prompt = (descInput.value || "").trim();
        if (!prompt) {
          descOutput.textContent = "Напиши хоча б 1–2 речення про модель.";
          return;
        }
        callAI("/api/ai/generate_description", { prompt }, descOutput);
      });
    }

    // ===== Генерація тегів =====
    if (btnTags && tagsInput && tagsOutput) {
      btnTags.addEventListener("click", () => {
        const prompt = (tagsInput.value || "").trim();
        if (!prompt) {
          tagsOutput.textContent = "Опиши модель або встав назву — AI підбере теги.";
          return;
        }
        callAI("/api/ai/generate_tags", { prompt }, tagsOutput);
      });
    }

    // ===== Переклад =====
    if (btnTranslate && translateInput && translateOutput && translateLang) {
      btnTranslate.addEventListener("click", () => {
        const text = (translateInput.value || "").trim();
        if (!text) {
          translateOutput.textContent = "Встав текст, який треба перекласти.";
          return;
        }
        const target_lang = translateLang.value || "en";
        callAI(
          "/api/ai/translate",
          { text, target_lang },
          translateOutput
        );
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
