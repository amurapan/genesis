import * as T from "../vendor/three/three.module.min.js";
import { CSS3DRenderer, CSS3DObject } from "../vendor/three/CSS3DRenderer.js";
import { mix, clamp } from "./timeline.js";

function roundedBox(w, h, depth, r = 0.14) {
  const x = -w / 2,
    y = -h / 2,
    s = new T.Shape();
  s.moveTo(x + r, y);
  s.lineTo(x + w - r, y);
  s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r);
  s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h);
  s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r);
  s.quadraticCurveTo(x, y, x + r, y);
  const g = new T.ExtrudeGeometry(s, {
    depth,
    bevelEnabled: true,
    bevelSegments: 2,
    steps: 1,
    bevelSize: 0.025,
    bevelThickness: 0.025,
    curveSegments: 7,
  });
  g.translate(0, 0, -depth / 2);
  return g;
}
function canvasTexture(draw, w = 1024, h = 768) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const ctx = c.getContext("2d");
  draw(ctx, w, h);
  const tex = new T.CanvasTexture(c);
  tex.colorSpace = T.SRGBColorSpace;
  return tex;
}
function labelTexture(kind) {
  return canvasTexture((c, w, h) => {
    const cover = kind === "cover",
      dark = cover || kind === "ledger";
    c.fillStyle = dark ? "#17231f" : "#e8ede4";
    c.fillRect(0, 0, w, h);
    c.strokeStyle = dark ? "#3c5247" : "#acbbaf";
    c.lineWidth = 2;
    c.strokeRect(44, 44, w - 88, h - 88);
    c.fillStyle = dark ? "#a1b9aa" : "#506557";
    c.font = "20px monospace";
    c.fillText(cover ? "EL BIG 4 / GENESIS" : "СЛЕД / PRIMARY RECORD", 80, 95);
    if (cover) {
      c.font = "bold 170px sans-serif";
      c.fillStyle = "#dbf4df";
      c.fillText("СЛЕД", 74, 337);
      c.fillStyle = "#86edaa";
      c.fillRect(80, 390, 620, 4);
      c.font = "30px sans-serif";
      c.fillStyle = "#a5c0ae";
      c.fillText("DOCUMENTS INTO EVIDENCE", 80, 452);
      c.font = "22px monospace";
      c.fillText("REPRODUCIBLE AUDIT ENVIRONMENT", 80, h - 110);
      for (let i = 0; i < 47; i++) {
        c.fillStyle = i % 3 === 0 ? "#91d6a5" : "#456c55";
        c.fillRect(80 + i * 7, h - 85, 3, 25);
      }
    } else {
      const heading = {
        payment: "100 USD",
        invoice: "100 000 KZT",
        ledger: "44 000 KZT",
        fx: "450 KZT / USD",
      }[kind];
      c.font = "bold 76px sans-serif";
      c.fillStyle = dark ? "#d2ecd9" : "#203c2b";
      c.fillText(heading, 80, 265);
      c.font = "24px monospace";
      c.fillStyle = dark ? "#9fc8ad" : "#557160";
      c.fillText(
        {
          payment: "30 NOV 2026 / PAYMENT",
          invoice: "ORIGINAL INVOICE",
          ledger: "01 DEC 2026 / LEDGER",
          fx: "30 NOV 2026 / FX POLICY",
        }[kind],
        80,
        328,
      );
      c.strokeStyle = dark ? "#526d5b" : "#acbcaf";
      for (let i = 0; i < 4; i++) {
        c.beginPath();
        c.moveTo(80, 410 + i * 58);
        c.lineTo(w - 80, 410 + i * 58);
        c.stroke();
      }
      c.font = "19px monospace";
      c.fillText("SYNTHETIC DATA / READ ONLY", 80, h - 80);
    }
  });
}
function studioTexture() {
  return canvasTexture(
    (c, w, h) => {
      c.fillStyle = "#263b30";
      c.fillRect(0, 0, w, h);
      const g = c.createLinearGradient(0, 0, 0, h);
      g.addColorStop(0, "#a3c0ac");
      g.addColorStop(0.45, "#273c31");
      g.addColorStop(1, "#060d09");
      c.fillStyle = g;
      c.fillRect(0, 0, w, h);
      for (const [x, width, alpha] of [
        [80, 100, 0.9],
        [350, 35, 0.7],
        [720, 170, 1],
      ]) {
        c.fillStyle = `rgba(237,255,245,${alpha})`;
        c.fillRect(x, 40, width, 240);
      }
      c.fillStyle = "#67cc93";
      c.fillRect(550, 110, 28, 210);
    },
    1024,
    512,
  );
}
function opacity(mesh, value) {
  const materials = Array.isArray(mesh.material)
    ? mesh.material
    : [mesh.material];
  for (const m of materials) m.opacity = value;
  mesh.visible = value > 0.001;
}

