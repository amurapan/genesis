import { sample, shotRanges, clamp } from "./cinema/timeline.js";
// Keep previously shared laboratory links usable.
function redirectLegacy() {
  if (
    ["company", "workspace", "architecture", "guide"].includes(
      location.hash.slice(1),
    ) ||
    new URLSearchParams(location.search).has("episode")
  ) {
    const target = new URL("lab.html", location.href);
    target.hash = location.hash;
    target.search = location.search;
    location.replace(target);
    return true;
  }
  return false;
}
const redirecting = redirectLegacy();
const root = document.documentElement,
  film = document.querySelector("#film"),
  stage = document.querySelector("#film-stage"),
  world = document.querySelector("#world"),
  spatial = document.querySelector("#spatial-ui");
const shots = [...document.querySelectorAll("[data-shot]")],
  previews = [...document.querySelectorAll("[data-preview]")];
const homes = previews.map((el) => el.parentElement),
  anchors = shotRanges.map(({ anchor }) => document.getElementById(anchor));
const menu = document.querySelector("#site-menu"),
  menuButton = document.querySelector("#menu-toggle"),
  shade = document.querySelector("#menu-shade"),
  motionButton = document.querySelector("#motion-toggle");
const viewportReference = document.querySelector("#viewport-reference");
// Portrait phones keep the film even when browser controls reduce its height.
// The stable small viewport also keeps toolbar motion from changing layouts.
const compactViewport = () => {
  const h = viewportReference.getBoundingClientRect().height;
  return h < 740 && innerWidth > h;
};
function syncPortraitLayout() {
  const h = viewportReference.getBoundingClientRect().height;
  root.classList.toggle("short-portrait", h < 740 && innerWidth <= h);
  root.dataset.portraitFov = String(clamp(40 + ((740 - h) / 172) * 22, 40, 74));
}
syncPortraitLayout();
const reduced = matchMedia("(prefers-reduced-motion: reduce)");
let stored;
try {
  stored = localStorage.getItem("sled-cinema-mode");
  if (!stored && localStorage.getItem("sled-motion") === "off") stored = "off";
} catch {}
let engine = null,
  frame = 0,
  epoch = 0,
  cinematic = false,
  loading = false,
  failed = false,
  menuOpen = false,
  progress = 0,
  lastState = sample(0),
  sizeDirty = true,
  wasCompact = compactViewport();
let renders = 0,
  restTimer = 0,
  moving = false;
const renderTimes = [],
  errors = [];
