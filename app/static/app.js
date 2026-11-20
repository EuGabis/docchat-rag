// DocChat RAG — interface web (JavaScript puro, sem build)
const $ = (sel) => document.querySelector(sel);
const thread = $("#thread");
const form = $("#composer");
const input = $("#question");
const sendBtn = $("#send");
let mode = "hybrid";
let busy = false;

const MODE_LABEL = { hybrid: "híbrida", vector: "vetorial", keyword: "palavra-chave" };

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// Markdown mínimo e seguro (negrito, itálico, listas, parágrafos) + marcadores de citação
function renderAnswer(segments) {
  let raw = "";
  let last = null;
  for (const seg of segments) {
    if (seg.type === "text") { raw += seg.text; last = null; }
    else if (seg.type === "cite" && seg.index !== last) { raw += `\u0001${seg.index}\u0002`; last = seg.index; }
  }
  const inline = (s) => escapeHtml(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*(?!\s)(.+?)\*/g, "$1<em>$2</em>")
    .replace(/_\((.+?)\)_/g, "<em>($1)</em>")
    .replace(/\u0001(\d+)\u0002/g, (_, i) => `<button class="cite" data-i="${i}" title="Ver fonte ${+i + 1}">${+i + 1}</button>`);

  const blocks = raw.split(/\n{2,}/);
  return blocks.map((block) => {
    const lines = block.split("\n").filter((l) => l.trim() !== "");
    if (lines.length && lines.every((l) => /^\s*([-*•]|\d+\.)\s+/.test(l) || /^\u0001\d+\u0002$/.test(l.trim()))) {
      return "<ul>" + lines.map((l) => `<li>${inline(l.replace(/^\s*([-*•]|\d+\.)\s+/, ""))}</li>`).join("") + "</ul>";
    }
    return lines.length ? `<p>${lines.map(inline).join("<br>")}</p>` : "";
  }).join("");
}

function sourceCard(hit, index) {
  const badges = [];
  if (hit.vector_rank) badges.push(`<span class="badge v" title="Posição na busca vetorial (similaridade ${hit.similarity})">vetorial #${hit.vector_rank}</span>`);
  if (hit.keyword_rank) badges.push(`<span class="badge k" title="Posição na busca por palavra-chave">texto #${hit.keyword_rank}</span>`);
  badges.push(`<span class="badge" title="Score da Reciprocal Rank Fusion">rrf ${hit.score.toFixed(4)}</span>`);
  const section = hit.heading ? hit.heading.split(" > ").slice(-1)[0] : "";
  return `<div class="card" data-i="${index}">
      <div class="head"><span class="num">${index + 1}</span><span class="doc">${escapeHtml(hit.document_title)}</span>
      ${section ? `<span class="sec">· ${escapeHtml(section)}</span>` : ""}<div class="badges">${badges.join("")}</div></div>
      <div class="text">${escapeHtml(hit.content)}</div></div>`;
}

function addUserMessage(text) {
  $("#empty")?.remove();
  const el = document.createElement("div");
  el.className = "msg user";
  el.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
  thread.appendChild(el);
}

function addBotMessage() {
  const el = document.createElement("div");
  el.className = "msg bot";
  el.innerHTML = `<div class="bubble"><div class="answer typing"></div>
    <details class="sources" open><summary>Fontes consultadas</summary><div class="cards"></div></details>
    <div class="meta-line"></div></div>`;
  thread.appendChild(el);
  el.addEventListener("click", (e) => {
    const cite = e.target.closest(".cite");
    if (cite) {
      const card = el.querySelector(`.card[data-i="${cite.dataset.i}"]`);
      if (card) {
        el.querySelector("details.sources").open = true;
        card.scrollIntoView({ behavior: "smooth", block: "nearest" });
        card.classList.add("flash");
        setTimeout(() => card.classList.remove("flash"), 1400);
      }
    }
    const text = e.target.closest(".card .text");
    if (text) text.classList.toggle("open");
  });
  return el;
}

function scrollDown() { thread.scrollTop = thread.scrollHeight; }

