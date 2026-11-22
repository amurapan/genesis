/** Real-browser QA for the reversible WebGL/HTML film and its native navigation. */
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
export default async ({ context }) => {
  const base = process.env.SLED_WEB_URL || "http://127.0.0.1:4174",
    root = process.env.SLED_REPO || process.cwd();
  const page = await context.newPage();
  await page.route("**/*", (r) => r.continue());
  const checks = [],
    errors = [],
    failed = [];
  let performanceReport, preferences;
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  page.on("response", (r) => {
    if (r.url().startsWith(base) && r.status() >= 400)
      failed.push(`${r.status()} ${r.url()}`);
  });
  const pass = (name) => {
      checks.push(name);
      console.log("OK " + name);
    },
    shot = async (name) => {
      await page.waitForTimeout(500);
      return page.screenshot({
        path: resolve(root, "docs/images", name + ".png"),
      });
    };
  const ready = async () =>
    page.waitForFunction(
      () => window.sledFilm && !window.sledFilm.snapshot().loading,
    );
  const state = () => page.evaluate(() => window.sledFilm.snapshot());
  const scroll = async (p) => {
    await page.evaluate((t) => {
      const f = document.querySelector("#film"),
        s = document.querySelector("#film-stage");
      window.scrollTo({
        top: f.offsetTop + (f.offsetHeight - s.offsetHeight) * t,
        behavior: "instant",
      });
    }, p);
    await page.waitForFunction(
      (t) => Math.abs(window.sledFilm.snapshot().progress - t) < 0.0003,
      p,
    );
  };
  const go = async (url = base) => {
    await page.goto(url, { waitUntil: "networkidle" });
    await ready();
  };
  await mkdir(resolve(root, "docs/images"), { recursive: true });
  try {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.bringToFront();
    await go();
    preferences = await page.evaluate(() => {
      const old = ["sled-cinema-mode", "sled-motion"].map((k) =>
        localStorage.getItem(k),
      );
      localStorage.removeItem("sled-cinema-mode");
      localStorage.removeItem("sled-motion");
      return old;
    });
    await page.reload({ waitUntil: "networkidle" });
    await ready();
    assert.equal((await state()).mode, "cinematic");
    assert.equal((await state()).graphics.threeRevision, "180");
    assert.equal(await page.locator("#world canvas").count(), 1);
    assert.equal(
      await page.locator("[data-shot=opening]").getAttribute("aria-hidden"),
      "false",
    );
    await shot("landing");
    pass("Landing renders a real Three.js archive with a readable first frame");
    await page.locator("[data-shot=opening] .pill").hover();
    await page.waitForTimeout(250);
    assert.notEqual(
      await page
        .locator("[data-shot=opening] .pill")
        .evaluate((e) => getComputedStyle(e).backgroundColor),
      "rgb(215, 246, 222)",
    );
    await page.locator("#menu-toggle").click();
    assert.equal(await page.locator("#site-menu").isVisible(), true);
    assert.equal(
      await page.locator("#menu-toggle").getAttribute("aria-expanded"),
      "true",
    );
    await page.keyboard.press("Escape");
    assert.equal(await page.locator("#site-menu").isVisible(), false);
    assert.equal(
      await page.evaluate(() => document.activeElement.id),
      "menu-toggle",
    );
    pass(
      "Hover and menu interactions work, with Escape returning keyboard focus",
    );
    await page.locator("[data-shot=opening] a[href='#detail']").click();
    await page.waitForFunction(
      () => Math.abs(window.sledFilm.snapshot().progress - 0.19) < 0.001,
    );
    assert.equal(new URL(page.url()).hash, "#detail");
    await page.locator("#menu-toggle").click();
    await page.locator('#site-menu a[href="#duplicates"]').click();
    await page.waitForFunction(
      () => Math.abs(window.sledFilm.snapshot().progress - 0.65) < 0.001,
    );
    assert.equal((await state()).active, "duplicate");
    await page.waitForTimeout(400);
    await page.goBack({ waitUntil: "commit" });
    await page.waitForFunction(
      () => Math.abs(window.sledFilm.snapshot().progress - 0.19) < 0.001,
    );
    assert.equal(new URL(page.url()).hash, "#detail");
    pass(
      "Native anchors and browser Back return to the correct film composition",
    );
    const keyFrames = [];
    for (const p of [0, 0.19, 0.29, 0.43, 0.555, 0.65, 0.82, 0.97]) {
      await scroll(p);
      const s = await state();
      assert.equal(s.graphics.progress, s.progress);
      assert.ok(s.graphics.calls <= 45);
      assert.ok(s.graphics.triangles < 20000);
      keyFrames.push(s);
    }
    assert.ok(
      Math.abs(
        keyFrames[3].graphics.camera[0] - keyFrames[5].graphics.camera[0],
      ) >= 8,
    );
    pass(
      "The camera approaches, unfolds, trucks to a second case and returns; WebGL shares the HTML timeline",
    );
    await scroll(0.43);
    const forward = await page.evaluate(() => ({
      graphics: window.sledFilm.snapshot().graphics,
      css: document.querySelector("[data-preview=fx]").style.transform,
      copy: document.querySelector("[data-shot=fx]").style.cssText,
      y: scrollY,
    }));
    await scroll(0.82);
    await scroll(0.43);
    const reverse = await page.evaluate(() => ({
      graphics: window.sledFilm.snapshot().graphics,
      css: document.querySelector("[data-preview=fx]").style.transform,
      copy: document.querySelector("[data-shot=fx]").style.cssText,
      y: scrollY,
    }));
    assert.deepEqual(reverse.graphics.matrix, forward.graphics.matrix);
    assert.deepEqual(reverse.graphics.cssMatrix, forward.graphics.cssMatrix);
    assert.equal(reverse.css, forward.css);
    assert.equal(reverse.copy, forward.copy);
    assert.equal(reverse.y, forward.y);
    pass(
      "Reverse scrolling reproduces exact camera matrices, CSS 3D transforms and text composition",
    );
    for (const [a, b] of [
      [0.41, 0.46],
      [0.63, 0.68],
    ]) {
      await scroll(a);
      const before = (await state()).graphics;
      await scroll(b);
      const after = (await state()).graphics;
      assert.deepEqual(after.matrix, before.matrix);
      assert.deepEqual(after.cssMatrix, before.cssMatrix);
    }
    await scroll(0.43);
    await page.waitForTimeout(500);
    const idle = (await state()).renders;
    await page.waitForTimeout(500);
    assert.equal((await state()).renders, idle);
    pass(
      "Both case pauses are stationary, and the renderer stops requesting frames while idle",
    );
    const fx = page.locator("[data-preview=fx]");
    await fx.locator("[data-screen-tab=evidence]").click();
    assert.equal(
      await fx.locator("[data-screen-content=evidence]").isVisible(),
      true,
    );
    assert.match(
      await fx.locator("[data-screen-content=evidence]").textContent(),
      /44 000 KZT/,
    );
    await page.keyboard.press("ArrowLeft");
    assert.equal(
      await fx
        .locator("[data-screen-tab=compare]")
        .getAttribute("aria-selected"),
      "true",
    );
    await shot("story");
    await scroll(0.65);
    await page
      .locator("[data-preview=duplicate] [data-screen-tab=evidence]")
      .click();
    assert.match(
      await page
        .locator("[data-preview=duplicate] [data-screen-content=evidence]")
        .textContent(),
      /500 KZT из 600 KZT/,
    );
    await page
      .locator("[data-preview=duplicate] [data-screen-tab=compare]")
      .click();
    await shot("landing-duplicate");
    pass(
      "Both interfaces are interactive HTML, including keyboard tabs and real evidence values",
    );
    const response = await page.request.get(base + "/data/demo.json");
    const data = await response.json();
    assert.equal(
      data.cases[0].submission.findings[0].claimed_amount_minor,
      100000,
    );
    assert.equal(
      data.cases[1].submission.findings[1].claimed_amount_minor,
      10000,
    );
    pass(
      "Displayed financial examples agree with the recorded public episodes",
    );
    await scroll(0.29);
    await shot("landing-unfold");
    await scroll(0.82);
    await shot("landing-proof");
    await scroll(0.43);
    await page.locator("[data-shot=fx] .pill").click();
    await page.locator("#app").waitFor({ state: "visible" });
    assert.equal(new URL(page.url()).searchParams.get("episode"), "fx-period");
    assert.match(await page.locator("#app h1").textContent(), /Валюта/);
    await page.goBack({ waitUntil: "commit" });
    await ready();
    await page.waitForFunction(
      () => Math.abs(window.sledFilm.snapshot().progress - 0.43) < 0.005,
    );
    pass(
      "The case opens in the laboratory, and browser Back restores the film position",
    );
    await scroll(0);
    await page.locator("body").click({ position: { x: 8, y: 400 } });
    await page.keyboard.press("PageDown");
    await page.waitForFunction(
      () => window.sledFilm.snapshot().progress > 0.02,
    );
    pass("PageDown uses the normal document scrollbar");
    const pin = await page.evaluate(() => {
      const f = document.querySelector("#film"),
        s = document.querySelector("#film-stage");
      return {
        top: f.offsetTop,
        end: f.offsetTop + f.offsetHeight - s.offsetHeight,
        height: s.offsetHeight,
      };
    });
    for (const y of [
      pin.top,
      pin.top + 2,
      pin.end - 2,
      pin.end,
      pin.end + 2,
      pin.end + 12,
    ]) {
      await page.evaluate((y) => scrollTo({ top: y, behavior: "instant" }), y);
      await page.waitForTimeout(40);
      const actual = await page
        .locator("#film-stage")
        .evaluate((e) => e.getBoundingClientRect().top);
      assert.ok(
        Math.abs(actual - -Math.max(0, y - pin.end)) < 2.5,
        `Pin seam at ${y}: ${actual}`,
      );
    }
    pass(
      "Sticky entry and release are continuous at the beginning and end of the film",
    );
    await page.evaluate(() => scrollTo({ top: 0, behavior: "instant" }));
    await scroll(0);
    const start = (await state()).renders;
    const intervals = await page.evaluate(async () => {
      const f = document.querySelector("#film"),
        s = document.querySelector("#film-stage"),
        travel = f.offsetHeight - s.offsetHeight;
      const out = [];
      let previous = performance.now();
      for (let i = 0; i < 120; i++) {
        await new Promise(requestAnimationFrame);
        const now = performance.now();
        out.push(now - previous);
        previous = now;
        scrollTo({ top: travel * (i / 119), behavior: "instant" });
      }
      await new Promise(requestAnimationFrame);
      await new Promise(requestAnimationFrame);
      return out;
    });
    const afterPerf = await state(),
      times = afterPerf.renderMillis.slice(
        -Math.min(300, afterPerf.renders - start),
      );
    const percentile = (a, p) =>
      [...a].sort((a, b) => a - b)[Math.floor((a.length - 1) * p)];
    performanceReport = {
      environment:
        "Headless Chromium on this workstation; not a hardware-wide FPS guarantee",
      graphics_quality: afterPerf.graphics.quality,
      pixel_ratio: afterPerf.graphics.pixelRatio,
      scroll_frames: intervals.length,
      frame_interval_p50_ms: percentile(intervals, 0.5),
      frame_interval_p95_ms: percentile(intervals, 0.95),
      render_cpu_p50_ms: percentile(times, 0.5),
      render_cpu_p95_ms: percentile(times, 0.95),
      max_draw_calls: Math.max(...keyFrames.map((x) => x.graphics.calls)),
      max_triangles: Math.max(...keyFrames.map((x) => x.graphics.triangles)),
    };
    assert.ok(
      performanceReport.render_cpu_p95_ms < 35,
      JSON.stringify(performanceReport),
    );
    pass(
      "A 120-frame scroll trace records rendering cost and stays within the tested CPU budget",
    );
    for (const width of [320, 390, 768, 1024, 1440]) {
      await page.setViewportSize({
        width,
        height: width === 768 ? 1024 : 1000,
      });
      await go();
      for (const p of [0, 0.19, 0.29, 0.43, 0.65, 0.82, 0.97]) {
        await scroll(p);
        const bounds = await page.evaluate(() => {
          const current = [...document.querySelectorAll("[data-shot]")].find(
              (e) => !e.inert,
            ),
            copy = current?.querySelector(".shot-copy").getBoundingClientRect(),
            screen = [...document.querySelectorAll("[data-preview]")]
              .find((e) => !e.inert && getComputedStyle(e).display !== "none")
              ?.getBoundingClientRect();
          return {
            overflow: document.documentElement.scrollWidth > innerWidth + 1,
            copy: copy
              ? { top: copy.top, bottom: copy.bottom, right: copy.right }
              : null,
            screen: screen
              ? {
                  left: screen.left,
                  right: screen.right,
                  top: screen.top,
                  bottom: screen.bottom,
                }
              : null,
            width: innerWidth,
            height: innerHeight,
          };
        });
        assert.equal(bounds.overflow, false, `Page overflow at ${width}/${p}`);
        assert.ok(
          bounds.copy.bottom < bounds.height - 50,
          `Copy clipped at ${width}/${p}`,
        );
        if (bounds.screen) {
          assert.ok(
            bounds.screen.left >= -1 && bounds.screen.right <= bounds.width + 1,
            `Screen clipped ${width}/${p}: ${JSON.stringify(bounds)}`,
          );
          assert.ok(
            width <= 900
              ? bounds.screen.top >= bounds.copy.bottom - 5
              : bounds.screen.left >= bounds.copy.right - 5,
            `Text and scene collide ${width}/${p}: ${JSON.stringify(bounds)}`,
          );
        }
      }
    }
    pass(
      "Seven scenes fit five viewport widths, with readable text separated from the project interface",
    );
    await page.setViewportSize({ width: 390, height: 844 });
    await go();
    await shot("landing-mobile");
    await scroll(0.43);
    await page.locator("[data-preview=fx] [data-screen-tab=evidence]").click();
    await shot("landing-mobile-case");
    assert.equal(
      await page
        .locator("[data-preview=fx] [data-screen-content=evidence]")
        .isVisible(),
      true,
    );
    pass(
      "Mobile retains the interactive project and a dedicated readable text area",
    );
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.waitForFunction(
      () => window.sledFilm.snapshot().mode === "static",
    );
    assert.equal(await page.locator("#world canvas").count(), 0);
    assert.equal(await page.locator("[data-shot][inert]").count(), 0);
    assert.equal(await page.locator(".preview-home .case-preview").count(), 2);
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth + 1,
      ),
      false,
    );
    await page.locator("[data-preview=fx] [data-screen-tab=compare]").click();
    assert.equal(
      await page
        .locator("[data-preview=fx] [data-screen-content=compare]")
        .isVisible(),
      true,
    );
    pass(
      "Reduced motion becomes a normal readable page with both working examples and no WebGL",
    );
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.waitForFunction(
      () =>
        window.sledFilm.snapshot().mode === "cinematic" &&
        !window.sledFilm.snapshot().loading,
    );
    await page.locator("#menu-toggle").click();
    await page.locator("#motion-toggle").click();
    assert.equal((await state()).mode, "static");
    await page.reload({ waitUntil: "networkidle" });
    await ready();
    assert.equal((await state()).mode, "static");
    await page.locator("#menu-toggle").click();
    await page.locator("#motion-toggle").click();
    await page.waitForFunction(
      () =>
        window.sledFilm.snapshot().mode === "cinematic" &&
        !window.sledFilm.snapshot().loading,
    );
    pass("The motion choice persists and can restore the complete 3D film");
    await page.setViewportSize({ width: 844, height: 390 });
    await page.waitForFunction(
      () => window.sledFilm.snapshot().mode === "static",
    );
    assert.equal(await page.locator(".preview-home .case-preview").count(), 2);
    pass("Short landscape screens use the readable non-pinned layout");
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(base + "/#workspace", { waitUntil: "networkidle" });
    await page.locator("#app").waitFor({ state: "visible" });
    assert.match(page.url(), /lab(?:\.html)?#workspace/);
    pass("Legacy laboratory links remain usable");
    await go();
    await page.bringToFront();
    await page.evaluate(() =>
      document
        .querySelector("#world canvas")
        .getContext("webgl2")
        .getExtension("WEBGL_lose_context")
        .loseContext(),
    );
    await page.waitForFunction(
      () => window.sledFilm.snapshot().mode === "static",
    );
    assert.equal(await page.locator(".preview-home .case-preview").count(), 2);
    assert.equal(await page.locator("[data-shot][inert]").count(), 0);
    await page.locator("[data-preview=fx] [data-screen-tab=evidence]").click();
    assert.equal(
      await page
        .locator("[data-preview=fx] [data-screen-content=evidence]")
        .isVisible(),
      true,
    );
    pass(
      "A real WebGL context loss restores readable content and working evidence tabs",
    );
    const fallback = await context.newPage();
    try {
      await fallback.addInitScript(() => {
        const original = HTMLCanvasElement.prototype.getContext;
        HTMLCanvasElement.prototype.getContext = function (type, ...args) {
          return type === "webgl2" ? null : original.call(this, type, ...args);
        };
      });
      await fallback.goto(base, { waitUntil: "networkidle" });
      await fallback.waitForFunction(
        () =>
          window.sledFilm?.snapshot().mode === "static" &&
          window.sledFilm.snapshot().errors.length > 0,
      );
      assert.equal(await fallback.locator("[data-shot][inert]").count(), 0);
      assert.equal(
        await fallback.locator(".preview-home .case-preview").count(),
        2,
      );
    } finally {
      await fallback.close();
    }
    pass(
      "Unavailable WebGL gracefully retains the complete content and case links",
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(failed, []);
    pass("No JavaScript, console or resource errors in the supported path");
    const result = {
      url: base,
      passed: checks.length,
      checks,
      browser_errors: errors,
      failed_requests: failed,
      performance: performanceReport,
    };
    await mkdir(resolve(root, "artifacts"), { recursive: true });
    await writeFile(
      resolve(root, "artifacts/landing-check.json"),
      JSON.stringify(result, null, 2) + "\n",
    );
    return result;
  } catch (error) {
    await page
      .screenshot({
        path: resolve(root, "artifacts/landing-failure.png"),
        timeout: 10000,
      })
      .catch(() => {});
    throw new Error("After " + checks.at(-1) + "\n" + error.stack);
  } finally {
    if (preferences)
      await page
        .evaluate(
          (values) =>
            ["sled-cinema-mode", "sled-motion"].forEach((k, i) =>
              values[i] === null
                ? localStorage.removeItem(k)
                : localStorage.setItem(k, values[i]),
            ),
          preferences,
        )
        .catch(() => {});
    await page.close();
  }
};
