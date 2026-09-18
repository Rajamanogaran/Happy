const $ = (s) => document.querySelector(s);
let skills = [],
  history = [],
  currentView = "command",
  busy = false,
  toastTimer,
  conversationReady = false;
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const safeUrl = (u) => (/^https?:\/\//i.test(u) ? u : "#");
const sourceMarkup = (s, i) =>
  safeUrl(s.url) === "#"
    ? `<span class="source-note">[${i + 1}] ${esc(s.title)} · saved knowledge</span>`
    : `<a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">[${i + 1}] ${esc(s.title)} ↗</a>`;
async function api(path, data, method) {
  const r = await fetch("/api/" + path, {
    method: method || (data ? "POST" : "GET"),
    headers: { "Content-Type": "application/json" },
    ...(data ? { body: JSON.stringify(data) } : {}),
  });
  if (r.status === 401) {
    location.assign("/login");
    throw Error("Please sign in.");
  }
  if (!r.ok) {
    let e = await r.json().catch(() => ({}));
    throw Error(
      typeof e.detail === "string"
        ? e.detail
        : "Request failed. Check your input and try again.",
    );
  }
  return r.json();
}
function toast(text) {
  $("#toast").textContent = text;
  $("#toast").style.display = "block";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("#toast").style.display = "none"), 6000);
}
function go(view) {
  currentView = view;
  document
    .querySelectorAll(".view")
    .forEach((e) => e.classList.toggle("active", e.id === "view-" + view));
  document
    .querySelectorAll(".nav")
    .forEach((e) => e.classList.toggle("active", e.dataset.view === view));
  $("#page-name").textContent = {
    command: "Command center",
    chat: "Conversation",
    skills: "Skill library",
    agents: "Agents",
    knowledge: "Knowledge",
    browser: "Web explorer",
    settings: "Settings",
    tools: "Offline tools",
  }[view];
  if (view === "knowledge") loadNotes();
  if (view === "agents") loadAgents();
  window.scrollTo(0, 0);
}
document
  .querySelectorAll("[data-view],[data-go]")
  .forEach((b) => (b.onclick = () => go(b.dataset.view || b.dataset.go)));
$("#help").onclick = () => go("settings");
async function refreshStatus() {
  try {
    const s = await api("status");
    $("#side-status").textContent =
      s.status === "ready"
        ? "Local inference ready"
        : s.status === "loading"
          ? "Loading model"
          : "Model not loaded";
    $("#model-state").textContent =
      s.status === "ready"
        ? "● Online"
        : s.status === "loading"
          ? "Loading…"
          : "Setup needed";
    $("#model-state").classList.toggle("cyan", s.status === "ready");
    $("#core-status").textContent =
      s.status === "ready" ? "LOCAL MODEL ONLINE" : "READY TO EXPLORE";
    $("#memory-count").textContent = s.memories;
    $("#setup-status").textContent = s.detail;
    $("#protection-status").textContent = s.protected
      ? "Password protection is enabled. Sessions expire after 8 hours."
      : "Local mode: no password configured. Anyone with access to this server can open your workspace.";
    $("#logout").hidden = !s.protected;
    if ($("#chat-notice"))
      $("#chat-notice").textContent =
        s.status === "ready"
          ? "Local model online. Your conversation stays on this device."
          : "Model offline. Web tools and saved knowledge are available. See Settings to enable inference.";
  } catch (e) {
    $("#side-status").textContent = "Backend disconnected";
  }
}
function clock() {
  $("#clock").textContent =
    new Date().toLocaleTimeString("en-GB", {
      timeZone: "UTC",
      hour: "2-digit",
      minute: "2-digit",
    }) + " UTC";
}
clock();
setInterval(clock, 1000);
refreshStatus();
setInterval(refreshStatus, 15000);
for (let i = 0; i < 55; i++) {
  const bar = document.createElement("i");
  bar.style.height = 9 + Math.sin(i * 0.7) * 6 + (i % 7) * 2 + "px";
  $(".signal-bars").append(bar);
}
function renderSkills() {
  const query = $("#skill-search").value.toLowerCase(),
    category = $("#skill-category").value;
  const filtered = skills.filter(
    (s) =>
      s.name.toLowerCase().includes(query) &&
      (!category || s.category === category),
  );
  $("#skill-count").textContent = filtered.length + " skills";
  $("#skill-grid").innerHTML = filtered
    .map(
      (s) =>
        `<button class="skill-card" data-skill="${s.id}"><small>${esc(s.category.toUpperCase())} / ${s.id.slice(-3)}</small><h3>${esc(s.name)}</h3><span>Start a conversation ↗</span></button>`,
    )
    .join("");
  document.querySelectorAll("[data-skill]").forEach(
    (b) =>
      (b.onclick = () => {
        $("#chat-skill").value = b.dataset.skill;
        go("chat");
        $("#chat-message").placeholder =
          "Try " +
          skills.find((s) => s.id === b.dataset.skill).name.toLowerCase() +
          "…";
        $("#chat-message").focus();
      }),
  );
}
api("skills")
  .then((s) => {
    skills = s;
    $("#chat-skill").innerHTML = s
      .map((k) => `<option value="${k.id}">${esc(k.name)}</option>`)
      .join("");
    $("#skill-category").innerHTML += [...new Set(s.map((k) => k.category))]
      .map((c) => `<option>${esc(c)}</option>`)
      .join("");
    renderSkills();
  })
  .catch((e) => toast(e.message));
