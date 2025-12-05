document.addEventListener("DOMContentLoaded", () => {

    console.log("edit_model.js loaded");

    // --- Авто-ресайз textarea ---
    const ta = document.querySelector(".edit-textarea");
    if (ta) {
        ta.addEventListener("input", () => {
            ta.style.height = "auto";
            ta.style.height = ta.scrollHeight + "px";
        });
    }

    // --- Прев'ю нового зображення ---
    const fileInput = document.querySelector("input[name='new_images']");
    fileInput?.addEventListener("change", () => {
        const count = fileInput.files.length;
        fileInput.setAttribute("data-count", count);
    });

    // --- Підсвітка змін у інпутах ---
    document.querySelectorAll(".edit-input, .edit-textarea").forEach(el => {
        const startValue = el.value;
        el.addEventListener("input", () => {
            if (el.value !== startValue) {
                el.style.borderColor = "#6f78ff";
            } else {
                el.style.borderColor = "#303341";
            }
        });
    });
});
