(function () {
  const videos = document.querySelectorAll("video[data-video-preview]");
  if (!videos.length) return;

  function loadAndPlay(v) {
    if (!v.src) {
      const s = v.getAttribute("data-src");
      if (s) v.src = s;
    }
    // play може падати (autoplay policy) — ігноруємо
    const p = v.play();
    if (p && typeof p.catch === "function") p.catch(() => {});
  }

  function stop(v) {
    v.pause();
    // скидуємо на перший кадр
    try { v.currentTime = 0; } catch (e) {}
    // optional: вивантажити, щоб не тримати мережу
    // v.removeAttribute("src"); v.load();
  }

  videos.forEach((v) => {
    v.addEventListener("mouseenter", () => loadAndPlay(v));
    v.addEventListener("mouseleave", () => stop(v));
    v.addEventListener("touchstart", () => loadAndPlay(v), { passive: true });
    v.addEventListener("touchend", () => stop(v), { passive: true });
  });
})();