$("#skill-search").oninput = renderSkills;
$("#skill-category").onchange = renderSkills;
function addMessage(role, text, sources = [], warning) {
  $(".welcome")?.remove();
  const el = document.createElement("div");
  el.className = "message " + role;
  el.innerHTML =
    `<div class="label">${role === "user" ? "YOU" : "HAPPY"}</div><div>${esc(text)}</div>` +
    (warning ? `<p class="warning">${esc(warning)}</p>` : "") +
    sources.map((s, i) => `<div>${sourceMarkup(s, i)}</div>`).join("");
  $("#messages").append(el);
  $("#messages").scrollTop = $("#messages").scrollHeight;
  return el;
}
async function send(text) {
  if (busy) return;
  if (!conversationReady)
    return toast(
      "Saved conversation is still loading. Please try again in a moment.",
    );
  busy = true;
  go("chat");
  $("#chat-message").value = "";
  $("#send-chat").disabled = true;
  addMessage("user", text);
  const loading = addMessage("assistant", "Working on your request…");
  try {
    const r = await api("chat", {
      message: text,
      skill: $("#chat-skill").value || "skill-001",
      web: $("#chat-web").checked,
      history: history
        .slice(-6)
        .map((m) => ({ role: m.role, content: m.content.slice(0, 12000) })),
    });
    loading.remove();
    addMessage("assistant", r.answer, r.sources, r.warning);
    history.push(
      { role: "user", content: text },
      {
        role: "assistant",
        content: r.answer,
        sources: r.sources,
        warning: r.warning,
      },
    );
  } catch (e) {
    loading.remove();
    addMessage("assistant", e.message);
  } finally {
    busy = false;
    $("#send-chat").disabled = false;
  }
}
$("#chat-form").onsubmit = (e) => {
  e.preventDefault();
  const text = $("#chat-message").value.trim();
  if (text) send(text);
};
$("#chat-message").onkeydown = (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    $("#chat-form").requestSubmit();
  }
};
$("#quick-form").onsubmit = (e) => {
  e.preventDefault();
  const text = $("#quick-message").value.trim();
  if (text) send(text);
};
document
  .querySelectorAll("[data-prompt]")
  .forEach((b) => (b.onclick = () => send(b.dataset.prompt)));
$('[data-action="research"]').onclick = () => {
  go("browser");
  $("#browser-query").focus();
};
$("#clear-chat").onclick = async () => {
  if (busy) return toast("Wait for the current response to finish.");
  if (!confirm("Permanently delete the saved conversation?")) return;
  try {
    await api("conversation", null, "DELETE");
    history = [];
    $("#messages").replaceChildren();
    toast("Saved conversation deleted");
  } catch (e) {
    toast(e.message);
  }
};
api("conversation")
  .then((messages) => {
    history = messages;
    messages.forEach((m) =>
      addMessage(m.role, m.content, m.sources || [], m.warning),
    );
    conversationReady = true;
  })
  .catch((e) => {
    toast("Could not load saved conversation. Reload to retry. " + e.message);
  });