async function ask(question) {
  if (busy || !question.trim()) return;
  busy = true; sendBtn.disabled = true;
  addUserMessage(question);
  const bot = addBotMessage();
  const answerEl = bot.querySelector(".answer");
  const cardsEl = bot.querySelector(".cards");
  const metaEl = bot.querySelector(".meta-line");
  const segments = [];
  let meta = {};
  scrollDown();

  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, mode }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sep;
      while ((sep = buffer.indexOf("\n\n")) >= 0) {
        const raw = buffer.slice(0, sep); buffer = buffer.slice(sep + 2);
        const event = /^event: (.+)$/m.exec(raw)?.[1];
        const data = JSON.parse(/^data: (.+)$/m.exec(raw)?.[1] || "{}");
        if (event === "sources") {
          meta.retrieval = data.retrieval_ms;
          cardsEl.innerHTML = data.hits.length ? data.hits.map(sourceCard).join("") : `<div class="sec">Nenhum trecho encontrado.</div>`;
          bot.querySelector("summary").textContent = `Fontes consultadas (${data.hits.length}) — busca ${MODE_LABEL[data.mode]}`;
        } else if (event === "text") {
          segments.push({ type: "text", text: data.text });
        } else if (event === "citation") {
          segments.push({ type: "cite", index: data.source_index });
        } else if (event === "usage") {
          meta.model = data.model; meta.tokens = data.input_tokens + data.output_tokens;
        } else if (event === "error") {
          segments.push({ type: "text", text: `\n\n` });
          answerEl.insertAdjacentHTML("afterend", `<p class="error">${escapeHtml(data.message)}</p>`);
        } else if (event === "done") {
          meta.total = data.total_ms; meta.llm = data.llm;
        }
        answerEl.innerHTML = renderAnswer(segments);
        answerEl.scrollIntoView({ block: "nearest" });
      }
    }
  } catch (err) {
    answerEl.innerHTML = `<p class="error">Falha ao consultar a API: ${escapeHtml(err.message)}</p>`;
  } finally {
    answerEl.classList.remove("typing");
    const parts = [`busca ${meta.retrieval ?? "?"} ms`, `total ${((meta.total ?? 0) / 1000).toFixed(1)} s`];
    parts.push(meta.model ? `${meta.model} · ${meta.tokens} tokens` : "sem LLM (somente recuperação)");
    metaEl.textContent = parts.join(" · ");
    busy = false; sendBtn.disabled = false; input.focus();
    // ao terminar, deixa a pergunta no topo para ler a resposta do começo
    bot.previousElementSibling?.scrollIntoView({ block: "start" });
  }
}

// ---------- documentos ----------
async function loadDocs() {
  const docs = await (await fetch("/api/documents")).json();
  const ext = (d) => ({ "application/pdf": "PDF", "text/markdown": "MD", "text/plain": "TXT" })[d.mime] || "DOC";
  $("#docs").innerHTML = docs.map((d) => `<li>
      <span class="icon">${ext(d)}</span>
      <div class="meta"><div class="title" title="${escapeHtml(d.title)}">${escapeHtml(d.title)}</div>
      <div class="sub">${d.chunks} trechos · ${escapeHtml(d.source)}</div></div>
      <button class="del" data-id="${d.id}" title="Remover documento">×</button></li>`).join("")
    || `<li><div class="meta"><div class="sub">Nenhum documento ainda.</div></div></li>`;
}

async function loadHealth() {
  const h = await (await fetch("/api/health")).json();
  const pill = $("#llm-pill");
  if (h.llm.enabled) { pill.textContent = `LLM: ${h.llm.model}`; pill.className = "pill"; }
  else { pill.textContent = "sem chave do Claude: só recuperação"; pill.className = "pill warn"; }
  $("#stats-pill").textContent = `${h.documents} docs · ${h.chunks} trechos`;
}

async function upload(file) {
  const msg = $("#upload-msg");
  msg.textContent = `Indexando ${file.name}…`;
  const body = new FormData();
  body.append("file", file);
  const res = await fetch("/api/documents", { method: "POST", body });
  const data = await res.json();
  msg.textContent = res.ok
    ? `✓ ${data.title}: ${data.chunks} trechos indexados${data.replaced ? " (versão anterior substituída)" : ""}`
    : `Erro: ${data.detail}`;
  await Promise.all([loadDocs(), loadHealth()]);
}

$("#docs").addEventListener("click", async (e) => {
  const btn = e.target.closest(".del");
  if (!btn || !confirm("Remover este documento do índice?")) return;
  await fetch(`/api/documents/${btn.dataset.id}`, { method: "DELETE" });
  await Promise.all([loadDocs(), loadHealth()]);
});

const drop = $("#drop");
$("#file").addEventListener("change", (e) => e.target.files[0] && upload(e.target.files[0]));
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); e.dataTransfer.files[0] && upload(e.dataTransfer.files[0]); });

// ---------- controles ----------
$("#mode").addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  mode = btn.dataset.mode;
  document.querySelectorAll("#mode button").forEach((b) => b.classList.toggle("active", b === btn));
});

$("#suggestions")?.addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (btn) ask(btn.textContent);
});

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = input.value;
  input.value = ""; input.style.height = "auto";
  ask(q);
});
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
});
input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = `${input.scrollHeight}px`; });

loadDocs();
loadHealth();

// links compartilháveis: /?q=sua+pergunta&mode=vector já abre com a pergunta respondida
const params = new URLSearchParams(location.search);
if (params.get("mode") && MODE_LABEL[params.get("mode")]) {
  document.querySelector(`#mode button[data-mode="${params.get("mode")}"]`).click();
}
if (params.get("q")) ask(params.get("q"));
