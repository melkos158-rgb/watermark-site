// static/js/dev_issues.js
// Логіка сторінки Dev Issues:
// - клік по проблемі → показати деталі внизу
// - згенерувати текст, який можна скинути в чат AI

document.addEventListener("DOMContentLoaded", () => {
  const problemItems = document.querySelectorAll(".problem-item");
  const detailBox = document.getElementById("problem-detail");
  const titleEl = document.getElementById("pd-title");
  const textEl = document.getElementById("pd-text");

  if (!problemItems.length || !detailBox || !titleEl || !textEl) {
    return;
  }

  problemItems.forEach((el) => {
    el.addEventListener("click", () => {
      const feature = el.dataset.feature || "";
      const file = el.dataset.file || "";
      const func = el.dataset.function || "";
      const details = el.dataset.details || "";
      const status = el.dataset.status || "";

      let statusText = "";
      if (status === "error") statusText = "ПРОБЛЕМА / БАГ";
      if (status === "fix") statusText = "ПОТРІБНА ПРАВКА";
      if (status === "orphan") statusText = "НЕ ПІДКЛЮЧЕНИЙ КОД";

      titleEl.textContent = "Проблема у фічі: " + feature;

      const text = 
`Фіча: ${feature}
Статус: ${statusText}

Файл: ${file}
Функція: ${func || "не вказано"}

Опис проблеми:
${details}

Що треба зробити:
(сюди своїми словами допиши, що хочеш отримати — і відправ весь цей текст AI)
`;

      textEl.textContent = text;
      detailBox.style.display = "block";

      // трохи прокрутити до блоку з деталями
      detailBox.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
});
