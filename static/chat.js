document.addEventListener("DOMContentLoaded", () => {
  const themeSelect = document.getElementById("chat-theme");
  const root = document.documentElement;

  // Відновлення теми з localStorage
  const savedTheme = localStorage.getItem("chat-theme") || "dark";
  root.setAttribute("data-theme", savedTheme);
  themeSelect.value = savedTheme;

  themeSelect.addEventListener("change", () => {
    root.setAttribute("data-theme", themeSelect.value);
    localStorage.setItem("chat-theme", themeSelect.value);
  });

  // Автоскрол вниз
  const chatMessages = document.getElementById("chat-messages");
  function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  // Відправка тестових повідомлень
  const sendBtn = document.getElementById("chat-send");
  const input = document.getElementById("chat-text");

  sendBtn.addEventListener("click", () => {
    if (!input.value.trim()) return;

    const msg = document.createElement("div");
    msg.classList.add("chat-message");
    msg.innerHTML = `
      <img src="/static/default-avatar.png" class="chat-avatar">
      <div class="chat-content">
        <a href="/profile/1" class="chat-name">Ти</a>
        <div class="chat-text">${input.value}</div>
      </div>`;
    chatMessages.appendChild(msg);

    input.value = "";
    scrollToBottom();
  });
});
