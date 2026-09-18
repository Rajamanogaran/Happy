// Run against a disposable Happy workspace, never your personal database.
// HAPPY_TEST_URL=http://127.0.0.1:8001 HAPPY_TEST_PASSWORD=... NODE_PATH=.cache/ui-tests/node_modules node scripts/test_browser.cjs
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { chromium } = require("playwright-core");
(async () => {
  if (!process.env.HAPPY_TEST_URL || !process.env.HAPPY_TEST_PASSWORD)
    throw Error(
      "Set HAPPY_TEST_URL and HAPPY_TEST_PASSWORD for a disposable password-protected test workspace.",
    );
  let options = { executablePath: process.env.CHROME_PATH, headless: true };
  if (!options.executablePath) {
    const packaged = require("@sparticuz/chromium");
    const binary = packaged.default || packaged;
    options.executablePath = await binary.executablePath();
    options.args = binary.args.filter(
      (a) => !a.includes("disable-web-security"),
    );
  }
  const browser = await chromium.launch(options);
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1050 },
  });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("dialog", (dialog) => dialog.accept());
  fs.mkdirSync(".cache/screenshots", { recursive: true });
  try {
    await page.goto(process.env.HAPPY_TEST_URL);
    await page.waitForURL("**/login");
    await page.locator("#password").fill(process.env.HAPPY_TEST_PASSWORD);
    await page.locator("#login-form button").click();
    await page.waitForURL(process.env.HAPPY_TEST_URL + "/");
    await page.locator(".skill-card").first().waitFor({ state: "attached" });
    assert.equal(await page.locator(".skill-card").count(), 100);
    await page.screenshot({
      path: ".cache/screenshots/dashboard.png",
      fullPage: true,
    });
    await page.locator('[data-view="tools"]').click();
    await page.locator("#tool-input").fill("(15 + 5) * 3");
    await page.locator("#run-tool").click();
    await page.waitForFunction(
      () => document.querySelector("#tool-output").textContent === "60",
    );
    await page.locator('[data-tool="json"]').click();
    await page.locator("#tool-input").fill('{"works":true}');
    await page.locator("#run-tool").click();
    await page.waitForFunction(() =>
      document
        .querySelector("#tool-output")
        .textContent.includes('"works": true'),
    );
    await page.locator('[data-view="knowledge"]').click();
    await page.locator("#note-title").fill("Browser smoke solar");
    await page
      .locator("#note-content")
      .fill("Solar panels convert sunlight into electricity.");
    await page.locator("#save-note").click();
    await page
      .locator(".note-card")
      .filter({ hasText: "Browser smoke solar" })
      .first()
      .waitFor();
    await page
      .locator(".note-card")
      .filter({ hasText: "Browser smoke solar" })
      .first()
      .locator("[data-edit-note]")
      .click();
    await page.locator("#note-title").fill("Browser smoke solar edited");
    await page.locator("#save-note").click();
    await page
      .locator(".note-card")
      .filter({ hasText: "Browser smoke solar edited" })
      .first()
      .waitFor();
    const downloadEvent = page.waitForEvent("download");
    await page.locator('a[href="/api/knowledge/export"]').click();
    const download = await downloadEvent;
    assert.equal(download.suggestedFilename(), "happy-knowledge.json");
    const backup = JSON.parse(fs.readFileSync(await download.path(), "utf8"));
    assert(backup.notes.some((n) => n.title === "Browser smoke solar edited"));
    await page
      .locator("#import-file")
      .setInputFiles({
        name: "backup.json",
        mimeType: "application/json",
        buffer: Buffer.from(
          JSON.stringify({
            version: 1,
            notes: [
              {
                title: "Imported document",
                content: "Import was successful.",
                source: "Backup",
              },
            ],
          }),
        ),
      });
    await page
      .locator(".note-card")
      .filter({ hasText: "Imported document" })
      .first()
      .waitFor();
    await page.locator('[data-view="agents"]').click();
    await page.locator("#agent-source").selectOption("knowledge");
    await page.locator("#agent-topic").fill("solar");
    await page.locator("#agent-form .primary").click();
    await page
      .locator(".job")
      .first()
      .locator("[data-save-job]")
      .waitFor({ timeout: 20000 });
    assert(
      (await page.locator(".job").first().innerText()).includes(
        "not an AI-generated answer",
      ),
    );
    await page.locator(".job").first().locator("[data-retry-job]").click();
    await page.waitForFunction(
      () => document.querySelectorAll(".job").length >= 2,
    );
    await page.locator(".job").first().locator("[data-delete-job]").waitFor();
    await page.locator(".job").first().locator("[data-delete-job]").click();
    await page.locator('[data-view="chat"]').click();
    await page
      .locator("#chat-message")
      .fill("What do my notes say about solar?");
    await page.locator("#send-chat").click();
    await page.waitForFunction(() =>
      document.querySelector("#messages").textContent.includes("sunlight"),
    );
    await page.reload();
    await page.locator('[data-view="chat"]').click();
    await page.waitForFunction(() =>
      document.querySelector("#messages").textContent.includes("sunlight"),
    );
    await page.locator('[data-view="command"]').click();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: ".cache/screenshots/mobile.png",
      fullPage: true,
    });
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
      "Dashboard overflows on mobile",
    );
    await page.locator('[data-view="tools"]').click();
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
      "Tools overflow on mobile",
    );
    await page.locator('[data-view="settings"]').click();
    await page.locator("#logout").click();
    await page.waitForURL("**/login");
    assert.equal(
      (
        await page.request.get(process.env.HAPPY_TEST_URL + "/api/knowledge")
      ).status(),
      401,
    );
    assert.deepEqual(errors, []);
    console.log(
      "PASS: Chromium desktop/mobile, password login/logout, utilities, edit, backup/import, offline research/retry/delete, chat persistence, and no page errors.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
