import * as THREE from "../vendor/three/three.module.min.js";

const PALETTE = [
  { paper: "#e9f0e6", ink: "#22372b", edge: "#627d6e" },
  { paper: "#b9e5cc", ink: "#214333", edge: "#5b9b7d" },
  { paper: "#6eaf9c", ink: "#142e27", edge: "#357864" },
];

function cover(source, colors) {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 430;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = colors.paper;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = colors.edge;
  ctx.lineWidth = 2;
  ctx.strokeRect(26, 26, 460, 378);
  ctx.fillStyle = colors.ink;
  ctx.font = "700 28px system-ui";
  ctx.fillText(source.label.toUpperCase(), 50, 82);
  ctx.font = "700 126px system-ui";
  ctx.fillText(String(source.count), 44, 251);
  ctx.strokeStyle = colors.edge;
  for (const [index, length] of [390, 290, 350].entries()) {
    const y = 300 + 29 * index;
    ctx.beginPath();
    ctx.moveTo(50, y);
    ctx.lineTo(50 + length, y);
    ctx.stroke();
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

function buildStack(source, index, geometry) {
  const colors = PALETTE[index];
  const group = new THREE.Group();
  group.userData.source = source.key;
  const layers = Math.min(
    7,
    1 + Math.ceil(Math.log2(Math.max(source.count, 1))),
  );
  const paper = new THREE.MeshStandardMaterial({
    color: colors.paper,
    roughness: 0.57,
  });
  const support = new THREE.MeshStandardMaterial({
    color: "#174638",
    metalness: 0.32,
    roughness: 0.44,
  });
  const pad = new THREE.Mesh(geometry.pad, support);
  pad.position.y = -0.06;
  group.add(pad);
  const sheets = [];
  for (let n = 0; n < layers; n++) {
    const plate = new THREE.Mesh(geometry.sheet, paper);
    const top = n === layers - 1;
    const y = 0.12 + n * 0.093;
    const sheet = new THREE.Group();
    sheet.position.y = y;
    sheet.rotation.y = top ? 0 : n % 2 ? 0.03 : -0.025;
    sheet.add(plate);
    if (top) {
      const face = new THREE.Mesh(
        geometry.cover,
        new THREE.MeshBasicMaterial({ map: cover(source, colors) }),
      );
      face.rotation.x = -Math.PI / 2;
      face.position.y = 0.04;
      sheet.add(face);
    }
    sheets.push({ mesh: sheet, y });
    group.add(sheet);
  }
  return {
    group,
    sheets,
    source,
    x: (index - 1) * 2.36,
    z: index === 1 ? -0.72 : 0.62,
  };
}

export function createCompanyScene(host, sources, selected, onSelect) {
  const canvas = document.createElement("canvas");
  const options = {
    alpha: true,
    antialias: true,
    powerPreference: "low-power",
  };
  const context = canvas.getContext("webgl2", options);
  if (!context) return null;
  const renderer = new THREE.WebGLRenderer({ canvas, context, ...options });
  const pixelRatio = Math.min(devicePixelRatio || 1, 1.65);
  renderer.setPixelRatio(pixelRatio);
  renderer.setClearColor(0x000000, 0);
  canvas.className = "company-canvas";
  host.append(canvas);
  host.dataset.renderer = "webgl";

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(43, 1, 0.1, 40);
  camera.zoom = 1.1;
  const rig = new THREE.Group();
  scene.add(rig);
  scene.add(new THREE.HemisphereLight(0xe9fff1, 0x2a493a, 2.2));
  const light = new THREE.DirectionalLight(0xe4f9eb, 2.7);
  light.position.set(-2, 6, 5);
  scene.add(light);

  const platform = new THREE.Mesh(
    new THREE.CylinderGeometry(3.58, 3.62, 0.24, 64),
    new THREE.MeshStandardMaterial({
      color: "#153b31",
      roughness: 0.36,
      metalness: 0.25,
    }),
  );
  platform.scale.z = 0.78;
  platform.position.y = -0.225;
  rig.add(platform);
  for (const radius of [2.86, 3.18, 3.51]) {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(radius, radius === 3.51 ? 0.022 : 0.013, 5, 68),
      new THREE.MeshBasicMaterial({
        color: radius === 3.51 ? "#69b698" : "#285f4d",
      }),
    );
    ring.rotation.x = -Math.PI / 2;
    ring.scale.y = 0.78;
    ring.position.y = -0.09;
    rig.add(ring);
  }

  const geometry = {
    pad: new THREE.BoxGeometry(2.06, 0.16, 1.65),
    sheet: new THREE.BoxGeometry(1.87, 0.075, 1.56),
    cover: new THREE.PlaneGeometry(1.875, 1.565),
  };
  const stacks = sources.map((source, index) =>
    buildStack(source, index, geometry),
  );
  const beam = new THREE.LineBasicMaterial({ color: "#91dbb6" });
  const nodeMaterial = new THREE.MeshBasicMaterial({ color: "#a6f4c9" });
  const nodeGeometry = new THREE.SphereGeometry(0.04, 8, 6);
  for (const stack of stacks) {
    rig.add(stack.group);
    const elbow = new THREE.Vector3(stack.x, -0.075, 1.7);
    const end = new THREE.Vector3(stack.x * 0.52, -0.075, 2.28);
    rig.add(
      new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(stack.x, -0.075, stack.z),
          elbow,
          end,
        ]),
        beam,
      ),
    );
    const node = new THREE.Mesh(nodeGeometry, nodeMaterial);
    node.position.copy(end);
    rig.add(node);
    stack.node = node;
  }

  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const ray = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const origin = performance.now();
  let frame = 0;
  let deadline = origin + 1300;
  let last = 0;
  let pointerX = 0;
  let pointerY = 0;
  let cameraX = 0;
  let cameraY = 0;
  let down;
  let disposed = false;
  let ready = false;

  function animate(now) {
    frame = 0;
    if (disposed) return;
    if (!reduced.matches && now - last < 1000 / 45 && now < deadline) {
      frame = requestAnimationFrame(animate);
      return;
    }
    last = now;
    const progress = reduced.matches ? 1 : Math.min(1, (now - origin) / 1060);
    const reveal = 1 - (1 - progress) ** 3;
    const smooth = ready && !reduced.matches && now < deadline ? 0.2 : 1;
    cameraX += (pointerX - cameraX) * smooth;
    cameraY += (pointerY - cameraY) * smooth;
    camera.position.set(
      3.7 - 1.0 * reveal + 0.65 * cameraX,
      6.0 + 1.1 * reveal + 0.55 * cameraY,
      7.7 - 0.2 * reveal,
    );
    camera.lookAt(0, 0.26, 0.16);
    rig.rotation.y = -0.16 + 0.16 * reveal;

    for (const stack of stacks) {
      const active = stack.source.key === selected;
      const z = stack.z * reveal + (active ? 0.24 : 0);
      const y = active ? 0.5 : 0;
      stack.group.position.x = stack.x * (0.38 + 0.62 * reveal);
      stack.group.position.y += (y - stack.group.position.y) * smooth;
      stack.group.position.z += (z - stack.group.position.z) * smooth;
      stack.group.rotation.y +=
        ((active ? -0.13 : 0.02) - stack.group.rotation.y) * smooth;
      for (const [index, { mesh, y: height }] of stack.sheets.entries()) {
        const target = height + (active ? index * 0.021 : 0);
        mesh.position.y += (target - mesh.position.y) * smooth;
      }
      stack.node.scale.setScalar(active ? 1.45 : 0.65);
    }
    renderer.render(scene, camera);
    ready = true;
    if (!reduced.matches && now < deadline)
      frame = requestAnimationFrame(animate);
  }

  function schedule(ms = 0) {
    if (disposed) return;
    deadline = Math.max(deadline, performance.now() + ms);
    if (!frame) frame = requestAnimationFrame(animate);
  }

  const resize = new ResizeObserver(([entry]) => {
    const { width, height } = entry.contentRect;
    if (!width || !height) return;
    camera.aspect = width / height;
    camera.fov = 39 + Math.max(0, 1.55 - camera.aspect) * 18;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
    schedule();
  });
  resize.observe(host);

  canvas.addEventListener("pointermove", (event) => {
    if (event.pointerType !== "mouse" || reduced.matches) return;
    const box = canvas.getBoundingClientRect();
    pointerX = (2 * (event.clientX - box.left)) / box.width - 1;
    pointerY = (2 * (event.clientY - box.top)) / box.height - 1;
    schedule(310);
  });
  canvas.addEventListener("pointerleave", () => {
    pointerX = pointerY = 0;
    schedule(310);
  });
  canvas.addEventListener("pointerdown", (event) => {
    down = [event.clientX, event.clientY];
  });
  canvas.addEventListener("pointercancel", () => {
    down = null;
  });
  canvas.addEventListener("pointerup", (event) => {
    if (
      !down ||
      Math.hypot(event.clientX - down[0], event.clientY - down[1]) > 10
    )
      return;
    down = null;
    const box = canvas.getBoundingClientRect();
    pointer.set(
      (2 * (event.clientX - box.left)) / box.width - 1,
      1 - (2 * (event.clientY - box.top)) / box.height,
    );
    ray.setFromCamera(pointer, camera);
    const hit = ray.intersectObjects(
      stacks.map((stack) => stack.group),
      true,
    )[0];
    let target = hit?.object;
    while (target && !target.userData.source) target = target.parent;
    if (target) onSelect(target.userData.source);
  });
  const redraw = () => schedule();
  reduced.addEventListener("change", redraw);
  canvas.addEventListener("webglcontextlost", onLost);
  function onLost() {
    dispose();
  }
  function dispose() {
    if (disposed) return;
    disposed = true;
    cancelAnimationFrame(frame);
    resize.disconnect();
    reduced.removeEventListener("change", redraw);
    canvas.removeEventListener("webglcontextlost", onLost);
    const geometries = new Set();
    const materials = new Set();
    scene.traverse((object) => {
      if (object.geometry) geometries.add(object.geometry);
      if (object.material) materials.add(object.material);
    });
    for (const material of materials) {
      material.map?.dispose();
      material.dispose();
    }
    for (const geometry of geometries) geometry.dispose();
    renderer.dispose();
    renderer.forceContextLoss();
    canvas.remove();
    host.dataset.renderer = "css";
  }
  return {
    select(key) {
      selected = key;
      schedule(600);
    },
    dispose,
  };
}
