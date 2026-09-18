// DOM integration smoke test. Does not replace visual browser testing.
// npm install --prefix .cache/ui-tests --no-audit --no-fund jsdom
// NODE_PATH=.cache/ui-tests/node_modules node scripts/test_ui.cjs
const { JSDOM } = require("jsdom");
const fs = require("node:fs");
const assert = require("node:assert/strict");
const html = fs.readFileSync("happy/static/index.html", "utf8");
const script = fs.readFileSync("happy/static/app.js", "utf8");
let notes = [],
  messages = [],
  jobs = [],
  errors = [];
const skills = Array.from({ length: 100 }, (_, i) => ({
  id: `skill-${String(i + 1).padStart(3, "0")}`,
  name: i === 0 ? "Python assistant" : `Skill ${i + 1}`,
  category: "Coding",
}));
function launch() {
  const dom = new JSDOM(html, {
    url: "http://happy.test",
    runScripts: "outside-only",
  });
  const w = dom.window;
  w.scrollTo = () => {};
  w.confirm = () => true;
  w.HTMLElement.prototype.scrollIntoView = () => {};
  w.addEventListener("error", (e) => errors.push(e.error));
  w.fetch = async (path, opts) => {
    const url = new URL(path, "http://happy.test");
    const data = opts.body ? JSON.parse(opts.body) : null;
    let result;
    if (url.pathname === "/api/tools")
      result = [
        {
          id: "calculator",
          name: "Safe calculator",
          description: "Arithmetic",
          example: "2 + 2",
        },
      ];
    else if (url.pathname === "/api/tools/run")
      result = { output: "4", generated: false };
    else if (url.pathname === "/api/knowledge/1" && opts.method === "PUT") {
      notes[0] = { ...notes[0], ...data };
      result = { id: 1 };
    } else if (url.pathname === "/api/status")
      result = {
        status: "offline",
        memories: notes.length,
        detail: "Model untouched",
      };
    else if (url.pathname === "/api/skills") result = skills;
    else if (url.pathname === "/api/chat") {
      result = {
        answer: "Retrieved excerpt, not model output",
        sources: [],
        warning: null,
      };
      messages.push(
        { role: "user", content: data.message },
        { role: "assistant", content: result.answer },
      );
    } else if (url.pathname === "/api/conversation") {
      if (opts.method === "DELETE") messages = [];
      result = messages;
    } else if (url.pathname === "/api/knowledge") {
      if (opts.method === "POST") {
        notes.push({ ...data, id: 1, created: "2026-09-18" });
        result = { id: 1 };
      } else
        result = notes.filter((n) =>
          n.title
            .toLowerCase()
            .includes((url.searchParams.get("q") || "").toLowerCase()),
        );
    } else if (url.pathname === "/api/agents") {
      if (data) {
        assert.equal(data.source, "knowledge");
        jobs.push({
          id: "run",
          topic: data.query,
          status: "complete",
          steps: ["Saved notes retrieved"],
          sources: [],
          result: "Solar source excerpt",
        });
      }
      result = data ? jobs[0] : jobs;
    } else if (url.pathname === "/api/search")
      result = [
        {
          title: "Example",
          url: "https://example.com",
          content: "Search excerpt",
        },
      ];
    else if (url.pathname === "/api/browse")
      result = {
        title: "Example page",
        url: data.query,
        content: "Full page text",
      };
    else throw Error("Unexpected route " + url.pathname);
    return { ok: true, json: async () => structuredClone(result) };
  };
  w.eval(script);
  return dom;
}
async function waitFor(fn) {
  for (let i = 0; i < 100; i++) {
    if (fn()) return;
    await new Promise((r) => setTimeout(r, 10));
  }
  throw Error("Timed out waiting for UI");
}
(async () => {
  let dom = launch(),
    w = dom.window,
    d = w.document;
  const $ = (s) => d.querySelector(s);
  try {
    await waitFor(() => d.querySelectorAll(".skill-card").length === 100);
    $('[data-view="skills"]').click();
    $("#skill-search").value = "Python";
    $("#skill-search").dispatchEvent(new w.Event("input"));
    assert.equal(d.querySelectorAll(".skill-card").length, 1);
    $(".skill-card").click();
    assert($("#view-chat").classList.contains("active"));
    $("#chat-message").value = "Hello";
    $("#chat-form").requestSubmit();
    await waitFor(
      () =>
        messages.length === 2 &&
        $("#messages").textContent.includes("Retrieved excerpt"),
    );
    assert($("#messages").textContent.includes("Retrieved excerpt"));
    // Status refresh after welcome node removal must not throw.
    await w.eval("refreshStatus()");
    $('[data-view="knowledge"]').click();
    $("#note-title").value = "Solar notes";
    $("#note-content").value = "Sunlight becomes electricity";
    $("#note-form").requestSubmit();
    await waitFor(() => $("#note-list").textContent.includes("Solar notes"));
    $("[data-edit-note]").click();
    $("#note-title").value = "Solar research";
    $("#note-form").requestSubmit();
    await waitFor(() => $("#note-list").textContent.includes("Solar research"));
    assert.equal(notes[0].source, "Note");
    $('[data-view="tools"]').click();
    await waitFor(() => $("[data-tool]"));
    $("#tool-example").click();
    $("#tool-form").requestSubmit();
    await waitFor(() => $("#tool-output").textContent === "4");
    $('[data-view="knowledge"]').click();
    $("#note-search").value = "missing";
    $("#note-search").dispatchEvent(new w.Event("input"));
    await waitFor(() => !$("#note-list").textContent.includes("Solar notes"));
    $('[data-view="agents"]').click();
    $("#agent-source").value = "knowledge";
    $("#agent-topic").value = "solar";
    $("#agent-form").requestSubmit();
    await waitFor(() =>
      $("#agent-list").textContent.includes("Solar source excerpt"),
    );
    $('[data-view="browser"]').click();
    $("#browser-query").value = "example";
    $("#browser-form").requestSubmit();
    await waitFor(() => $("[data-read-result]"));
    $("[data-read-result]").click();
    await waitFor(() =>
      $("#browser-results").textContent.includes("Full page text"),
    );
    dom.window.close();
    dom = launch();
    w = dom.window;
    d = w.document;
    await waitFor(() => d.querySelectorAll(".message").length === 2);
    $('[data-view="chat"]').click();
    $("#clear-chat").click();
    await waitFor(
      () =>
        messages.length === 0 && d.querySelectorAll(".message").length === 0,
    );
    assert.deepEqual(errors, []);
    console.log(
      "PASS: skills, chat, status refresh, knowledge search/save, offline agent, page reader, persistence restore and clear.",
    );
  } finally {
    dom.window.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
