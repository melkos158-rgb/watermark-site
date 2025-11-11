// Дрібниці для UX фільтрів: збереження стану, автопідказки
import { suggest } from "./api.js";
const $ = (s, r=document) => r.querySelector(s);

function saveState() {
  const st = {
    q:   $("#q")?.value || "",
    cat: $("#cat")?.value || "",
    sort:$("#sort")?.value || "new",
  };
  localStorage.setItem("market:state", JSON.stringify(st));
}
function restoreState() {
  try {
    const st = JSON.parse(localStorage.getItem("market:state")||"{}");
    if ($("#q")   && !$("#q").value)   $("#q").value = st.q || "";
    if ($("#cat") && !$("#cat").value) $("#cat").value = st.cat || "";
    if ($("#sort")&& !$("#sort").value)$("#sort").value = st.sort || "new";
  } catch {}
}
document.addEventListener("DOMContentLoaded", () => {
  restoreState();
  ["#q","#cat","#sort"].forEach(sel => $(sel)?.addEventListener("change", saveState));
  $("#q")?.addEventListener("input", debounce(async (e)=>{
    const q = e.target.value.trim();
    if (q.length < 2) return;
    try {
      const items = await suggest(q);
      // тут можна підсвітити дропдаун із підказками (мінімалізм)
      console.debug("suggest:", items);
    } catch {}
  }, 250));
});

// простий debounce
function debounce(fn, ms=300){ let t; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a), ms); }; }