$("#export-chat").onclick = () => {
  if (!history.length) return toast("No saved messages to export.");
  const text = history
    .map(
      (m) =>
        `${m.role.toUpperCase()}\n${m.content}\n${(m.sources || []).map((s) => s.title + " — " + s.url).join("\n")}`,
    )
    .join("\n\n");
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "happy-conversation.txt";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
async function saveNote(title, content, source = "Note") {
  await api("knowledge", {
    title: title.slice(0, 200),
    content: content.slice(0, 30000),
    source: source.slice(0, 2000),
  });
  toast("Saved to your local knowledge");
  refreshStatus();
}
function resetNote() {
  $("#note-form").reset();
  $("#note-id").value = "";
  $("#note-source").value = "Note";
  $("#note-heading").textContent = "Add a memory";
  $("#save-note").textContent = "Save to knowledge +";
  $("#cancel-note-edit").hidden = true;
}
$("#cancel-note-edit").onclick = resetNote;
$("#note-form").onsubmit = async (e) => {
  e.preventDefault();
  const button = $("#save-note");
  button.disabled = true;
  try {
    const id = $("#note-id").value;
    if (id) {
      await api(
        "knowledge/" + id,
        {
          title: $("#note-title").value,
          content: $("#note-content").value,
          source: $("#note-source").value,
        },
        "PUT",
      );
      toast("Memory updated");
      refreshStatus();
    } else
      await saveNote(
        $("#note-title").value,
        $("#note-content").value,
        $("#note-source").value,
      );
    resetNote();
    loadNotes();
  } catch (err) {
    toast(err.message);
  } finally {
    button.disabled = false;
  }
};
async function loadNotes() {
  try {
    const query = $("#note-search").value;
    const notes = await api("knowledge?q=" + encodeURIComponent(query));
    if (query !== $("#note-search").value) return;
    $("#note-list").innerHTML = notes.length
      ? notes
          .map(
            (n) =>
              `<article class="note-card"><span class="job-status">${esc(n.created)}</span><h3>${esc(n.title)}</h3><p>${esc(n.content)}</p><small>${esc(n.source)}</small><br><button data-edit-note="${n.id}">Edit memory</button> <button data-delete="${n.id}">Delete memory</button></article>`,
          )
          .join("")
      : '<div class="empty-state"><div>▧</div><h3>Your discoveries belong here.</h3><p>Add a note above, or save a source from Web explorer.</p></div>';
    document.querySelectorAll("[data-edit-note]").forEach(
      (b) =>
        (b.onclick = () => {
          const n = notes.find((n) => n.id === +b.dataset.editNote);
          $("#note-id").value = n.id;
          $("#note-title").value = n.title;
          $("#note-content").value = n.content;
          $("#note-source").value = n.source;
          $("#note-heading").textContent = "Edit memory";
          $("#save-note").textContent = "Save changes";
          $("#cancel-note-edit").hidden = false;
          $("#note-title").focus();
          $("#note-form").scrollIntoView({
            behavior: "smooth",
            block: "start",
          });
        }),
    );
    document.querySelectorAll("[data-delete]").forEach(
      (b) =>
        (b.onclick = async () => {
          if (!confirm("Delete this memory?")) return;
          try {
            await api("knowledge/" + b.dataset.delete, null, "DELETE");
            loadNotes();
            refreshStatus();
          } catch (e) {
            toast(e.message);
          }
        }),
    );
  } catch (e) {
    toast(e.message);
  }
}
$("#browser-form").onsubmit = async (e) => {
  e.preventDefault();
  const query = $("#browser-query").value.trim();
  const button =
    e.submitter ||
    e.currentTarget.querySelector("button[type=submit],button.primary");
  button.disabled = true;
  $("#browser-results").className = "";
  $("#browser-results").innerHTML =
    '<div class="empty-state">Exploring public sources…</div>';
  try {
    const reading = /^https?:\/\//i.test(query);
    const data = await api(reading ? "browse" : "search", { query });
    const results = reading ? [data] : data;
    $("#browser-results").innerHTML = results.length
      ? results
          .map(
            (r, i) =>
              `<article class="result-card"><h3>${esc(r.title)}</h3><a href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener noreferrer">${esc(r.url)} ↗</a><p>${esc(r.content)}</p><button data-save-result="${i}">Save to knowledge +</button>${!reading ? ` <button data-read-result="${i}">Read page ↗</button>` : ""}</article>`,
          )
          .join("")
      : '<div class="empty-state">No results found. Try another search.</div>';
    document.querySelectorAll("[data-save-result]").forEach(
      (b) =>
        (b.onclick = async () => {
          const r = results[+b.dataset.saveResult];
          try {
            await saveNote(r.title, r.content || r.title, r.url);
          } catch (e) {
            toast(e.message);
          }
        }),
    );
    document.querySelectorAll("[data-read-result]").forEach(
      (b) =>
        (b.onclick = () => {
          $("#browser-query").value = results[+b.dataset.readResult].url;
          $("#browser-form").requestSubmit();
        }),
    );
  } catch (err) {
    $("#browser-results").textContent = err.message;
  } finally {
    button.disabled = false;
  }
};
$("#agent-form").onsubmit = async (e) => {
  e.preventDefault();
  const button =
    e.submitter ||
    e.currentTarget.querySelector("button[type=submit],button.primary");
  button.disabled = true;
  try {
    await api("agents", {
      query: $("#agent-topic").value,
      source: $("#agent-source").value,
    });
    $("#agent-topic").value = "";
    loadAgents();
    toast("Research workflow started");
  } catch (err) {
    toast(err.message);
  } finally {
    button.disabled = false;
  }
};
async function loadAgents() {
  try {
    const jobs = await api("agents");
    $("#agent-list").innerHTML = jobs.length
      ? jobs
          .map(
            (j) =>
              `<article class="job"><span class="job-status">${esc(j.status.toUpperCase())}</span><h3>${esc(j.topic)}</h3><ol>${j.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>${j.result ? `<pre>${esc(j.result)}</pre>` : ""}${j.sources.map(sourceMarkup).join("")}${j.status === "running" ? `<button data-cancel-job="${j.id}">Cancel research</button>` : ""}${!["running", "cancelling"].includes(j.status) ? `<button data-retry-job="${j.id}">Run again ↗</button> <button data-delete-job="${j.id}">Delete run</button>` : ""}${j.status === "complete" ? `<button data-save-job="${j.id}">Save research brief +</button>` : ""}</article>`,
          )
          .join("")
      : '<div class="empty-state"><div>⌘</div><h3>Ready for a mission.</h3><p>Give your crew a research topic to begin.</p></div>';
    document.querySelectorAll("[data-retry-job]").forEach(
      (b) =>
        (b.onclick = async () => {
          b.disabled = true;
          try {
            await api("agents/" + b.dataset.retryJob + "/retry", {});
            loadAgents();
            toast("New research run started");
          } catch (e) {
            toast(e.message);
            b.disabled = false;
          }
        }),
    );
    document.querySelectorAll("[data-delete-job]").forEach(
      (b) =>
        (b.onclick = async () => {
          if (
            !confirm(
              "Delete this research run? Saved knowledge is not affected.",
            )
          )
            return;
          try {
            await api("agents/" + b.dataset.deleteJob, null, "DELETE");
            loadAgents();
          } catch (e) {
            toast(e.message);
          }
        }),
    );
    document.querySelectorAll("[data-cancel-job]").forEach(
      (b) =>
        (b.onclick = async () => {
          b.disabled = true;
          try {
            await api("agents/" + b.dataset.cancelJob + "/cancel", {});
            loadAgents();
          } catch (e) {
            toast(e.message);
            b.disabled = false;
          }
        }),
    );
    document.querySelectorAll("[data-save-job]").forEach(
      (b) =>
        (b.onclick = async () => {
          const j = jobs.find((j) => j.id === b.dataset.saveJob);
          try {
            await saveNote(
              j.topic,
              j.result +
                "\n\nSources:\n" +
                j.sources.map((s) => s.url).join("\n"),
              "Research workflow",
            );
          } catch (e) {
            toast(e.message);
          }
        }),
    );
  } catch (e) {
    toast(e.message);
  }
}
setInterval(() => {
  if (currentView === "agents") loadAgents();
}, 3000);

let noteSearchTimer;
$("#note-search").oninput = () => {
  clearTimeout(noteSearchTimer);
  noteSearchTimer = setTimeout(loadNotes, 200);
};
$("#import-notes").onclick = () => $("#import-file").click();
$("#import-file").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    if (file.size > 32 * 1024 * 1024)
      throw Error("Backup exceeds the 32 MB import limit.");
    const data = JSON.parse(await file.text());
    if (data.version !== 1 || !Array.isArray(data.notes))
      throw Error("Choose a Happy knowledge JSON backup (version 1).");
    if (
      !confirm(
        `Import ${data.notes.length} notes? Existing notes stay unchanged; exact duplicates are skipped.`,
      )
    )
      return;
    const result = await api("knowledge/import", data);
    toast(`Imported ${result.added} new memories`);
    loadNotes();
    refreshStatus();
  } catch (err) {
    toast(err.message);
  } finally {
    e.target.value = "";
  }
};