export function createScene({ host, htmlHost, previews, onContextLost }) {
  const renderer = new T.WebGLRenderer({
    alpha: true,
    antialias: false,
    powerPreference: "high-performance",
    stencil: false,
  });
  const gl = renderer.getContext(),
    debug = gl.getExtension("WEBGL_debug_renderer_info");
  const softwareRenderer = debug
    ? /swiftshader|llvmpipe|softpipe|software/i.test(
        gl.getParameter(debug.UNMASKED_RENDERER_WEBGL),
      )
    : false;
  // Software WebGL keeps the same geometry and camera with a simpler lighting model.
  function surface({ metalness = 0.0, roughness = 0.5, ...options }) {
    return softwareRenderer
      ? new T.MeshPhongMaterial({
          ...options,
          shininess: 8 + (1 - roughness) * 85,
          specular: new T.Color("#729884").multiplyScalar(
            0.2 + metalness * 0.5,
          ),
        })
      : new T.MeshStandardMaterial({ ...options, metalness, roughness });
  }

  renderer.outputColorSpace = T.SRGBColorSpace;
  renderer.toneMapping = T.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  renderer.setClearColor(0x08100c, 0);
  host.append(renderer.domElement);
  renderer.domElement.setAttribute("aria-hidden", "true");
  const onLost = (e) => {
    e.preventDefault();
    onContextLost();
  };
  renderer.domElement.addEventListener("webglcontextlost", onLost);
  const scene = new T.Scene(),
    camera = new T.PerspectiveCamera(34, 1, 0.1, 100);
  scene.fog = new T.FogExp2("#0a120e", 0.014);
  const cssScene = new T.Scene(),
    cssRenderer = new CSS3DRenderer();
  htmlHost.append(cssRenderer.domElement);
  let environmentTarget;
  if (!softwareRenderer) {
    const environment = studioTexture();
    environment.mapping = T.EquirectangularReflectionMapping;
    const pmrem = new T.PMREMGenerator(renderer);
    environmentTarget = pmrem.fromEquirectangular(environment);
    scene.environment = environmentTarget.texture;
    environment.dispose();
    pmrem.dispose();
  }
  scene.add(new T.HemisphereLight(0xd7ffe8, 0x102018, 2));
  const key = new T.DirectionalLight(0xf2fff4, 4.1);
  key.position.set(5, 9, 7);
  scene.add(key);
  const fill = new T.DirectionalLight(0x6dffb5, 2.7);
  fill.position.set(-6, 1, 4);
  scene.add(fill);
  const rim = new T.DirectionalLight(0xe1edff, 3.2);
  rim.position.set(2, 4, -6);
  scene.add(rim);
  const rig = new T.Group(),
    cssRig = new T.Group();
  scene.add(rig);
  cssScene.add(cssRig);
  const metal = surface({
    color: "#31433a",
    metalness: 0.87,
    roughness: 0.25,
    transparent: true,
  });
  const edge = surface({
    color: "#b9d2c1",
    metalness: 0.92,
    roughness: 0.18,
    transparent: true,
  });
  const green = surface({
    color: "#8dffb6",
    emissive: "#51cc82",
    emissiveIntensity: 0.65,
    metalness: 0.5,
    roughness: 0.25,
    transparent: true,
  });
  const dark = surface({
    color: "#122018",
    metalness: 0.65,
    roughness: 0.28,
    transparent: true,
  });
  const plateGeometry = roundedBox(4.3, 3.04, 0.045, 0.12),
    paperGeometry = roundedBox(4.13, 2.88, 0.026, 0.1),
    faceGeometry = new T.PlaneGeometry(3.96, 2.72);
  const sheets = [],
    folios = [1, 4, 8, 11],
    kinds = ["invoice", "payment", "ledger", "fx"];
  for (let i = 0; i < 14; i++) {
    const group = new T.Group(),
      mat = surface({
        color: i % 3 === 0 ? "#6c8c77" : i % 2 === 0 ? "#dce4d8" : "#293e31",
        metalness: i % 2 === 0 ? 0.2 : 0.8,
        roughness: 0.34,
        transparent: true,
      });
    const mesh = new T.Mesh(i % 2 === 0 ? paperGeometry : plateGeometry, mat);
    group.add(mesh);
    const materials = [mesh];
    if (folios.includes(i)) {
      const face = new T.Mesh(
        faceGeometry,
        surface({
          map: labelTexture(kinds[folios.indexOf(i)]),
          metalness: 0.05,
          roughness: 0.65,
          transparent: true,
        }),
      );
      face.position.z = 0.057;
      group.add(face);
      materials.push(face);
    }
    rig.add(group);
    sheets.push({ group, materials, index: i, folio: folios.indexOf(i) });
  }
  const back = new T.Mesh(roundedBox(4.58, 3.32, 0.18), metal.clone());
  back.position.z = -1.02;
  rig.add(back);
  const coverPivot = new T.Group();
  coverPivot.position.set(-2.29, 0, 0.87);
  rig.add(coverPivot);
  const cover = new T.Mesh(roundedBox(4.58, 3.32, 0.15), metal.clone());
  cover.position.x = 2.29;
  coverPivot.add(cover);
  const coverFace = new T.Mesh(
    new T.PlaneGeometry(4.34, 3.1),
    surface({
      map: labelTexture("cover"),
      roughness: 0.38,
      metalness: 0.42,
      transparent: true,
    }),
  );
  coverFace.position.set(2.29, 0, 0.105);
  coverPivot.add(coverFace);
  const bolts = [];
  for (const x of [0.17, 4.41])
    for (const y of [-1.46, 1.46]) {
      const m = new T.Mesh(
        new T.CylinderGeometry(0.065, 0.065, 0.035, 12),
        edge.clone(),
      );
      m.rotation.x = Math.PI / 2;
      m.position.set(x, y, 0.13);
      coverPivot.add(m);
      bolts.push(m);
    }
  const tracePoints = [
    [-1.85, -1.4, 1.02],
    [-1.85, -1.7, 0.65],
    [0.5, -1.7, 0.65],
    [1.88, -1.7, 0.65],
    [2.36, -1.3, 0.4],
    [2.36, 1.27, 0.4],
    [1.9, 1.64, -0.4],
    [0.4, 1.64, -0.4],
  ].map((v) => new T.Vector3(...v));
  const tracer = new T.Mesh(
    new T.TubeGeometry(
      new T.CatmullRomCurve3(tracePoints),
      70,
      0.025,
      7,
      false,
    ),
    green.clone(),
  );
  rig.add(tracer);
  const cableGroup = new T.Group();
  cableGroup.position.z = -0.15;
  rig.add(cableGroup);
  const cablePaths = [
    [
      [-1.55, 1.2, 0.8],
      [-0.4, 1.35, 1.15],
      [0.4, 0.8, 0.9],
      [1.45, 1.1, 0],
    ],
    [
      [1.45, 1.1, 0],
      [2.5, 0.1, 0.7],
      [1.95, -1, 0.9],
      [1.45, -1.2, 0.65],
    ],
    [
      [1.45, -1.2, 0.65],
      [0.2, -1.9, 1.1],
      [-1.1, -1.2, 0.8],
      [-1.45, -1.1, 0.3],
    ],
    [
      [-1.45, -1.1, 0.3],
      [-2.5, -0.2, 0.7],
      [-2.3, 0.9, 1],
      [-1.55, 1.2, 0.8],
    ],
  ];
  for (const path of cablePaths)
    cableGroup.add(
      new T.Mesh(
        new T.TubeGeometry(
          new T.CatmullRomCurve3(path.map((v) => new T.Vector3(...v))),
          32,
          0.015,
          5,
        ),
        green.clone(),
      ),
    );
  const frame = new T.Group();
  rig.add(frame);
  const frameBody = new T.Mesh(roundedBox(6.64, 4.69, 0.2, 0.13), dark.clone());
  frameBody.position.z = 0.04;
  frame.add(frameBody);
  const borderGeometry = new T.EdgesGeometry(
    roundedBox(6.7, 4.75, 0.13, 0.15),
    15,
  );
  const border = new T.LineSegments(
    borderGeometry,
    new T.LineBasicMaterial({ color: "#93dfb0", transparent: true }),
  );
  frame.add(border);
  const cssObjects = previews.map((el) => {
    el.classList.add("spatial-preview");
    const object = new CSS3DObject(el);
    cssRig.add(object);
    return object;
  });
  const seal = new T.Group();
  rig.add(seal);
  const rings = [];
  for (let i = 0; i < 3; i++) {
    const m = new T.Mesh(
      new T.TorusGeometry(1.7 + i * 0.17, 0.018, 6, 100),
      i === 0 ? green.clone() : metal.clone(),
    );
    m.position.z = 0.2 - i * 0.15;
    m.rotation.x = i * 0.13;
    seal.add(m);
    rings.push(m);
  }
  const check = new T.Group();
  check.position.set(0, 0, 0.4);
  seal.add(check);
  const arm1 = new T.Mesh(roundedBox(0.23, 0.85, 0.14, 0.06), green.clone());
  arm1.position.set(-0.48, -0.2, 0);
  arm1.rotation.z = 0.75;
  check.add(arm1);
  const arm2 = new T.Mesh(roundedBox(0.23, 1.7, 0.14, 0.06), green.clone());
  arm2.position.set(0.28, 0.13, 0);
  arm2.rotation.z = -0.68;
  check.add(arm2);
  const shadowTexture = canvasTexture(
    (c, w, h) => {
      const g = c.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
      g.addColorStop(0, "rgba(50,150,90,.22)");
      g.addColorStop(0.5, "rgba(14,45,27,.14)");
      g.addColorStop(1, "rgba(0,0,0,0)");
      c.fillStyle = g;
      c.fillRect(0, 0, w, h);
    },
    256,
    256,
  );
  const shadow = new T.Mesh(
    new T.PlaneGeometry(10, 10),
    new T.MeshBasicMaterial({
      map: shadowTexture,
      transparent: true,
      depthWrite: false,
    }),
  );
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = -2.65;
  rig.add(shadow);
  let width = 1,
    height = 1,
    lastState,
    highlight = 0,
    renderCount = 0,
    moving = false;
  const raycaster = new T.Raycaster(),
    pointer = new T.Vector2();
  function resize() {
    const r = host.getBoundingClientRect();
    width = Math.max(1, r.width);
    height = Math.max(1, r.height);
    const mobile = matchMedia("(max-width: 900px)").matches;
    renderer.setPixelRatio(
      softwareRenderer
        ? moving
          ? 0.65
          : mobile
            ? 1
            : 1.5
        : Math.min(devicePixelRatio || 1, mobile ? 1 : 1.5),
    );
    renderer.setSize(width, height);
    cssRenderer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }
  function setMoving(value) {
    if (!softwareRenderer || moving === value) return false;
    moving = value;
    return true;
  }
  function update(s) {
    lastState = s;
    camera.position.fromArray(s.camera);
    camera.lookAt(...s.target);
    rig.position.fromArray(s.position);
    rig.rotation.set(...s.rotation);
    cssRig.position.copy(rig.position);
    cssRig.rotation.copy(rig.rotation);
    // Portrait framing changes projection only; all transforms still use the same timeline.
    const mobileScene = matchMedia("(max-width: 900px)").matches;
    const minimumFov = mobileScene ? 37 : 34;
    const baseFov = T.MathUtils.radToDeg(
      2 *
        Math.atan(
          Math.tan(T.MathUtils.degToRad(minimumFov) / 2) *
            Math.max(1, 0.8 / camera.aspect),
        ),
    );
    const distance = camera.position.distanceTo(new T.Vector3(...s.target));
    const fitFov = T.MathUtils.radToDeg(
      2 *
        Math.atan(
          Math.max(
            (mobileScene ? 4.5 : 6.8) / (2 * distance * camera.aspect * 0.9),
            4.8 / (2 * distance * 0.9),
          ),
        ),
    );
    camera.fov = mix(baseFov, fitFov, s.screen);
    camera.updateProjectionMatrix();
    const fan = [
      [-1.55, 1.2, 0.7],
      [1.45, 1.1, -0.1],
      [-1.45, -1.1, 0.2],
      [1.45, -1.2, 0.6],
    ];
    for (const { group, materials, index: i, folio: f } of sheets) {
      const angle = (i / 14) * Math.PI * 2;
      const target =
        f >= 0 ? fan[f] : [Math.cos(angle) * 2.3, Math.sin(angle) * 1.9, -0.8];
      const k = s.spread;
      group.position.set(
        mix(0, target[0], k),
        mix(0, target[1], k),
        mix(-0.78 + i * 0.115, target[2], k),
      );
      group.rotation.set(
        k * (f < 0 ? 0.3 : 0),
        k * (f % 2 === 0 ? 0.2 : -0.18),
        k * (f < 0 ? angle * 0.15 : f % 2 === 0 ? -0.11 : 0.12),
      );
      group.scale.setScalar(mix(1, f >= 0 ? 0.57 : 0.27, k));
      if (s.seal) {
        group.position.lerp(
          new T.Vector3(
            Math.cos(angle) * 2.45,
            Math.sin(angle) * 2.2,
            -0.35 + Math.sin(angle * 2) * 0.25,
          ),
          s.seal,
        );
        group.scale.setScalar(mix(group.scale.x, 0.14, s.seal));
        group.rotation.z = mix(group.rotation.z, angle - Math.PI / 2, s.seal);
      }
      const alpha = (1 - s.screen) * (f >= 0 ? 1 : mix(1, 0.45, k));
      for (const m of materials) opacity(m, alpha);
    }
    coverPivot.rotation.y = -s.cover * 1.9;
    coverPivot.position.x = -2.29 - s.spread * 0.4;
    const coverAlpha = (1 - s.screen) * (1 - s.seal);
    for (const m of [cover, coverFace, ...bolts, back, tracer])
      opacity(m, coverAlpha);
    cover.material.emissive.set("#63c38c");
    cover.material.emissiveIntensity = 0.03 + highlight * 0.15;
    for (const m of cableGroup.children)
      opacity(m, s.spread * (1 - s.screen) * (1 - s.seal));
    const frameScale = mix(0.68, 1, s.screen);
    frame.scale.set(
      frameScale * (mobileScene ? 0.65 : 1),
      frameScale,
      frameScale,
    );
    opacity(frameBody, s.screen);
    border.material.opacity = s.screen * 0.6;
    border.visible = s.screen > 0.001;
    for (let i = 0; i < cssObjects.length; i++) {
      const a = i === 0 ? s.fx : s.duplicate,
        obj = cssObjects[i];
      obj.position.set(0, 0, 0.2);
      obj.scale.setScalar(0.01 * frameScale);
      obj.visible = a > 0.001;
      obj.element.style.opacity = a.toFixed(5);
      obj.element.style.pointerEvents = a > 0.98 ? "auto" : "none";
      obj.element.inert = a < 0.98;
      obj.element.setAttribute("aria-hidden", String(a < 0.01));
    }
    for (const m of [...rings, arm1, arm2]) opacity(m, s.seal);
    seal.rotation.z = s.seal * 0.12;
    const tint = new T.Color("#8dffb6").lerp(new T.Color("#f1c397"), s.warm);
    for (const m of [tracer, ...cableGroup.children]) {
      m.material.color.copy(tint);
      m.material.emissive.copy(tint).multiplyScalar(0.5);
    }
    scene.updateMatrixWorld(true);
    cssScene.updateMatrixWorld(true);
    renderer.render(scene, camera);
    cssRenderer.render(cssScene, camera);
    renderCount++;
  }
  function hover(x, y) {
    const r = host.getBoundingClientRect();
    pointer.set(
      ((x - r.left) / r.width) * 2 - 1,
      (-(y - r.top) / r.height) * 2 + 1,
    );
    raycaster.setFromCamera(pointer, camera);
    const hit = !!raycaster.intersectObjects([cover, coverFace], false).length;
    const next = hit ? 1 : 0;
    if (next !== highlight) {
      highlight = next;
      return true;
    }
    return false;
  }
  function diagnostics() {
    return {
      webgl: true,
      quality: softwareRenderer ? "software" : "full",
      threeRevision: T.REVISION,
      renderCount,
      calls: renderer.info.render.calls,
      triangles: renderer.info.render.triangles,
      pixelRatio: renderer.getPixelRatio(),
      width,
      height,
      progress: lastState?.p,
      camera: camera.position.toArray(),
      target: lastState?.target,
      rig: rig.position.toArray(),
      screen: lastState?.screen,
      matrix: camera.matrixWorld.elements.slice(),
      cssMatrix: cssObjects[0].matrixWorld.elements.slice(),
    };
  }
  function dispose() {
    renderer.domElement.removeEventListener("webglcontextlost", onLost);
    const geometries = new Set(),
      materials = new Set(),
      textures = new Set();
    scene.traverse((o) => {
      if (o.geometry) geometries.add(o.geometry);
      if (o.material)
        for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
          materials.add(m);
          if (m.map) textures.add(m.map);
        }
    });
    for (const x of [...geometries, ...materials, ...textures]) x.dispose();
    environmentTarget?.dispose();
    renderer.dispose();
    renderer.domElement.remove();
    cssRenderer.domElement.remove();
  }
  resize();
  return { resize, setMoving, update, hover, diagnostics, dispose };
}
