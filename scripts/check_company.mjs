/** Browser checks for the company overview, document handoff and recorded playback. */
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

export default async ({ context }) => {
  const base = process.env.SLED_WEB_URL || "http://127.0.0.1:4174";
  const root = process.env.SLED_REPO || process.cwd();
  const shots = resolve(root, "docs/images");
  const page = await context.newPage();
  const errors = [];
  const checks = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => r.continue());
  await mkdir(shots, { recursive: true });
  try {
    const company = () => page.locator(".company-page");
    const scene = () => page.locator("#company-scene");
    const choose = (source) =>
      page.locator(`[data-company-source="${source}"]`).click();
    const currentStage = () =>
      page.locator(".lab-flow [aria-current='step']").textContent();
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.bringToFront();
    await page.goto(base);
    await page.waitForFunction(
      () => window.sledFilm && !window.sledFilm.snapshot().loading,
    );
    await page.screenshot({ path: resolve(shots, "landing.png") });
    await Promise.all([
      page.waitForURL(/episode=fx-period#workspace$/),
      page.locator("[data-shot='opening'] .pill").click(),
    ]);
    await page.locator(".document-sheet").waitFor();
    assert.match(
      await page.locator(".case-header h1").textContent(),
      /Валюта и граница периода/,
    );
    assert.equal(await scene().count(), 0);
    await page.locator(".transport-bar [data-action='play']").click();
    await page.locator(".comparison-mismatch").waitFor({ timeout: 11000 });
    assert.match(
      await page.locator(".comparison-mismatch").textContent(),
      /44\s000,00/,
    );
    checks.push(
      "The primary entry opens the FX documents and one click replays the case through comparison",
    );

    await page.setViewportSize({ width: 320, height: 568 });
    await page.goto(base);
    assert.match(
      await page.locator(".header-lab").getAttribute("href"),
      /episode=fx-period#workspace$/,
    );
    await page.locator("#menu-toggle").click();
    assert.equal(
      await page
        .locator("#site-menu")
        .evaluate((menu) => menu.getBoundingClientRect().bottom <= innerHeight),
      true,
    );
    await Promise.all([
      page.waitForURL(/episode=generated#company$/),
      page.locator("#site-menu a[href$='#company']").click(),
    ]);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await company().waitFor();
    assert.equal(
      await page.locator("#company-title").textContent(),
      "Сгенерированная компания",
    );
    assert.match(await currentStage(), /Компания/);
    assert.equal(await page.locator(".case-select option").count(), 10);
    assert.deepEqual(
      await page.locator(".company-source strong").allTextContents(),
      ["40", "45", "305"],
    );
    assert.equal(await page.locator(".comparison-mismatch").count(), 0);
    checks.push(
      "Company is reachable from the mobile landing menu, with actual counts and no results shown",
    );

    await page
      .locator("#company-scene[data-renderer='webgl'] canvas")
      .waitFor({ timeout: 8000 });
    const canvas = scene().locator("canvas");
    await page.waitForTimeout(1400);
    const before = await canvas.screenshot();
    await choose("payments");
    assert.match(
      await page.locator("#company-sample").textContent(),
      /Первичный платёж/,
    );
    await page.waitForTimeout(750);
    const after = await canvas.screenshot();
    assert.notDeepEqual(before, after);
    await page.waitForTimeout(350);
    assert.deepEqual(await canvas.screenshot(), after);
    await page.screenshot({ path: resolve(shots, "company.png") });
    const size = await canvas.boundingBox();
    await canvas.click({
      position: { x: size.width * 0.72, y: size.height * 0.59 },
    });
    assert.equal(
      await page
        .locator('[data-company-source="ledger"]')
        .getAttribute("aria-pressed"),
      "true",
    );
    await choose("payments");
    checks.push(
      "The 3D view changes with the selected stack and stays still when idle",
    );

    await page.locator("[data-action='company-documents']").click();
    await page.waitForURL(/#workspace$/);
    await page.locator(".paper-title").waitFor();
    assert.match(
      await page.locator(".paper-title").textContent(),
      /Поступление средств/,
    );
    assert.match(await currentStage(), /Прогон/);
    assert.equal(await canvas.count(), 0);
    checks.push(
      "Sources opens the selected real document and releases the 3D view",
    );

    await page.locator(".lab-flow a[href='#company']").click();
    await company().waitFor();
    await page
      .locator("#episode-select")
      .selectOption({ label: "Валюта и граница периода" });
    assert.deepEqual(
      await page.locator(".company-source strong").allTextContents(),
      ["1", "1", "4"],
    );
    await page.locator("[data-action='company-run']").click();
    await page.locator(".lab[data-playing='true']").waitFor();
    assert.match(await currentStage(), /Прогон/);
    await page.locator(".comparison-mismatch").waitFor({ timeout: 11000 });
    assert.match(await currentStage(), /Сверка/);
    assert.match(
      await page.locator(".comparison-mismatch").textContent(),
      /44\s000,00/,
    );
    checks.push(
      "Playback starts from the company and automatically reveals the confirmed comparison",
    );

    await page.goto(base + "/lab.html");
    await page.locator(".document-sheet").waitFor();
    assert.match(
      await page.locator(".case-header h1").textContent(),
      /Валюта и граница периода/,
    );
    await page.goto(base + "/lab.html?episode=generated#company");
    await company().waitFor();
    assert.equal(
      await page.locator("#company-title").textContent(),
      "Сгенерированная компания",
    );
    assert.equal(new URL(page.url()).searchParams.get("episode"), "generated");
    for (const width of [320, 393, 768]) {
      await page.setViewportSize({ width, height: 770 });
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth,
        ),
        false,
      );
    }
    await page.setViewportSize({ width: 393, height: 848 });
    await choose("ledger");
    assert.match(
      await page.locator("#company-sample").textContent(),
      /Дебет|Кредит/,
    );
    await page.evaluate(() => scrollTo({ top: 0, behavior: "instant" }));
    await page.screenshot({
      path: resolve(shots, "company-mobile.png"),
      fullPage: true,
    });
    checks.push(
      "Bare Lab opens the FX case and the separate company view fits narrow viewports",
    );

    await page.addInitScript(() => {
      const getContext = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (kind, ...options) {
        return kind.startsWith("webgl")
          ? null
          : getContext.call(this, kind, ...options);
      };
    });
    await page.goto(base + "/lab.html?episode=fx-period#company");
    await page.waitForFunction(
      () =>
        document.querySelector("#company-scene")?.dataset.renderer === "css",
    );
    await choose("payments");
    assert.match(
      await page.locator("#company-sample").textContent(),
      /Первичный платёж/,
    );
    assert.equal(await page.locator(".company-fallback").isVisible(), true);
    assert.deepEqual(errors, []);
    checks.push(
      "A CSS model and source inspection work when WebGL is unavailable",
    );
    return { base, passed: checks.length, checks };
  } finally {
    await page.close();
  }
};