$("#import-document").onclick = () => $("#document-file").click();
$("#document-file").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    if (!/\.(txt|md)$/i.test(file.name))
      throw Error("Choose a .txt or .md document.");
    if (file.size > 120000)
      throw Error("Choose a smaller document (maximum 30,000 characters).");
    const text = await file.text();
    if (text.length > 30000)
      throw Error(
        "Document exceeds the 30,000-character note limit. Split it into smaller notes.",
      );
    if (!text.trim()) throw Error("This document is empty.");
    resetNote();
    $("#note-title").value = file.name.slice(0, 200);
    $("#note-content").value = text;
    toast("Document loaded. Review it, then select Save to knowledge.");
  } catch (err) {
    toast(err.message);
  } finally {
    e.target.value = "";
  }
};

$("#logout").onclick = async () => {
  try {
    await fetch("/auth/logout", { method: "POST" });
    location.assign("/login");
  } catch (error) {
    toast(error.message);
  }
};
let toolCatalog = [],
  selectedTool = null,
  toolResult = "",
  toolResultName = "";
function chooseTool(id) {
  selectedTool = toolCatalog.find((t) => t.id === id);
  if (!selectedTool) return;
  $("#tool-name").textContent = selectedTool.name;
  $("#tool-description").textContent = selectedTool.description;
  $("#tool-input").placeholder = selectedTool.example;
  $("#tool-input").value = "";
  $("#tool-other").value = "";
  $("#tool-other-wrap").hidden = id !== "diff";
  $("#tool-result").hidden = true;
  toolResult = "";
  document
    .querySelectorAll("[data-tool]")
    .forEach((b) => b.classList.toggle("active", b.dataset.tool === id));
}
api("tools")
  .then((catalog) => {
    toolCatalog = catalog;
    $("#tool-picker").innerHTML = catalog
      .map(
        (t) =>
          `<button class="tool-choice" data-tool="${esc(t.id)}">${esc(t.name)}</button>`,
      )
      .join("");
    document
      .querySelectorAll("[data-tool]")
      .forEach((b) => (b.onclick = () => chooseTool(b.dataset.tool)));
    if (catalog.length) chooseTool(catalog[0].id);
  })
  .catch((e) => toast(e.message));
