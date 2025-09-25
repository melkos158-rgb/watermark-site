// chat.js
document.addEventListener("DOMContentLoaded", () => {
  // ---- вузли
  const panel        = document.getElementById("chatPanel") || document.getElementById("chat-panel");
  const themeSelect  = document.getElementById("chat-theme");
  const list         = document.getElementById("chat-messages");  // контейнер повідомлень
  const sendBtn      = document.getElementById("chat-send");
  const input        = document.getElementById("chat-text");

  // якщо верстки чату немає — тихо виходимо
  if (!panel || !list) return;

  // ---- хто я (щоб малювати свої справа)
  const CURRENT_UID = (panel.getAttribute("data-uid") || "").toString();

  // ---- тема, ізольована на панелі
  const THEME_KEY = "chat-theme";
  const applyTheme = (v) => panel.setAttribute("data-theme", v);
  const savedTheme = localStorage.getItem(THEME_KEY) || "dark";
  applyTheme(savedTheme);
  if (themeSelect) themeSelect.value = savedTheme;
  themeSelect?.addEventListener("change", () => {
    const v = themeSelect.value || "dark";
    applyTheme(v);
    localStorage.setItem(THEME_KEY, v);
  });

  // ---- утиліти
  const nearBottom = () => list.scrollHeight - list.scrollTop - list.clientHeight < 60;
  const scrollToBottom = () => { list.scrollTop = list.scrollHeight; };
  const esc = (s) => (s ?? "").replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));

  // запам’ятовуємо попереднього автора для групування
  let lastSenderId = null;

  // ---- побудова DOM одного повідомлення
  function buildMessageDOM(payload) {
    const {
      id = null,
      user_id = null,
      name = "Гість",
      text = "",
      time = "",
      avatar = "/static/default-avatar.png",
      profileUrl = user_id ? `/profile/${user_id}` : "#",
      // якщо це продовження серії того ж автора — без аватарки та хвостика
      isContinuation = false,
      isMe = false,
    } = payload;

    // ряд
    const row = document.createElement("div");
    row.className = "chat-row";
    if (isMe) row.classList.add("me");
    if (isContinuation) row.classList.add("cont");
    if (id != null) row.dataset.id = String(id);

    // аватар — тільки на першому в серії
    if (!isContinuation) {
      const img = document.createElement("img");
      img.className = "chat-avatar";
      img.src = avatar;
      img.alt = "avatar";
      if (!isMe) row.appendChild(img);
    }

    // бульбашка
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";

    // всередині один рядок: текст + час праворуч
    const line = document.createElement("div");
    line.className = "chat-line";

    const spanText = document.createElement("span");
    spanText.className = "chat-text";
    // безпечний текст (це не HTML)
    spanText.textContent = text;

    const spanTime = document.createElement("span");
    spanTime.className = "chat-time";
    spanTime.textContent = time || "";

    line.appendChild(spanText);
    if (time) line.appendChild(spanTime);
    bubble.appendChild(line);

    // якщо це моє — бульбашка ліворуч у DOM, аватар праворуч (row-reverse у CSS зробить решту)
    if (isMe) {
      row.appendChild(bubble);
      if (!isContinuation) {
        const img = document.createElement("img");
        img.className = "chat-avatar";
        img.src = avatar;
        img.alt = "avatar";
        row.appendChild(img);
      }
    } else {
      // чужі: аватар (якщо є) вже додали зліва; тепер бульбашку
      row.appendChild(bubble);
    }

    return row;
  }

  // ---- додавання повідомлення (публічна точка)
  function appendMessage(payload) {
    const stick = nearBottom();

    const uid = (payload.user_id ?? "").toString();
    const isMe = uid && uid === CURRENT_UID;
    const isContinuation = lastSenderId != null && (String(lastSenderId) === uid);

    const node = buildMessageDOM({
      ...payload,
      isMe,
      isContinuation,
    });

    list.appendChild(node);
    lastSenderId = payload.user_id ?? null;

    if (stick) scrollToBottom();
  }

  // зробимо доступним у вікні: window.ChatAppend(payload)
  window.ChatAppend = appendMessage;

  // ---- локальне тестове надсилання (без сервера)
  function sendFromInput() {
    if (!sendBtn || !input) return;
    const raw = input.value.replace(/\r/g, "");
    if (!raw.trim()) return;

    appendMessage({
      id: Date.now(),
      user_id: CURRENT_UID || "me",
      name: "Ти",
      text: raw,
      time: new Date().toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"}),
      avatar: "/static/default-avatar.png",
    });

    input.value = "";
    input.focus();
  }

  sendBtn?.addEventListener("click", sendFromInput);
  input?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendFromInput();
    }
  });

  // автоскрол, якщо щось додається зовні
  const mo = new MutationObserver(() => { if (nearBottom()) scrollToBottom(); });
  mo.observe(list, { childList: true });

  // стартовий скрол вниз
  scrollToBottom();
});