const chapterLabels = [
  "Откройте архив прокруткой",
  "Приближение к источнику",
  "От записей к связям",
  "Валюта и граница периода",
  "Повторное признание счёта",
  "Проверка самой среды",
  "Продолжите в лаборатории",
];
const sceneLabels = [
  "THE EVIDENCE ARCHIVE",
  "A CLOSER LOOK",
  "CONNECTED BY EVIDENCE",
  "CASE / FX-PERIOD",
  "CASE / DUPLICATES",
  "VERIFIED BY THE ENVIRONMENT",
  "FOLLOW THE EVIDENCE",
];
function wantsMotion() {
  return (
    !failed &&
    !wasCompact &&
    (stored === "on" || (stored !== "off" && !reduced.matches))
  );
}
function menuState(open, { focus = true } = {}) {
  menuOpen = open;
  menu.hidden = !open;
  shade.hidden = !open;
  menuButton.setAttribute("aria-expanded", String(open));
  menuButton.setAttribute("aria-label", open ? "Закрыть меню" : "Открыть меню");
  menuButton.querySelector("span").textContent = open ? "Закрыть" : "Меню";
  if (focus) {
    if (open) menu.querySelector("a").focus({ preventScroll: true });
    else menuButton.focus({ preventScroll: true });
  }
}
menuButton.addEventListener("click", () => menuState(!menuOpen));
shade.addEventListener("click", () => menuState(false));
menu.addEventListener("click", (e) => {
  if (e.target.closest("a")) menuState(false, { focus: false });
});
document.addEventListener("keydown", (e) => {
  if (menuOpen && e.key === "Escape") {
    e.preventDefault();
    menuState(false);
  }
  if (menuOpen && e.key === "Tab") {
    const items = [menuButton, ...menu.querySelectorAll("a,button")],
      i = items.indexOf(document.activeElement);
    if (e.shiftKey && i <= 0) {
      e.preventDefault();
      items.at(-1).focus();
    } else if (!e.shiftKey && i === items.length - 1) {
      e.preventDefault();
      menuButton.focus();
    }
  }
  const tab = e.target.closest("[data-screen-tab]");
  if (tab && ["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) {
    e.preventDefault();
    const tabs = [...tab.parentElement.querySelectorAll("[role=tab]")];
    const next =
      e.key === "Home"
        ? tabs[0]
        : e.key === "End"
          ? tabs.at(-1)
          : tabs[(tabs.indexOf(tab) + 1) % tabs.length];
    next.click();
    next.focus({ preventScroll: true });
  }
});
for (const preview of previews)
  preview.addEventListener("click", (e) => {
    const button = e.target.closest("[data-screen-tab]");
    if (!button) return;
    for (const tab of preview.querySelectorAll("[data-screen-tab]")) {
      const on = tab === button;
      tab.setAttribute("aria-selected", String(on));
      tab.tabIndex = on ? 0 : -1;
    }
    for (const content of preview.querySelectorAll("[data-screen-content]"))
      content.hidden =
        content.dataset.screenContent !== button.dataset.screenTab;
  });
function setMotionButton() {
  motionButton.setAttribute("aria-pressed", String(!cinematic));
  motionButton.disabled = wasCompact;
  motionButton.textContent = wasCompact
    ? innerWidth <= 900
      ? "Поверните экран вертикально для 3D"
      : "Увеличьте высоту окна для 3D"
    : cinematic
      ? "Уменьшить движение"
      : "Включить 3D-историю";
}
function requestFrame() {
  if (!frame && cinematic && !document.hidden)
    frame = requestAnimationFrame(draw);
}
function onScroll() {
  moving = true;
  if (engine?.setMoving(true)) sizeDirty = true;
  requestFrame();
  clearTimeout(restTimer);
  // Refine the resting image once, without changing the shared animation clock.
  restTimer = setTimeout(() => {
    moving = false;
    if (engine?.setMoving(false)) {
      sizeDirty = true;
      requestFrame();
    }
  }, 350);
}
function draw() {
  frame = 0;
  if (!cinematic || document.hidden) return;
  const start = performance.now();
  if (sizeDirty) {
    engine?.resize();
    sizeDirty = false;
  }
  const rect = film.getBoundingClientRect(),
    travel = Math.max(1, film.offsetHeight - stage.offsetHeight);
  progress = clamp(-rect.top / travel);
  const s = sample(progress);
  // Use the same reversible sample for the compact layout and its camera.
  if (root.classList.contains("short-portrait")) {
    const top = 340 - 130 * s.screen;
    if (stage.style.getPropertyValue("--scene-top") !== `${top}px`) {
      stage.style.setProperty("--scene-top", `${top}px`);
      engine?.resize();
    }
  }
  lastState = s;
  for (let i = 0; i < shots.length; i++) {
    const a = s.shots[i],
      range = shotRanges[i].range;
    shots[i].style.opacity = a.toFixed(5);
    const direction = progress < (range[1] + range[2]) / 2 ? 1 : -1;
    shots[i].style.transform =
      `translate3d(0,${((1 - a) * direction * 22).toFixed(3)}px,0)`;
    shots[i].inert = a < 0.98;
    shots[i].setAttribute("aria-hidden", String(a < 0.01));
  }
  document.querySelector("#film-progress").style.transform =
    `scaleX(${progress.toFixed(6)})`;
  document.querySelector("#film-position").textContent =
    Math.round(progress * 100) + "%";
  document.querySelector("#chapter-label").textContent =
    chapterLabels[s.active];
  document.querySelector("#scene-label-text").textContent =
    sceneLabels[s.active];
  for (const a of document.querySelectorAll("[data-chapter]"))
    a.setAttribute(
      "aria-current",
      String(Number(a.dataset.chapter) === s.active),
    );
  engine?.update(s);
  renders++;
  renderTimes.push(performance.now() - start);
  if (renderTimes.length > 300) renderTimes.shift();
}
function restoreContent() {
  previews.forEach((el, i) => {
    homes[i].append(el);
    el.classList.remove("spatial-preview");
    el.removeAttribute("style");
    el.inert = false;
    el.removeAttribute("aria-hidden");
  });
  anchors.forEach((el, i) => shots[i].prepend(el));
  for (const shot of shots) {
    shot.removeAttribute("style");
    shot.inert = false;
    shot.removeAttribute("aria-hidden");
  }
}
function jumpToCurrentHash(fallbackIndex) {
  const id = decodeURIComponent(location.hash.slice(1));
  const anchor =
    document.getElementById(id) ||
    (fallbackIndex ? anchors[fallbackIndex] : null);
  if (anchor) anchor.scrollIntoView({ block: "start", behavior: "instant" });
}
function disable({ reason, keepPlace = true } = {}) {
  epoch++;
  clearTimeout(restTimer);
  moving = false;
  const active = lastState.active,
    hadMode = cinematic;
  cinematic = false;
  loading = false;
  cancelAnimationFrame(frame);
  frame = 0;
  restoreContent();
  engine?.dispose();
  engine = null;
  world.replaceChildren();
  spatial.replaceChildren();
  root.classList.remove("cinematic", "webgl-ready");
  setMotionButton();
  if (reason) {
    failed = true;
    errors.push(reason);
    const note = document.querySelector("#fallback-message");
    note.hidden = false;
    note.textContent =
      "3D недоступно. Документы и расследования можно изучить в обычном режиме.";
  }
  if (keepPlace && hadMode)
    requestAnimationFrame(() =>
      anchors[active].scrollIntoView({ block: "start", behavior: "instant" }),
    );
}
async function enable() {
  if (cinematic || loading) return;
  const generation = ++epoch;
  loading = true;
  cinematic = true;
  root.classList.add("cinematic");
  anchors.forEach((anchor) => film.append(anchor));
  setMotionButton();
  sizeDirty = true;
  requestFrame();
  jumpToCurrentHash();
  try {
    const { createScene } = await import("./cinema/sled-scene.js");
    if (generation !== epoch || !wantsMotion()) return;
    engine = createScene({
      host: world,
      htmlHost: spatial,
      previews,
      onContextLost: () => disable({ reason: "WebGL context lost" }),
    });
    engine.setMoving(moving);
    loading = false;
    sizeDirty = true;
    draw();
    root.classList.add("webgl-ready");
    jumpToCurrentHash();
    requestFrame();
  } catch (error) {
    disable({ reason: String(error.message || error) });
  }
}
function syncMode() {
  if (wantsMotion()) enable();
  else if (cinematic || loading) disable();
  else setMotionButton();
}
motionButton.addEventListener("click", () => {
  stored = cinematic ? "off" : "on";
  failed = false;
  document.querySelector("#fallback-message").hidden = true;
  try {
    localStorage.setItem("sled-cinema-mode", stored);
  } catch {}
  menuState(false);
  syncMode();
});
reduced.addEventListener("change", () => {
  if (!stored) syncMode();
});
window.addEventListener("scroll", onScroll, { passive: true });
function resizeScene() {
  sizeDirty = true;
  syncPortraitLayout();
  const compact = compactViewport();
  if (compact !== wasCompact) {
    wasCompact = compact;
    syncMode();
  }
  requestFrame();
}
window.addEventListener("resize", resizeScene, { passive: true });
window.visualViewport?.addEventListener("resize", resizeScene, {
  passive: true,
});
// Dynamic viewport units can update without a matching window resize event.
const viewportObserver = new ResizeObserver(resizeScene);
viewportObserver.observe(stage);
viewportObserver.observe(viewportReference);
window.addEventListener("hashchange", () => {
  if (redirectLegacy()) return;
  menuState(false, { focus: false });
  requestFrame();
});
window.addEventListener("popstate", requestFrame);
window.addEventListener("pageshow", requestFrame);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    cancelAnimationFrame(frame);
    frame = 0;
  } else requestFrame();
});
window.addEventListener("pagehide", () => {
  cancelAnimationFrame(frame);
  frame = 0;
});
stage.addEventListener(
  "pointermove",
  (e) => {
    if (e.pointerType === "touch" || !engine || lastState.screen > 0.1) return;
    if (engine.hover(e.clientX, e.clientY)) requestFrame();
  },
  { passive: true },
);
stage.addEventListener("pointerleave", () => {
  if (engine?.hover(-100, -100)) requestFrame();
});
window.sledFilm = {
  snapshot: () => ({
    mode: cinematic ? "cinematic" : "static",
    loading,
    progress,
    active: shotRanges[lastState.active].id,
    renders,
    renderMillis: renderTimes.slice(),
    state: JSON.parse(JSON.stringify(lastState)),
    graphics: engine?.diagnostics() || null,
    errors: errors.slice(),
  }),
};
if (!redirecting) syncMode();
