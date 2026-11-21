/** Density and projection regression checks shared by Chromium and Firefox. */
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
export async function checkMobile(
  page,
  { base = "http://127.0.0.1:4174", engine = "chromium" } = {},
) {
  const checks = [],
    errors = [];
  const pass = (s) => {
    checks.push(s);
    console.log("OK " + s);
  };
  page.on("pageerror", (e) => errors.push(e.message));
  const resize = async (width, height) =>
    page.setViewportSize
      ? page.setViewportSize({ width, height })
      : page.setViewport({ width, height, deviceScaleFactor: 3 });
  const state = () => page.evaluate(() => sledFilm.snapshot());
  const scroll = async (p) => {
    await page.evaluate((v) => {
      window.mobileTarget = v;
      const f = document.querySelector("#film"),
        s = document.querySelector("#film-stage");
      scrollTo({
        top: f.offsetTop + (f.offsetHeight - s.offsetHeight) * v,
        behavior: "instant",
      });
    }, p);
    await page.waitForFunction(
      () =>
        Math.abs(sledFilm.snapshot().progress - window.mobileTarget) < 0.0003,
    );
  };
  const rect = () =>
    page.evaluate(() => {
      const el = [...document.querySelectorAll("[data-preview]")].find(
          (e) => !e.inert,
        ),
        r = el?.getBoundingClientRect(),
        host = document.querySelector("#spatial-ui").getBoundingClientRect();
      return r
        ? {
            left: r.left,
            top: r.top,
            width: r.width,
            height: r.height,
            hostLeft: host.left,
            hostTop: host.top,
          }
        : null;
    });
  const sameBox = (a, b, tolerance = 1) => {
    for (const k of ["left", "top", "width", "height"])
      assert.ok(Math.abs(a[k] - b[k]) < tolerance, `${k}: ${a[k]} vs ${b[k]}`);
  };
  await mkdir("artifacts/mobile-fix", { recursive: true });
  await resize(393, 873);
  await page.goto(base, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(
    () => window.sledFilm && !sledFilm.snapshot().loading,
  );
  await new Promise((r) => setTimeout(r, 600));
  let s = await state();
  assert.equal(s.mode, "cinematic");
  assert.ok(s.graphics.devicePixelRatio >= 2);
  assert.ok(s.graphics.pixelRatio >= 2);
  assert.ok(s.graphics.antialias);
  assert.ok(s.graphics.bufferWidth >= s.graphics.width * 1.99);
  const graphics = s.graphics;
  await page.screenshot({ path: `artifacts/mobile-fix/${engine}-opening.png` });
  pass("Retina canvas uses at least 2x resolution and antialiasing");
  const before = await page.evaluate(() => ({
    y: document.querySelector("#world").getBoundingClientRect().y,
    h: document.querySelector("#world").getBoundingClientRect().height,
    fov: sledFilm.snapshot().graphics.horizontalFov,
  }));
  // Model a collapsing toolbar: stable small viewport/travel, changing live viewport.
  await page.evaluate(() => {
    const f = document.querySelector("#film"),
      s = document.querySelector("#film-stage"),
      ref = document.querySelector("#viewport-reference");
    f.style.setProperty(
      "--scroll-travel",
      `${f.offsetHeight - s.offsetHeight}px`,
    );
    ref.style.height = `${ref.offsetHeight}px`;
  });
  await resize(393, 933);
  await new Promise((r) => setTimeout(r, 400));
  const after = await page.evaluate(() => ({
    y: document.querySelector("#world").getBoundingClientRect().y,
    h: document.querySelector("#world").getBoundingClientRect().height,
    stage: document.querySelector("#film-stage").getBoundingClientRect().height,
    vv: visualViewport.height,
    fov: sledFilm.snapshot().graphics.horizontalFov,
  }));
  assert.ok(Math.abs(after.stage - after.vv) < 2);
  assert.ok(after.y + after.h / 2 > before.y + before.h / 2 + 20);
  assert.ok(Math.abs(after.fov - before.fov) < 0.01);
  pass(
    "Live viewport fills the screen and lowers the scene without changing archive scale",
  );
  await scroll(0.43);
  const pBefore = (await state()).progress;
  await resize(393, 873);
  await new Promise((r) => setTimeout(r, 400));
  assert.ok(Math.abs((await state()).progress - pBefore) < 0.0003);
  pass(
    "A height-only viewport change preserves the current scene and scroll progress",
  );
  for (const [entry, flat, exit] of [
    [0.389, 0.391, 0.481],
    [0.609, 0.611, 0.701],
  ]) {
    await scroll(entry);
    const a = await rect();
    await scroll(flat);
    const b = await rect();
    sameBox(a, b);
    const box = (await state()).graphics.readingBox;
    assert.ok(box);
    sameBox(
      b,
      {
        left: b.hostLeft + box.left,
        top: b.hostTop + box.top,
        width: box.width,
        height: box.height,
      },
      0.5,
    );
    await scroll(exit - 0.002);
    const c = await rect();
    await scroll(exit);
    sameBox(c, await rect());
  }
  pass(
    "Both reading panels match their 3D planes within 1px at entry and exit",
  );
  await scroll(0.43);
  await page.click("[data-preview=fx] [data-screen-tab=evidence]");
  await page.keyboard.press("ArrowLeft");
  await scroll(0.44);
  await new Promise((r) => setTimeout(r, 600));
  assert.equal(
    await page.evaluate(() => document.activeElement?.dataset.screenTab),
    "compare",
  );
  assert.equal(
    await page.evaluate(() =>
      document
        .querySelector("[data-preview=fx] [data-screen-tab=compare]")
        .getAttribute("aria-selected"),
    ),
    "true",
  );
  pass(
    "Reading controls stay interactive and retain keyboard focus during a paused scene",
  );
  await scroll(0.43);
  const forward = await rect();
  await scroll(0.82);
  await scroll(0.43);
  sameBox(forward, await rect(), 0.1);
  await page.screenshot({ path: `artifacts/mobile-fix/${engine}-case.png` });
  pass("Reverse scrolling restores the same crisp panel and position");
  for (const [width, height] of [
    [320, 568],
    [360, 640],
    [375, 667],
    [393, 700],
    [393, 739],
    [320, 740],
    [360, 780],
    [393, 873],
    [412, 915],
  ]) {
    await resize(width, height);
    await page.evaluate(() => {
      document.querySelector("#film").style.removeProperty("--scroll-travel");
      document.querySelector("#viewport-reference").style.height = "";
    });
    for (const p of [0, 0.19, 0.29, 0.43, 0.65, 0.82, 0.97]) {
      await scroll(p);
      const bounds = await page.evaluate(() => {
        const copy = [...document.querySelectorAll("[data-shot]")]
            .find((e) => !e.inert)
            .querySelector(".shot-copy")
            .getBoundingClientRect(),
          el = [...document.querySelectorAll("[data-preview]")].find(
            (e) => !e.inert,
          ),
          r = el?.getBoundingClientRect();
        return {
          overflow: document.documentElement.scrollWidth > innerWidth + 1,
          copy: copy.bottom,
          screen: r
            ? { top: r.top, bottom: r.bottom, left: r.left, right: r.right }
            : null,
          w: innerWidth,
          h: innerHeight,
        };
      });
      assert.equal(bounds.overflow, false);
      assert.ok(bounds.copy < bounds.h - 50);
      if (bounds.screen) {
        assert.ok(bounds.screen.top >= bounds.copy - 1);
        assert.ok(bounds.screen.bottom <= bounds.h - 50);
        assert.ok(
          bounds.screen.left >= 0 && bounds.screen.right <= bounds.w + 1,
        );
      }
    }
  }
  pass(
    "Seven scenes fit nine phone sizes, including 568–739px portrait heights",
  );
  await resize(393, 700);
  await scroll(0.43);
  assert.equal((await state()).mode, "cinematic");
  const shortBefore = await rect();
  // A browser toolbar can cross 740px without changing the stable small viewport.
  await page.evaluate(() => {
    const f = document.querySelector("#film"),
      s = document.querySelector("#film-stage");
    f.style.setProperty(
      "--scroll-travel",
      `${f.offsetHeight - s.offsetHeight}px`,
    );
    document.querySelector("#viewport-reference").style.height = "700px";
    window.shortCanvas = document.querySelector("#world canvas");
  });
  const shortProgress = (await state()).progress;
  await resize(393, 780);
  await new Promise((r) => setTimeout(r, 400));
  assert.equal((await state()).mode, "cinematic");
  assert.ok(Math.abs((await state()).progress - shortProgress) < 0.0003);
  assert.equal(
    await page.evaluate(
      () =>
        document.documentElement.classList.contains("short-portrait") &&
        window.shortCanvas === document.querySelector("#world canvas"),
    ),
    true,
  );
  await resize(393, 700);
  await new Promise((r) => setTimeout(r, 400));
  sameBox(shortBefore, await rect());
  await page.evaluate(() => {
    document.querySelector("#film").style.removeProperty("--scroll-travel");
    document.querySelector("#viewport-reference").style.height = "";
  });
  pass(
    "Short portrait keeps its camera, canvas and scroll position when the toolbar crosses 740px",
  );
  for (const [entry, flat, exit] of [
    [0.389, 0.391, 0.481],
    [0.609, 0.611, 0.701],
  ]) {
    await scroll(entry);
    const before = await rect();
    await scroll(flat);
    sameBox(before, await rect());
    await scroll(exit - 0.002);
    const after = await rect();
    await scroll(exit);
    sameBox(after, await rect());
  }
  pass(
    "Compact HTML cards match their resized 3D frames at both reading transitions",
  );
  for (const [width, height] of [
    [320, 568],
    [393, 700],
  ]) {
    await resize(width, height);
    for (const [caseId, position] of [
      ["fx", 0.43],
      ["duplicate", 0.65],
    ]) {
      await scroll(position);
      const before = await rect();
      for (const tab of ["compare", "evidence"]) {
        await page.click(`[data-preview=${caseId}] [data-screen-tab=${tab}]`);
        const bounds = await page.evaluate(() => {
          const card = [...document.querySelectorAll("[data-preview]")].find(
            (e) => !e.inert,
          );
          const content = card.querySelector(".screen-content:not([hidden])");
          const footer = card
            .querySelector(".preview-footer")
            .getBoundingClientRect();
          return {
            bottom: Math.max(
              ...[...content.children].map(
                (e) => e.getBoundingClientRect().bottom,
              ),
            ),
            footerTop: footer.top,
            footerBottom: footer.bottom,
            cardBottom: card.getBoundingClientRect().bottom,
          };
        });
        assert.ok(
          bounds.bottom <= bounds.footerTop + 1,
          JSON.stringify(bounds),
        );
        assert.ok(
          bounds.footerBottom <= bounds.cardBottom + 1,
          JSON.stringify(bounds),
        );
      }
      await scroll(0.82);
      await scroll(position);
      sameBox(before, await rect());
    }
  }
  await page.screenshot({
    path: `artifacts/mobile-fix/${engine}-short-case.png`,
  });
  await scroll(0);
  await page.screenshot({
    path: `artifacts/mobile-fix/${engine}-short-opening.png`,
  });
  pass(
    "Both compact cards remain readable and interactive without content or footer collisions",
  );
  await resize(700, 393);
  await page.waitForFunction(() => sledFilm.snapshot().mode === "static");
  assert.equal(
    await page.evaluate(
      () => document.querySelectorAll(".preview-home .case-preview").length,
    ),
    2,
  );
  await resize(393, 700);
  await page.waitForFunction(
    () =>
      sledFilm.snapshot().mode === "cinematic" && !sledFilm.snapshot().loading,
  );
  pass(
    "Rotating a short screen restores full 3D in portrait and readable content in landscape",
  );
  assert.deepEqual(errors, []);
  assert.deepEqual((await state()).errors, []);
  pass("No page errors or fallback failures");
  const result = {
    url: base,
    engine,
    passed: checks.length,
    checks,
    graphics,
    limitations:
      "Desktop engine at mobile viewport sizes and 3x density. Toolbar size changes are modeled; this is not a physical Android test.",
  };
  await writeFile(
    `artifacts/mobile-fix/${engine}-checks.json`,
    JSON.stringify(result, null, 2) + "\n",
  );
  return result;
}
export default async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 393, height: 873 },
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
  });
  try {
    const page = await context.newPage();
    await page.route("**/*", (r) => r.continue());
    await page.bringToFront();
    return await checkMobile(page, {
      base: process.env.SLED_WEB_URL,
      engine: "chromium",
    });
  } finally {
    await context.close();
  }
};
