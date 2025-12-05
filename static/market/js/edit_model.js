document.addEventListener("DOMContentLoaded", () => {

    console.log("edit_model.js loaded");

    // -----------------------------
    // 1) Авто-ресайз textarea
    // -----------------------------
    const ta = document.querySelector(".edit-textarea");
    if (ta) {
        const autoResize = () => {
            ta.style.height = "auto";
            ta.style.height = ta.scrollHeight + "px";
        };
        ta.addEventListener("input", autoResize);
        autoResize();
    }

    // -----------------------------
    // 2) Прев'ю кількості нових фото
    // -----------------------------
    const fileInput = document.querySelector("input[name='new_images']");
    if (fileInput) {
        fileInput.addEventListener("change", () => {
            const count = fileInput.files.length;
            fileInput.setAttribute("data-count", count);
            console.log("Вибрано нових фото:", count);
        });
    }

    // -----------------------------
    // 3) Підсвітка змінених інпутів
    // -----------------------------
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

    // -----------------------------
    // 4) Підсвітка зміненого select
    // -----------------------------
    const categorySelect = document.querySelector("select[name='category']");
    if (categorySelect) {
        const initial = categorySelect.value;
        categorySelect.addEventListener("change", () => {
            if (categorySelect.value !== initial) {
                categorySelect.style.borderColor = "#6f78ff";
            } else {
                categorySelect.style.borderColor = "#303341";
            }
        });
    }

    // -----------------------------
    // 5) Підсвітка чекбоксів "видалити фото"
    // -----------------------------
    document.querySelectorAll(".edit-photo-item input[type='checkbox']").forEach(cb => {
        cb.addEventListener("change", () => {
            const box = cb.closest(".edit-photo-item");
            if (cb.checked) {
                box.style.border = "1px solid #ff4d4d";
                box.style.background = "#20181a";
            } else {
                box.style.border = "1px solid #2d3040";
                box.style.background = "#1a1c25";
            }
        });
    });

    // -----------------------------
    // 6) Ховер на галерею фото
    // -----------------------------
    document.querySelectorAll(".edit-photo-item").forEach(item => {
        item.addEventListener("mouseenter", () => {
            item.style.transform = "scale(1.03)";
        });
        item.addEventListener("mouseleave", () => {
            item.style.transform = "scale(1)";
        });
    });

});