$("#tool-example").onclick = () => {
  if (selectedTool) {
    $("#tool-input").value = selectedTool.example;
    if (selectedTool.id === "diff") $("#tool-other").value = "Revised text";
  }
};
$("#tool-form").onsubmit = async (e) => {
  e.preventDefault();
  if (!selectedTool) return;
  const tool = selectedTool;
  const button = $("#run-tool");
  button.disabled = true;
  document.querySelectorAll("[data-tool]").forEach((b) => (b.disabled = true));
  $("#tool-result").hidden = true;
  try {
    const result = await api("tools/run", {
      tool: tool.id,
      text: $("#tool-input").value,
      other: $("#tool-other").value,
    });
    toolResult = result.output;
    toolResultName = tool.name;
    $("#tool-output").textContent = toolResult;
    $("#tool-result").hidden = false;
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
    document
      .querySelectorAll("[data-tool]")
      .forEach((b) => (b.disabled = false));
  }
};
$("#copy-tool").onclick = async () => {
  try {
    await navigator.clipboard.writeText(toolResult);
    toast("Result copied");
  } catch {
    toast(
      "Clipboard unavailable. Select the result text and copy it manually.",
    );
  }
};
$("#download-tool").onclick = () => {
  const url = URL.createObjectURL(
    new Blob([toolResult], { type: "text/plain;charset=utf-8" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "happy-tool-result.txt";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
$("#save-tool").onclick = async () => {
  try {
    if (!toolResult) return toast("There is no output to save.");
    if (toolResult.length > 30000)
      return toast("Result is too long for a note. Download it instead.");
    await saveNote(
      toolResultName,
      toolResult,
      "Offline utility · deterministic output",
    );
  } catch (error) {
    toast(error.message);
  }
};
