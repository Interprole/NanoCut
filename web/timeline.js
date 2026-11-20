"use strict";
const $ = (id) => document.getElementById(id);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const uid = () => crypto.randomUUID();
const copy = (value) => JSON.parse(JSON.stringify(value));
const tc = (f, fps) => {
  const s = Math.floor(f / fps);
  return [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60, f % fps]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");
};
function node(tag, cls, text) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text !== undefined) el.textContent = text;
  return el;
}
function button(text, title, action) {
  const b = node("button", "", text);
  b.type = "button";
  b.title = title;
  b.onclick = action;
  return b;
}
function blank() {
  return {
    name: "Untitled project",
    fps: 30,
    width: 1920,
    height: 1080,
    library: [],
    clips: [],
  };
}
const ed = {
  p: blank(),
  assets: {},
  frame: 0,
  selected: null,
  snap: true,
  zoom: 42,
  history: [],
  future: [],
  playing: false,
  dirty: false,
  activeAsset: null,
};
const selected = () => ed.p.clips.find((c) => c.id === ed.selected);
const endFrame = () =>
  Math.max(0, ...ed.p.clips.map((c) => c.start + c.length));
const ppf = () => Math.pow(1.068, ed.zoom) * 0.18;
function snapshot() {
  return JSON.stringify({
    project: ed.p,
    selected: ed.selected,
    frame: ed.frame,
  });
}
function checkpoint() {
  ed.history.push(snapshot());
  if (ed.history.length > 90) ed.history.shift();
  ed.future = [];
}
function restore(redo) {
  const from = redo ? ed.future : ed.history,
    to = redo ? ed.history : ed.future;
  if (!from.length) return;
  stopPlay();
  to.push(snapshot());
  const previous = JSON.parse(from.pop());
  ed.p = previous.project;
  ed.frame = previous.frame;
  ed.selected = previous.selected;
  if (!selected()) ed.selected = null;
  changed();
}
function addClip(ident, track, start) {
  const a = ed.assets[ident];
  if (!a) return;
  track = track ?? (a.video ? 1 : 0);
  if (!a.video) track = 0;
  start =
    start ??
    Math.max(
      0,
      ...ed.p.clips
        .filter((c) => c.track === track)
        .map((c) => c.start + c.length),
    );
  const clip = {
    id: uid(),
    asset: ident,
    track,
    start: Math.max(0, Math.round(start)),
    length: Math.max(1, Math.round(a.duration * ed.p.fps)),
    offset: 0,
    rate: 1,
    x: 0.5,
    y: 0.5,
    scale: 1,
    volume: 1,
    guide: false,
    style: "Studio",
    cues: [],
  };
  ed.p.clips.push(clip);
  ed.selected = clip.id;
  return clip;
}
function splitClip() {
  const c = selected(),
    t = ed.frame;
  if (!c || t <= c.start || t >= c.start + c.length)
    return status("Place the playhead inside the selected clip.");
  checkpoint();
  const left = t - c.start,
    right = {
      ...copy(c),
      id: uid(),
      start: t,
      length: c.length - left,
      offset: c.offset + (left * c.rate) / ed.p.fps,
    };
  c.length = left;
  ed.p.clips.push(right);
  ed.selected = right.id;
  changed("Clip split at frame " + t);
}
function duplicate() {
  const c = selected();
  if (!c) return;
  checkpoint();
  const d = { ...copy(c), id: uid(), start: c.start + c.length };
  ed.p.clips.push(d);
  ed.selected = d.id;
  changed("Clip duplicated");
}
function removeClip() {
  if (!selected()) return;
  checkpoint();
  ed.p.clips = ed.p.clips.filter((c) => c.id !== ed.selected);
  ed.selected = null;
  changed("Clip deleted");
}
function snapFrame(value, otherEdge = 0, excluding = null) {
  value = Math.round(value);
  if (!ed.snap) return value;
  const points = [0, ed.frame];
  for (const c of ed.p.clips)
    if (c.id !== excluding) points.push(c.start, c.start + c.length);
  let best = value,
    dist = 7 / ppf();
  for (const point of points)
    for (const candidate of [point, point - otherEdge]) {
      if (Math.abs(candidate - value) < dist) {
        dist = Math.abs(candidate - value);
        best = candidate;
      }
    }
  return best;
}
function frameAt(x) {
  return Math.max(
    0,
    Math.round((x - $("seq").getBoundingClientRect().left) / ppf()),
  );
}
function zoomTo(value, anchor = ed.frame) {
  const old = ppf(),
    box = $("scroll"),
    delta = anchor * old - box.scrollLeft;
  ed.zoom = clamp(value, 0, 100);
  $("zoom").value = ed.zoom;
  drawTimeline();
  box.scrollLeft = Math.max(
    0,
    anchor * ppf() - clamp(delta, 0, box.clientWidth * 0.85),
  );
  drawRuler();
}
function fit() {
  const target =
    ($("scroll").clientWidth - 30) / Math.max(endFrame(), ed.p.fps * 4);
  zoomTo(Math.log(target / 0.18) / Math.log(1.068));
  $("scroll").scrollLeft = 0;
  drawRuler();
}
function drawRuler() {
  const r = $("ruler"),
    sc = $("scroll"),
    unit = ppf(),
    fps = ed.p.fps;
  r.replaceChildren();
  const seconds = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600];
  const major =
    unit >= 10
      ? Math.max(1, Math.ceil(65 / unit))
      : fps * (seconds.find((n) => n * fps * unit >= 65) || 3600);
  const step = unit >= 7 ? 1 : Math.max(1, Math.floor(major / 5));
  const left = Math.max(0, Math.floor(sc.scrollLeft / unit) - major);
  const right = Math.ceil((sc.scrollLeft + sc.clientWidth) / unit) + major;
  function tick(f, large) {
    const x = node("div", "tick" + (large ? " major" : ""));
    x.style.left = f * unit + "px";
    if (large)
      x.append(node("span", "", unit >= 7 ? f + "f" : tc(f, fps).slice(3, 8)));
    r.append(x);
  }
  for (let f = Math.floor(left / step) * step; f <= right; f += step)
    if (f % major !== 0) tick(f, false);
  for (let f = Math.floor(left / major) * major; f <= right; f += major)
    tick(f, true);
  $("grid-status").textContent =
    unit >= 7 ? "1 tick = 1 frame" : "Frame grid · " + fps + " fps";
}
function drawTimeline() {
  const unit = ppf(),
    w = Math.max(
      $("scroll").clientWidth,
      (Math.max(endFrame(), ed.frame) + ed.p.fps * 4) * unit,
    );
  $("seq").style.width = Math.ceil(w) + "px";
  for (const lane of document.querySelectorAll(".lane")) {
    lane.replaceChildren();
    lane.style.backgroundImage =
      unit >= 7
        ? "repeating-linear-gradient(to right,#34383d 0 1px,transparent 1px " +
          unit +
          "px)"
        : "none";
    const track = Number(lane.dataset.track);
    const clips = ed.p.clips
      .filter((c) => c.track === track)
      .sort((a, b) => a.start - b.start);
    for (const c of clips) {
      const block = node(
        "div",
        "block" + (c.id === ed.selected ? " active" : ""),
      );
      block.dataset.id = c.id;
      block.style.left = c.start * unit + "px";
      block.style.width = Math.max(2, c.length * unit) + "px";
      const a = ed.assets[c.asset];
      block.title =
        (a?.name || "Clip") + " · " + c.length + " frames · drag edges to trim";
      if (c.length * unit > 76) {
        const img = node("img");
        img.src = "thumb/" + c.asset;
        img.draggable = false;
        block.append(img);
      }
      block.append(
        node("span", "", (c.guide ? "Guide · " : "") + (a?.name || "Clip")),
      );
      for (const side of ["left", "right"]) {
        const h = node("i", "handle " + side);
        h.dataset.edge = side;
        block.append(h);
      }
      lane.append(block);
    }
  }
  drawRuler();
  updateNeedle();
}
function updateNeedle() {
  $("needle").style.left = ed.frame * ppf() + "px";
  $("timecode").textContent = tc(ed.frame, ed.p.fps);
  $("duration").textContent = "End " + tc(endFrame(), ed.p.fps);
}
function seek(f, scroll = false) {
  ed.frame = clamp(Math.round(f), 0, Math.max(endFrame(), ed.p.fps * 4));
  if (scroll) {
    const x = ed.frame * ppf(),
      s = $("scroll");
    if (x < s.scrollLeft || x > s.scrollLeft + s.clientWidth - 6)
      s.scrollLeft = Math.max(0, x - s.clientWidth * 0.22);
  }
  updateNeedle();
  preview();
}
function initTimeline() {
  let drag = null;
  $("seq").addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    stopPlay();
    const b = e.target.closest(".block"),
      frame = frameAt(e.clientX);
    if (!b) {
      seek(frame);
      drag = { type: "seek" };
      return;
    }
    ed.selected = b.dataset.id;
    const c = selected();
    drag = {
      type: e.target.dataset.edge || "move",
      c,
      old: copy(c),
      base: frame,
      dirty: false,
      x: e.clientX,
      y: e.clientY,
    };
    drawTimeline();
    inspector();
    updateButtons();
  });
  window.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const f = frameAt(e.clientX);
    if (drag.type === "seek") {
      seek(f);
      return;
    }
    if (!drag.dirty && Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < 4)
      return;
    const { c, old } = drag,
      delta = f - drag.base,
      a = ed.assets[c.asset];
    if (!drag.dirty) {
      checkpoint();
      drag.dirty = true;
    }
    const snap = (v, size = 0) =>
      e.altKey ? Math.round(v) : snapFrame(v, size, c.id);
    const available = a.still
      ? ed.p.fps * 86400
      : Math.max(
          1,
          Math.round(((a.duration - old.offset) * ed.p.fps) / c.rate),
        );
    if (drag.type === "move") {
      c.start = Math.max(0, snap(old.start + delta, old.length));
      const lane = document
        .elementFromPoint(e.clientX, e.clientY)
        ?.closest(".lane");
      if (lane) c.track = a.video ? Number(lane.dataset.track) : 0;
    } else if (drag.type === "right") {
      c.length = clamp(
        snap(old.start + old.length + delta) - old.start,
        1,
        available,
      );
    } else {
      const headroom = a.still
        ? old.start
        : Math.floor((old.offset * ed.p.fps) / c.rate + 1e-7);
      const shift = clamp(
        snap(old.start + delta) - old.start,
        -Math.min(headroom, old.start),
        old.length - 1,
      );
      c.start = old.start + shift;
      c.length = old.length - shift;
      c.offset = a.still
        ? 0
        : Math.max(0, old.offset + (shift * c.rate) / ed.p.fps);
    }
    drawTimeline();
    preview();
  });
  window.addEventListener("pointerup", () => {
    if (drag?.dirty) changed("Clip edited");
    drag = null;
  });
  $("scroll").addEventListener("scroll", drawRuler);
  $("zoom").oninput = (e) => zoomTo(+e.target.value);
  $("fit").onclick = fit;
  $("snap").onclick = () => {
    ed.snap = !ed.snap;
    $("snap").setAttribute("aria-pressed", ed.snap);
  };
  for (const lane of document.querySelectorAll(".lane")) {
    lane.ondragover = (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    };
    lane.ondrop = (e) => {
      e.preventDefault();
      const id = e.dataTransfer.getData("application/x-nanocut-asset");
      if (!ed.assets[id]) return;
      checkpoint();
      addClip(
        id,
        Number(lane.dataset.track),
        Math.max(0, snapFrame(frameAt(e.clientX))),
      );
      changed("Clip placed");
    };
  }
  $("undo").onclick = () => restore(false);
  $("redo").onclick = () => restore(true);
  $("split").onclick = splitClip;
  $("duplicate").onclick = duplicate;
  $("delete").onclick = removeClip;
}
