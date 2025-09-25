// chat.js
document.addEventListener("DOMContentLoaded", () => {
  // ---- елементи
  const themeSelect   = document.getElementById("chat-theme");
  const panel         = document.getElementById("chatPanel") || document.getElementById("chat-panel");
  const chatMessages  = document.getElementById("chat-messages");
  const sendBtn       = document.getElementById("chat-send");
  const input         = document.getElementById("chat-text");

  // якщо немає розмітки чату — виходимо тихо
  if (!panel || !chatMessages || !sendBtn || !input) return;

  // ---- тема (скоупимо тільки на чат, щоб не ламати сайт)
  const THEME_KEY = "chat-theme";
  const applyTheme = (v) => panel.setAttribute("data-theme", v);

  const savedTheme = (localStorage.getItem(THEME_KEY) || "dark");
  applyTheme(savedTheme);
  if (themeSelect) themeSelect.value = savedTheme;

  themeSelect?.addEventListener("change", () => {
    const v = themeSelect.value || "dark";
    applyTheme(v);
    localStorage.setItem(THEME_KEY, v);
  });

  // ---- утиліти
  const isNearBottom = () => {
    const threshold = 60; // px
    return chatMessages.scrollHeight - chatMessages.scrollTop - chatMessages.clientHeight < threshold;
  };

  const scrollToBottom = () => {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  };

  const esc = (s) =>
    (s ?? "").replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));

  // безпечне створення повідомлення без innerHTML
  function createMessageDom({ name = "Ти", text = "", avatar = "/static/default-avatar.png", profileUrl = "/profile/1" } = {}) {
    const row = document.createElement("div");
    row.className = "chat-message";

    const img = document.createElement("img");
    img.className = "chat-avatar";
    img.src = avatar;
    img.alt = "avatar";

    const content = document.createElement("div");
    content.className = "chat-content";

    const a = document.createElement("a");
    a.className = "chat-name";
    a.href = profileUrl;
    a.textContent = name;

    const body = document.createElement("div");
    body.className = "chat-text";
    // або body.textContent = text; (щоб взагалі виключити HTML)
    body.innerHTML = esc(text).replace(/\n/g, "<br>");

    content.appendChild(a);
    content.appendChild(body);

    row.appendChild(img);
    row.appendChild(content);
    return row;
  }

  function appendMessageSafe(payload) {
    const stick = isNearBottom();
    const node = createMessageDom(payload);
    chatMessages.appendChild(node);
    if (stick) scrollToBottom();
  }

  // ---- надсилання "тестових" локальних повідомлень
  function sendFromInput() {
    const val = input.value.replace(/\r/g, "");
    if (!val.trim()) return;
    appendMessageSafe({ name: "Ти", text: val, profileUrl: "/profile/1" });
    input.value = "";
    input.focus();
  }

  sendBtn.addEventListener("click", sendFromInput);

  // Enter = відправити, Shift+Enter = новий рядок
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendFromInput();
    }
  });

  // автоскрол, якщо повідомлення додаються ззовні
  const mo = new MutationObserver(() => {
    if (isNearBottom()) scrollToBottom();
  });
  mo.observe(chatMessages, { childList: true });

  // початковий скрол вниз
  scrollToBottom();
});
