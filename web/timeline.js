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
    tracks: [],
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
  ed.multi = [ed.selected];
  ed.range = null;
  if (!selected()) ed.selected = null;
  changed();
}
function tracks() {
  return ed.p.tracks ??= [...new Set([0, 1, 2, ...ed.p.clips.map(c => c.track)])].sort((a,b) => a-b);
}
function newTrack(video, above) {
  const rows = tracks();
  const id = video ? Math.max(0, ...rows) + 1 : Math.min(1, ...rows) - 1;
  if (above !== undefined && rows.includes(above)) rows.splice(rows.indexOf(above)+1, 0, id);
  else if (video) rows.push(id);
  else rows.unshift(id);
  return id;
}
function trackName(id) { return id > 0 ? "V" + id : "A" + (1-id); }
function selectClip(c, additive=false) {
  const ids = new Set(additive ? ed.multi : []);
  if (additive && ids.has(c.id)) ids.delete(c.id); else ids.add(c.id);
  ed.multi = [...ids];
  ed.selected = ids.has(c.id) ? c.id : ed.multi.at(-1);
}
function selectedClips() {
  const ids = new Set([ed.selected, ...(ed.multi || [])]);
  const groups = new Set(ed.p.clips.filter(c => ids.has(c.id) && c.link).map(c => c.link));
  return ed.p.clips.filter(c => ids.has(c.id) || groups.has(c.link));
}
function addClip(ident, track, start) {
  const a = ed.assets[ident];
  if (!a) return;
  const fresh = track == null;
  if (fresh) track = newTrack(a.video);
  else if (a.video ? track <= 0 && !a.audio : track > 0) throw Error("Choose a compatible track.");
  if (!tracks().includes(track)) tracks().push(track);
  start ??= fresh ? endFrame() : Math.max(0, ...ed.p.clips.filter(c => c.track === track).map(c => c.start+c.length));
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
  clip.kind = track > 0 ? "video" : "audio";
  if (track > 0 && a.audio) {
    const link = uid();
    clip.link = link;
    let partner = fresh ? undefined : tracks().find(t => t <= 0 && !ed.p.clips.some(c =>
      c.track === t && c.start < start+clip.length && start < c.start+c.length));
    ed.p.clips.push({...copy(clip), id: uid(), track: partner ?? newTrack(false), kind: "audio"});
  }
  selectClip(clip);
  return clip;
}
function splitClip() {
  const c = selected(),
    t = ed.frame;
  if (!c || t <= c.start || t >= c.start + c.length)
    return status("Place the playhead inside the selected clip.");
  checkpoint();
  const links = new Map();
  for (const item of selectedClips()) {
    const left = t-item.start;
    if (left <= 0 || left >= item.length) continue;
    const right = {...copy(item), id:uid(), start:t, length:item.length-left,
      offset:item.offset+left*item.rate/ed.p.fps};
    if (item.link) {
      if (!links.has(item.link)) links.set(item.link, uid());
      right.link = links.get(item.link);
    }
    item.length = left;
    ed.p.clips.push(right);
    if (item === c) ed.selected = right.id;
  }
  ed.multi = [ed.selected];
  changed("Split at frame " + t);
}
function duplicate() {
  if (!selected()) return;
  checkpoint();
  const items = selectedClips(), links = new Map();
  const delta = Math.max(...items.map(c => c.start+c.length))-Math.min(...items.map(c=>c.start));
  ed.multi = [];
  for (const c of items) {
    const d = {...copy(c), id:uid(), start:c.start+delta};
    if (c.link) {
      if (!links.has(c.link)) links.set(c.link, uid());
      d.link = links.get(c.link);
    }
    ed.p.clips.push(d);
    ed.multi.push(d.id);
    if (c.id === ed.selected) ed.selected = d.id;
  }
  changed("Selection duplicated");
}
function removeClip() {
  if (!selected()) return;
  checkpoint();
  const items = new Set(selectedClips());
  ed.p.clips = ed.p.clips.filter(c => !items.has(c));
  ed.selected = null;
  ed.multi = [];
  changed("Selection deleted");
}
function snapFrame(value, otherEdge = 0, excluding = null) {
  value = Math.round(value);
  if (!ed.snap) return value;
  const points = [0, ed.frame];
  for (const c of ed.p.clips)
    if (!(excluding instanceof Set ? excluding.has(c.id) : c.id === excluding)) points.push(c.start, c.start + c.length);
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
  syncLanes();
  const picked = new Set(selectedClips().map(c => c.id));
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
    if (ed.range?.lane === track) {
      const r = node("div","marked-region");
      r.style.left = ed.range.a*unit+"px"; r.style.width=(ed.range.b-ed.range.a)*unit+"px";
      lane.append(r);
    }
    const clips = ed.p.clips
      .filter((c) => c.track === track)
      .sort((a, b) => a.start - b.start);
    for (const c of clips) {
      const block = node(
        "div",
        "block" + (picked.has(c.id) ? " active" : ""),
      );
      block.dataset.id = c.id;
      block.style.left = c.start * unit + "px";
      block.style.width = Math.max(2, c.length * unit) + "px";
      const a = ed.assets[c.asset];
      block.title =
        (a?.name || "Clip") + " · " + c.length + " frames · drag edges to trim";
      if (track <= 0 && a?.audio) {
        const fraction = c.length*c.rate/(ed.p.fps*a.duration);
        block.style.backgroundImage = "url(wave/"+c.asset+")";
        block.style.backgroundSize = (100/fraction)+"% 100%";
        block.style.backgroundPositionX = (fraction >= 1 ? 0 : 100*c.offset/a.duration/(1-fraction))+"%";
      } else if (c.kind !== "caption" && c.length * unit > 76) {
        const img = node("img");
        img.src = "thumb/" + c.asset;
        img.draggable = false;
        block.append(img);
      }
      block.append(
        node("span", "", (c.kind === "caption" ? "CC · " + (c.cues[0]?.text || "Captions") : (c.link ? "↔ " : "") + (c.guide ? "Guide · " : "") + (a?.name || "Clip"))),
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
    if (e.shiftKey && e.target.closest(".lane")) {
      const lane = +e.target.closest(".lane").dataset.track;
      drag = {type:"range", base:frame, lane};
      ed.range = {a:frame,b:frame+1,lane};
      drawTimeline(); return;
    }
    if (!b) {
      seek(frame);
      drag = { type: "seek" };
      return;
    }
    const clicked = ed.p.clips.find(c=>c.id===b.dataset.id);
    if (e.ctrlKey || e.metaKey) {
      selectClip(clicked, true); refresh(); return;
    }
    if (!(ed.multi || []).includes(clicked.id)) selectClip(clicked);
    else ed.selected = clicked.id;
    const c = selected();
    drag = {
      type: e.target.dataset.edge || "move",
      c,
      old: copy(c),
      items: selectedClips().map(item => [item, copy(item)]),
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
    if (drag.type === "range") {
      ed.range = {a:Math.min(f,drag.base), b:Math.max(f,drag.base+1), lane:drag.lane};
      drawTimeline(); return;
    }
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
      e.altKey ? Math.round(v) : snapFrame(v, size, new Set(drag.items.map(([item])=>item.id)));
    const available = a.still
      ? ed.p.fps * 86400
      : Math.max(
          1,
          Math.round(((a.duration - old.offset) * ed.p.fps) / c.rate),
        );
    if (drag.type === "move") {
      const shift = Math.max(-Math.min(...drag.items.map(([,v])=>v.start)), snap(old.start+delta,old.length)-old.start);
      for (const [item, v] of drag.items) item.start = v.start+shift;
      const lane = document
        .elementFromPoint(e.clientX, e.clientY)
        ?.closest(".lane");
      if (lane && (old.track > 0) === (+lane.dataset.track > 0)) c.track = +lane.dataset.track;
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
    if (drag.type !== "move" && c.link) {
      for (const [item,v] of drag.items) {
        if (item !== c && item.link === c.link && v.start === old.start && v.length === old.length) {
          item.start = c.start; item.length = c.length;
          item.offset = Math.max(0,v.offset+(c.start-v.start)*item.rate/ed.p.fps);
        }
      }
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
  $("seq").ondragover = e => e.preventDefault();
  $("seq").ondrop = safe(e => {
    e.preventDefault();
    const id=e.dataTransfer.getData("application/x-nanocut-asset");
    if (!ed.assets[id]) return;
    const lane=e.target.closest(".lane");
    checkpoint();
    addClip(id,lane ? +lane.dataset.track : undefined, Math.max(0,snapFrame(frameAt(e.clientX))));
    changed("Clip placed");
  });
  $("undo").onclick = () => restore(false);
  $("redo").onclick = () => restore(true);
  $("split").onclick = splitClip;
  $("duplicate").onclick = duplicate;
  $("delete").onclick = removeClip;
}

function syncLanes() {
  const list = [...tracks()].reverse(), labels = $("lane-labels"), seq=$("seq");
  if (labels.dataset.tracks === JSON.stringify(list)) return;
  labels.dataset.tracks = JSON.stringify(list);
  labels.replaceChildren(node("div","ruler-label","TRACKS"));
  seq.querySelectorAll(".lane, .drop-track").forEach(el=>el.remove());
  for (const id of list) {
    const label = node("div","track-label"), lane = node("div","lane");
    label.append(node("em","",trackName(id)),node("span","",id>0?"Video":"Audio"));
    label.title = "Select all clips on this track. Ctrl-click to extend selection.";
    label.onclick = e => {
      const ids=ed.p.clips.filter(c=>c.track===id).map(c=>c.id);
      const prior = new Set(e.ctrlKey || e.metaKey ? ed.multi : []);
      const remove = ids.length && ids.every(item=>prior.has(item));
      for (const item of ids) { if (remove) prior.delete(item); else prior.add(item); }
      ed.multi=[...prior]; ed.selected=ed.multi.at(-1); refresh();
    };
    labels.append(label); lane.dataset.track=id;
    lane.dataset.type=id>0?"video":"audio"; seq.insertBefore(lane,$("needle"));
  }
  seq.insertBefore(node("div","drop-track","Drop media here to create tracks"),$("needle"));
}
