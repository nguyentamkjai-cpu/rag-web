const docsEl = document.querySelector("#docs");
const logEl = document.querySelector("#log");
const modeEl = document.querySelector("#mode");

function addBubble(text, who, sources) {
  const div = document.createElement("div");
  div.className = `bubble ${who}`;
  div.textContent = text;
  if (sources && sources.length) {
    const s = document.createElement("div");
    s.className = "src";
    s.textContent = "Nguồn: " + sources.map((x, i) => `[${i + 1}] ${x.title}`).join(" · ");
    div.appendChild(s);
  }
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
}

async function refresh() {
  const docs = await fetch("/api/docs").then((r) => r.json());
  docsEl.innerHTML = "";
  if (!docs.length) {
    docsEl.innerHTML = "<li><span class='meta'>Chưa có tài liệu.</span></li>";
    return;
  }
  for (const d of docs) {
    const li = document.createElement("li");
    li.innerHTML = `<div><strong>${d.title}</strong><div class="meta">${d.chunks} đoạn · ${d.chars} ký tự</div></div>`;
    const btn = document.createElement("button");
    btn.className = "ghost";
    btn.textContent = "Xóa";
    btn.onclick = async () => {
      await fetch("/api/docs/" + d.id, { method: "DELETE" });
      refresh();
    };
    li.appendChild(btn);
    docsEl.appendChild(li);
  }
}

document.querySelector("#file").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const body = new FormData();
  body.append("file", file);
  const res = await fetch("/api/upload", { method: "POST", body });
  if (!res.ok) {
    alert(await res.text());
    return;
  }
  e.target.value = "";
  refresh();
};

document.querySelector("#ask").onsubmit = async (e) => {
  e.preventDefault();
  const q = document.querySelector("#q");
  const question = q.value.trim();
  if (!question) return;
  addBubble(question, "user");
  q.value = "";
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  const data = await res.json();
  modeEl.textContent = data.mode === "llm" ? "model mở" : "trích đoạn";
  addBubble(data.answer, "bot", data.sources);
};

fetch("/api/health").then((r) => r.json()).then((h) => {
  modeEl.textContent = "sẵn sàng · " + h.ollama_model;
});
refresh();
addBubble("Tải một file lên, rồi hỏi bằng tiếng Việt. Nếu Ollama chưa chạy, mình vẫn trả các đoạn khớp trong tài liệu.", "bot");
