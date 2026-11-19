import assert from "node:assert/strict";
import { writeFile, mkdir } from "node:fs/promises";
import { sample, shotRanges } from "../web/cinema/timeline.js";
const checks = [];
const pass = (s) => checks.push(s);
const distance = (a, b) => Math.hypot(...a.map((x, i) => x - b[i]));
const forward = Array.from({ length: 1001 }, (_, i) => sample(i / 1000));
for (let i = 1000; i >= 0; i--) assert.deepEqual(sample(i / 1000), forward[i]);
pass("All timeline state is identical when sampled forward and backward");
for (const s of forward) {
  for (const value of [
    ...s.camera,
    ...s.position,
    ...s.rotation,
    s.spread,
    s.screen,
    s.seal,
    ...s.shots,
  ])
    assert.equal(Number.isFinite(value), true);
  assert.ok(distance(s.camera, s.position) > 5.5);
  for (const key of ["spread", "screen", "seal", "fx", "duplicate"])
    assert.ok(s[key] >= 0 && s[key] <= 1);
}
pass(
  "Camera stays outside the archive; all geometry and opacity values stay finite and bounded",
);
let maxCameraDelta = 0,
  maxRigDelta = 0,
  maxOpacityDelta = 0;
for (let i = 1; i <= 10000; i++) {
  const a = sample((i - 1) / 10000),
    b = sample(i / 10000);
  maxCameraDelta = Math.max(maxCameraDelta, distance(a.camera, b.camera));
  maxRigDelta = Math.max(maxRigDelta, distance(a.position, b.position));
  maxOpacityDelta = Math.max(
    maxOpacityDelta,
    ...a.shots.map((v, j) => Math.abs(v - b.shots[j])),
  );
}
assert.ok(maxCameraDelta < 0.04);
assert.ok(maxRigDelta < 0.03);
assert.ok(maxOpacityDelta < 0.01);
pass(
  "10,000 adjacent samples have bounded camera, object and HTML transitions without keyframe jumps",
);
for (const [a, b] of [
  [0.4, 0.46],
  [0.63, 0.68],
])
  for (const key of [
    "camera",
    "target",
    "position",
    "rotation",
    "spread",
    "screen",
    "seal",
  ])
    assert.deepEqual(sample(a)[key], sample(b)[key]);
pass("Both investigation scenes contain exact stationary reading intervals");
for (const shot of shotRanges)
  assert.equal(sample(shot.at).active, shotRanges.indexOf(shot));
assert.deepEqual(sample(-1), sample(0));
assert.deepEqual(sample(2), sample(1));
pass(
  "Chapter anchors resolve to the intended scene and scroll bounds are clamped",
);
const result = {
  passed: checks.length,
  checks,
  max_camera_delta_per_0_0001: maxCameraDelta,
  max_rig_delta_per_0_0001: maxRigDelta,
  max_opacity_delta_per_0_0001: maxOpacityDelta,
};
await mkdir("artifacts", { recursive: true });
await writeFile(
  "artifacts/timeline-check.json",
  JSON.stringify(result, null, 2) + "\n",
);
console.log(JSON.stringify(result, null, 2));
