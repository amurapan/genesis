/** Browser checks of the public investigation desk, using an existing BrowserContext. */
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

export default async ({ context }) => {
  const base = process.env.SLED_WEB_URL || "http://127.0.0.1:4174";
  const root = process.env.SLED_REPO || process.cwd();
  const page = await context.newPage();
  await page.route("**/*", (route) => route.continue());
  const errors = [],
    failures = [],
    checks = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.url().startsWith(base) && response.status() >= 400)
      failures.push(`${response.status()} ${response.url()}`);
  });
  const pass = (name) => checks.push(name);
  const screenshot = (name) =>
    page.screenshot({ path: resolve(root, "docs/images", name + ".png") });
  const finish = () =>
    page.locator('.transport-bar [data-action="finish"]').click();
  const open = async (route = "workspace") => {
    await page.goto(`${base}/lab.html#${route}`, { waitUntil: "networkidle" });
    await page.locator("#app").waitFor({ state: "visible" });
  };
  const scrub = async (step) => {
    await page.locator("#replay-range").fill(String(step));
    await page.locator("#replay-range").dispatchEvent("change");
  };
  const evidence = (id) => page.locator(`.evidence-link[data-proof="${id}"]`);
  await mkdir(resolve(root, "docs/images"), { recursive: true });
  try {
    await page.setViewportSize({ width: 1440, height: 1080 });
    await open();
    assert.match(
      await page.locator("#app h1").textContent(),
      /Валюта и граница периода/,
    );
    assert.equal(await page.locator(".case-item").count(), 10);
    for (const selector of [
      ".case-library",
      ".source-workspace",
      ".analysis-workspace",
      ".transport-bar",
    ])
      assert.equal(await page.locator(selector).isVisible(), true);
    assert.match(
      await page.locator(".paper-total").textContent(),
      /100\s000,00\sKZT/,
    );
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollHeight <= innerHeight,
      ),
      true,
    );
    await screenshot("workspace");
    pass(
      "Desktop workbench exposes cases, readable document, analysis and playback without page overflow",
    );

    await page
      .locator('.related-documents [data-proof="doc:payment-doc-1"]')
      .click();
    assert.match(
      await page.locator(".paper-total").textContent(),
      /100,00\sUSD/,
    );
    assert.match(
      await page.locator(".paper-facts").textContent(),
      /30.11.2026/,
    );
    await page.locator("#document-select").selectOption("0");
    assert.match(
      await page.locator(".paper-title h2").textContent(),
      /Счёт на оплату/,
    );
    pass(
      "Document viewer follows explicit invoice/payment links and retains original currencies",
    );

    await page.locator('[data-tab="ledger"]').click();
    assert.equal(await page.locator(".data-table tbody tr").count(), 4);
    await page.locator("#ledger-search").fill("cash");
    assert.equal(await page.locator(".data-table tbody tr").count(), 1);
    assert.equal(await page.locator("#ledger-search").inputValue(), "cash");
    await page.locator("#ledger-search").fill("no-such-row");
    assert.equal(await page.locator(".search-empty").count(), 1);
    await page.locator("#ledger-search").fill("");
    pass("Ledger search filters real records and handles an empty result");

    await page.locator('tbody [data-proof="ledger:r3"]').click();
    assert.match(
      await page.locator(".record-sheet").textContent(),
      /2026-12-01T00:00:00\+05:00/,
    );
    await page.locator('[data-action="raw"]').click();
    assert.match(
      await page.locator("#source-content .json-view").textContent(),
      /"debit_minor": 4400000/,
    );
    await page.locator('[data-action="raw"]').click();
    assert.equal(await page.locator(".record-sheet").isVisible(), true);
    pass("Readable record and original JSON show the same exact ledger source");

    await page.locator('[data-action="next"]').click();
    assert.equal(await page.locator("#replay-range").inputValue(), "1");
    assert.equal(
      await page.locator(".trace-step.current").getAttribute("data-step"),
      "1",
    );
    assert.equal(
      await page.evaluate(() => document.activeElement.dataset.action),
      "next",
    );
    await scrub(3);
    assert.equal(await page.locator("#replay-range").inputValue(), "3");
    assert.equal(
      await page
        .locator('[data-tab="documents"]')
        .getAttribute("aria-selected"),
      "true",
    );
    assert.match(
      await page.locator(".paper-title").textContent(),
      /Поступление средств/,
    );
    await scrub(1);
    assert.equal(await page.locator("#scrub-value").textContent(), "1");
    await page.locator('[data-action="reset"]').click();
    assert.equal(await page.locator("#replay-range").inputValue(), "0");
    assert.equal(await page.locator(".analysis-intro").count(), 1);
    assert.equal(await page.locator('[data-tab="comparison"]').count(), 0);
    pass(
      "Step, forward/backward scrubbing and reset update sources and preserve keyboard focus",
    );

    await page.locator('[data-action="play"]').click();
    await page.waitForFunction(
      () => document.querySelectorAll(".finding").length === 2,
      {},
      { timeout: 15000 },
    );
    assert.equal(await page.locator("#replay-range").inputValue(), "6");
    assert.equal(await page.locator('[data-action="next"]').isDisabled(), true);
    assert.match(await page.locator(".result-strip").textContent(), /0,990/);
    assert.equal(
      await page.locator("#results").evaluate((el) => el.scrollTop),
      0,
    );
    assert.equal(
      await page.locator(".case-item.selected .case-complete").count(),
      1,
    );
    assert.equal(await page.locator(".comparison-card").count(), 2);
    assert.match(
      await page.locator(".comparison-pair").textContent(),
      /45\s000,00\sKZT/,
    );
    assert.match(
      await page.locator(".comparison-mismatch").textContent(),
      /44\s000,00\sKZT/,
    );
    await page.locator("#comparison-finding").selectOption("1");
    assert.match(
      await page.locator(".comparison-pair").textContent(),
      /30\.11\.2026/,
    );
    assert.match(
      await page.locator(".comparison-mismatch").textContent(),
      /01\.12\.2026/,
    );
    await page.locator("#comparison-finding").selectOption("0");
    await screenshot("comparison");
    pass(
      "Confirmed findings reveal side-by-side evidence with only the booked mismatch marked",
    );
    await page.locator('[data-tab="documents"]').click();
    await page.locator("#document-select").selectOption("1");
    await page.locator("#results").evaluate((el) => (el.scrollTop = 0));
    await screenshot("findings");
    pass(
      "Recorded playback completes with the real F1, reward and two findings",
    );

    await evidence("ledger:r3").click();
    assert.equal(await page.locator(".record-sheet").isVisible(), true);
    assert.equal(
      await page.locator('.selected-row [data-proof="ledger:r3"]').count(),
      1,
    );
    assert.equal(await page.locator("dialog[open]").count(), 0);
    assert.equal(await page.locator(".finding-detail").isVisible(), true);
    await page.locator(".record-sheet summary").click();
    assert.match(
      await page.locator(".record-sheet .json-view").textContent(),
      /4400000/,
    );
    await page.locator(".record-sheet summary").click();
    await page.locator("#results").evaluate((el) => (el.scrollTop = 0));
    await screenshot("evidence");
    pass(
      "Finding evidence opens inline beside the conclusion with original amount and timestamp",
    );

    await evidence("doc:payment-doc-1").click();
    assert.equal(await page.locator("#document-select").inputValue(), "1");
    await evidence("fx:2026-11-30:USD:KZT").click();
    assert.match(
      await page.locator(".fx-register .selected-row").textContent(),
      /450/,
    );
    await evidence("policy:accounting").click();
    assert.match(
      await page.locator(".policy-sheet").textContent(),
      /ROUND_HALF_EVEN/,
    );
    await page.locator('[data-finding="1"]').click();
    assert.match(
      await page.locator(".finding-value").textContent(),
      /45\s000,00/,
    );
    await evidence("manifest:episode").click();
    assert.equal(await page.locator(".policy-sheet details[open]").count(), 1);
    pass(
      "Payment, FX, accounting policy and period evidence resolve to their public sources",
    );

    const downloadPromise = page.waitForEvent("download");
    await page.locator('[data-action="download-findings"]').click();
    const download = await downloadPromise;
    assert.match(download.suggestedFilename(), /fx-period-findings.json$/);
    const stream = await download.createReadStream();
    let body = "";
    for await (const chunk of stream) body += chunk;
    assert.equal(JSON.parse(body).findings.length, 2);
    pass("Findings export downloads valid JSON from the chosen episode");

    await scrub(2);
    await page.locator('[data-case="1"]').click();
    assert.equal(await page.locator("#replay-range").inputValue(), "0");
    await finish();
    await page.locator('[data-case="0"]').click();
    assert.equal(await page.locator("#replay-range").inputValue(), "2");
    pass("Switching cases restores each investigation position");

    const counts = [2, 2, 0, 4, 1, 1, 1, 1, 0, 4];
    for (let i = 0; i < counts.length; i++) {
      await page.locator(`[data-case="${i}"]`).click();
      await finish();
      assert.equal(await page.locator(".finding").count(), counts[i]);
      assert.doesNotMatch(
        await page.locator("#app").textContent(),
        /undefined|NaN/,
      );
      if (!counts[i]) {
        assert.match(
          await page.locator(".clean-conclusion").textContent(),
          /Нарушений\s*не обнаружено/,
        );
        assert.equal(await page.locator('[data-tab="comparison"]').count(), 0);
      } else {
        for (let index = 0; index < counts[i]; index++) {
          if (counts[i] > 1)
            await page
              .locator("#comparison-finding")
              .selectOption(String(index));
          assert.equal(await page.locator(".comparison-mismatch").count(), 1);
          assert.doesNotMatch(
            await page.locator(".comparison-pair").textContent(),
            /undefined|NaN/,
          );
        }
      }
    }
    pass(
      "All ten cases show actual findings and comparisons with clean companies left unmarked",
    );
    await page.locator('[data-case="3"]').click();
    await page.locator('[data-tab="ledger"]').click();
    const before = await page.locator(".data-table tbody").textContent();
    await page.locator('[data-action="page-next"]').click();
    assert.notEqual(
      await page.locator(".data-table tbody").textContent(),
      before,
    );
    await page.locator('[data-action="page-prev"]').click();
    assert.equal(await page.locator(".data-table tbody").textContent(), before);
    await scrub(2);
    assert.match(
      await page.locator(".table-pagination").textContent(),
      /49–56/,
    );
    pass("Large ledger pagination and recorded-page following work");

    await page.locator('[data-tab="documents"]').focus();
    await page.keyboard.press("ArrowRight");
    assert.equal(
      await page.locator('[data-tab="ledger"]').getAttribute("aria-selected"),
      "true",
    );
    await page.keyboard.press("End");
    assert.equal(
      await page.locator('[data-tab="policy"]').getAttribute("aria-selected"),
      "true",
    );
    pass("Source tabs support keyboard navigation");

    await page.locator('[data-nav="verification"]').click();
    await page.locator(".audit-workbench").waitFor();
    assert.equal(await page.locator(".benchmark-table tbody tr").count(), 4);
    const ids = new Set();
    for (const group of ["C", "D", "R", "G"]) {
      await page.locator(`[data-group="${group}"]`).click();
      assert.equal(await page.locator("[data-check]").count(), 20);
      for (const id of await page
        .locator("[data-check]")
        .evaluateAll((els) => els.map((el) => el.dataset.check)))
        ids.add(id);
      assert.match(
        await page.locator(".check-inspector").textContent(),
        /passed/,
      );
      assert.equal(
        await page
          .locator(".check-row")
          .first()
          .textContent()
          .then((t) => t.length > 15),
        true,
      );
    }
    assert.equal(ids.size, 80);
    await page.locator('[data-group="C"]').click();
    await page.locator('[data-check="C02"]').click();
    assert.match(
      await page.locator(".check-inspector .section-kicker").textContent(),
      /C02/,
    );
    await page.locator('[data-check="C01"]').click();
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
    await screenshot("verification");
    pass(
      "All 80 checks expose named procedures, expected outcomes and executed results across four groups",
    );

    await page.locator('[data-nav="architecture"]').click();
    assert.equal(await page.locator(".flow-card").count(), 4);
    assert.equal(await page.locator(".tool-register>div").count(), 5);
    await page.locator('[data-nav="guide"]').click();
    assert.equal(await page.locator(".guide-steps li").count(), 4);
    assert.equal(await page.locator("video").count(), 1);
    const pdf = await page.request.get(base + "/assets/presentation.pdf");
    assert.equal(pdf.status(), 200);
    await page.locator('[data-action="start-guide"]').click();
    assert.equal(await page.locator("#episode-select").inputValue(), "0");
    assert.equal(await page.locator("#replay-range").inputValue(), "0");
    pass(
      "Architecture and jury guide explain the environment and open the exact example",
    );

    for (const width of [320, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const route of [
        "workspace",
        "verification",
        "architecture",
        "guide",
      ]) {
        await open(route);
        assert.equal(
          await page.evaluate(
            () => document.documentElement.scrollWidth > innerWidth,
          ),
          false,
          `Overflow ${width}/${route}`,
        );
        if (route === "workspace") {
          await finish();
          assert.equal(
            await page.evaluate(
              () => document.documentElement.scrollWidth > innerWidth,
            ),
            false,
            `Results overflow ${width}`,
          );
        }
      }
    }
    pass("All sections and results fit 320, 390, 768, 1024 and 1440 px");

    await page.setViewportSize({ width: 390, height: 844 });
    await open();
    await page.locator("#episode-select").selectOption("1");
    await page.locator("#episode-select").selectOption("0");
    await finish();
    assert.equal(await page.locator(".comparison-mismatch").isVisible(), true);
    await page.locator("#comparison-finding").selectOption("1");
    assert.match(
      await page.locator(".comparison-mismatch").textContent(),
      /01\.12\.2026/,
    );
    await page.locator('[data-mobile="analysis"]').click();
    assert.equal(await page.locator(".analysis-workspace").isVisible(), true);
    await page.locator('[data-finding="1"]').click();
    await evidence("ledger:r3").click();
    assert.equal(await page.locator(".source-workspace").isVisible(), true);
    assert.equal(await page.locator(".analysis-workspace").isVisible(), false);
    assert.equal(await page.locator(".record-sheet").isVisible(), true);
    await page.locator('[data-mobile="analysis"]').click();
    assert.equal(
      await page.locator('[data-finding="1"]').getAttribute("aria-pressed"),
      "true",
    );
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
    await screenshot("mobile");
    pass(
      "Mobile switches between evidence and analysis while preserving the selected conclusion",
    );

    const report = await context.newPage();
    try {
      await report.goto(base + "/assets/verification.html", {
        waitUntil: "networkidle",
      });
      assert.equal(
        await report.evaluate(
          () => getComputedStyle(document.body).backgroundColor,
        ),
        "rgb(17, 24, 39)",
      );
    } finally {
      await report.close();
    }
    pass("Full verification report loads its stylesheet");
    assert.deepEqual(errors, []);
    assert.deepEqual(failures, []);
    pass("No JavaScript, console or local resource errors");
    const result = {
      url: base,
      passed: checks.length,
      checks,
      browser_errors: errors,
      failed_requests: failures,
    };
    await mkdir(resolve(root, "artifacts"), { recursive: true });
    await writeFile(
      resolve(root, "artifacts/web-check.json"),
      JSON.stringify(result, null, 2) + "\n",
    );
    return result;
  } finally {
    await page.close();
  }
};
