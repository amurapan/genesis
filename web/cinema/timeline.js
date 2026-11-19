/** One reversible scroll coordinate drives camera, geometry and HTML. */
export const clamp = (v, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, v));
export const ease = (v) => {
  const x = clamp(v);
  return x * x * x * (x * (x * 6 - 15) + 10);
};
export const ramp = (p, a, b) => ease((p - a) / (b - a));
export const mix = (a, b, t) => a + (b - a) * t;
export const shotRanges = [
  { id: "opening", anchor: "top", at: 0, range: [0, 0, 0.095, 0.145] },
  {
    id: "detail",
    anchor: "detail",
    at: 0.19,
    range: [0.125, 0.17, 0.21, 0.26],
  },
  {
    id: "unfold",
    anchor: "system",
    at: 0.29,
    range: [0.24, 0.275, 0.31, 0.36],
  },
  {
    id: "fx",
    anchor: "investigation",
    at: 0.43,
    range: [0.34, 0.385, 0.47, 0.535],
  },
  {
    id: "duplicate",
    anchor: "duplicates",
    at: 0.65,
    range: [0.52, 0.595, 0.69, 0.755],
  },
  {
    id: "proof",
    anchor: "verification",
    at: 0.82,
    range: [0.735, 0.79, 0.85, 0.91],
  },
  { id: "closing", anchor: "contact", at: 0.97, range: [0.89, 0.94, 1, 1] },
];
export function visibility(p, [a, b, c, d]) {
  return (a === b ? 1 : ramp(p, a, b)) * (c === d ? 1 : 1 - ramp(p, c, d));
}
const pose = (
  p,
  camera,
  target,
  position,
  rotation,
  spread,
  screen,
  seal,
  cover = 0,
) => ({ p, camera, target, position, rotation, spread, screen, seal, cover });
const poses = [
  pose(0, [6.8, 4.6, 9.4], [0, 0, 0], [0, 0, 0], [0, -0.15, -0.2], 0, 0, 0),
  pose(0.075, [6.8, 4.6, 9.4], [0, 0, 0], [0, 0, 0], [0, -0.15, -0.2], 0, 0, 0),
  pose(
    0.18,
    [3.1, 1.8, 6.0],
    [0.35, 0.1, 0.6],
    [0, 0, 0],
    [0.05, 0.1, -0.32],
    0.08,
    0,
    0,
    0.2,
  ),
  pose(
    0.205,
    [3.1, 1.8, 6.0],
    [0.35, 0.1, 0.6],
    [0, 0, 0],
    [0.05, 0.1, -0.32],
    0.08,
    0,
    0,
    0.2,
  ),
  pose(
    0.285,
    [5.2, 3.4, 11.3],
    [0, 0, 0],
    [0, 0, 0],
    [0, -0.12, -0.08],
    1,
    0,
    0,
    1,
  ),
  pose(
    0.31,
    [5.2, 3.4, 11.3],
    [0, 0, 0],
    [0, 0, 0],
    [0, -0.12, -0.08],
    1,
    0,
    0,
    1,
  ),
  pose(0.39, [0, 0, 12.8], [0, 0, 0], [0, 0, 0], [0, 0, 0], 0, 1, 0, 1),
  pose(0.48, [0, 0, 12.8], [0, 0, 0], [0, 0, 0], [0, 0, 0], 0, 1, 0, 1),
  pose(
    0.555,
    [5.0, 3.0, 9.7],
    [4.0, 0, -1.1],
    [4.0, 0, -1.1],
    [0.12, -0.55, 0.13],
    0.8,
    0,
    0,
    1,
  ),
  pose(0.61, [8, 0, 12.8], [8, 0, 0], [8, 0, 0], [0, 0, 0], 0, 1, 0, 1),
  pose(0.7, [8, 0, 12.8], [8, 0, 0], [8, 0, 0], [0, 0, 0], 0, 1, 0, 1),
  pose(
    0.8,
    [13, 3.8, 10.8],
    [9, 0, 0],
    [9, 0, 0],
    [0.08, -0.1, -0.1],
    0.45,
    0,
    1,
    1,
  ),
  pose(
    0.85,
    [13, 3.8, 10.8],
    [9, 0, 0],
    [9, 0, 0],
    [0.08, -0.1, -0.1],
    0.45,
    0,
    1,
    1,
  ),
  pose(
    0.95,
    [14.8, 3.0, 9.5],
    [9, 0, 0],
    [9, 0, 0],
    [0.05, -0.1, 0.13],
    0,
    0,
    0,
    0,
  ),
  pose(
    1,
    [14.8, 3.0, 9.5],
    [9, 0, 0],
    [9, 0, 0],
    [0.05, -0.1, 0.13],
    0,
    0,
    0,
    0,
  ),
];
export function sample(progress) {
  const p = clamp(progress);
  let i = 0;
  while (i < poses.length - 2 && poses[i + 1].p < p) i++;
  const a = poses[i],
    b = poses[i + 1],
    t = ease((p - a.p) / (b.p - a.p));
  const state = { p };
  for (const key of ["camera", "target", "position", "rotation"])
    state[key] = a[key].map((v, j) => mix(v, b[key][j], t));
  for (const key of ["spread", "screen", "seal", "cover"])
    state[key] = mix(a[key], b[key], t);
  state.fx = visibility(p, [0.345, 0.39, 0.48, 0.535]);
  state.duplicate = visibility(p, [0.57, 0.61, 0.7, 0.755]);
  state.warm = ramp(p, 0.51, 0.59) * (1 - ramp(p, 0.72, 0.8));
  state.shots = shotRanges.map((s) => visibility(p, s.range));
  state.active = state.shots.indexOf(Math.max(...state.shots));
  return state;
}
