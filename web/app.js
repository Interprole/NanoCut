"use strict";
let settings = {},
  clock = 0,
  startFrame = 0,
  raf = 0,
  autoTimer = 0,
  taskRunning = false,
  revision = 0;
const mediaNodes = new Map();
let changeModel = false;
function status(message) {
  $("status").textContent = message;
}
async function api(op, data = {}) {
  const res = await fetch("api/" + op, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const obj = await res.json();
  if (!res.ok || obj.error) throw Error(obj.error || "The operation failed.");
  return obj.value;
}
function message(error) {
  status(error.message || String(error));
  showForm(
    "Could not finish",
    [],
    () => {},
    "Close",
    error.message || String(error),
  );
}
const safe =
  (fn) =>
  async (...args) => {
    try {
      await fn(...args);
    } catch (e) {
      message(e);
    }
  };
function changed(note) {
  ed.dirty = true;
  revision++;
  refresh();
  if (note) status(note);
  clearTimeout(autoTimer);
  const rev = revision;
  autoTimer = setTimeout(async () => {
    try {
      await api("autosave", { project: ed.p });
      $("file-menu").querySelector('[data-action="recover"]').disabled = false;
      if (revision === rev && ed.dirty)
        $("save-state").textContent = "Recovery saved";
    } catch (e) {
      status("Recovery save failed · " + e.message);
    }
  }, 550);
}
function layout() {
  const v = $("viewer"),
    s = $("stage"),
    ratio = ed.p.width / ed.p.height;
  const w = Math.max(
    1,
    Math.min(v.clientWidth - 36, (v.clientHeight - 28) * ratio),
  );
  s.style.width = w + "px";
  s.style.height = w / ratio + "px";
}
function preview() {
  const f = ed.frame,
    p = ed.p,
    active = p.clips
      .filter((c) => f >= c.start && f < c.start + c.length)
      .sort((a, b) => a.track - b.track || a.start - b.start);
  const ids = new Set(active.map((c) => c.id));
  for (const [id, el] of mediaNodes) {
    if (
      !ids.has(id) ||
      el.dataset.asset !== p.clips.find((c) => c.id === id)?.asset
    ) {
      el.pause?.();
      el.removeAttribute("src");
      el.load?.();
      el.remove();
      mediaNodes.delete(id);
    }
  }
  let cues = [];
  for (const [z, c] of active.entries()) {
    const a = ed.assets[c.asset];
    if (!a) continue;
    let el = mediaNodes.get(c.id);
    if (!el) {
      el = node(a.still ? "img" : a.video ? "video" : "audio");
      el.dataset.asset = c.asset;
      el.dataset.clip = c.id;
      el.preload = "auto";
      el.onloadedmetadata = () => {
        if (mediaNodes.get(c.id) === el) preview();
      };
      el.onerror = () => {
        if (el.getAttribute("src"))
          status(
            "Playback unavailable for " +
              a.name +
              ". Try importing a converted copy.",
          );
      };
      el.src = "media/" + c.asset;
      el.draggable = false;
      $("layers").append(el);
      mediaNodes.set(c.id, el);
    }
    const time = c.offset + ((f - c.start) * c.rate) / p.fps;
    el.hidden = c.track === 0 || !a.video;
    Object.assign(el.style, {
      left: c.x * 100 + "%",
      top: c.y * 100 + "%",
      width: c.scale * 100 + "%",
      height: c.scale * 100 + "%",
      zIndex: z + 1,
    });
    if (!a.still) {
      el.volume = clamp(c.volume, 0, 1);
      const rate = c.rate * Number($("play-rate").value);
      el.playbackRate = clamp(rate, 0.0625, 16);
      if (el.readyState >= 1) {
        const tolerance = ed.playing ? 0.13 : 0.35 / p.fps;
        if (Math.abs(el.currentTime - time) > tolerance && !el.seeking)
          el.currentTime = Math.min(time, Math.max(0, a.duration - 0.001));
        if (ed.playing && el.paused) el.play().catch(() => {});
        if (!ed.playing && !el.paused) el.pause();
        el.onseeked = () => {
          if (!ed.playing && mediaNodes.get(c.id) === el) preview();
        };
      }
    }
    for (const cue of c.cues)
      if (time >= cue.in && time < cue.out) cues.push([c.style, cue.text]);
  }
  const ck = JSON.stringify(cues);
  if ($("captions").dataset.key !== ck) {
    $("captions").replaceChildren(
      ...cues.map(([style, t]) => node("div", "cue " + style, t)),
    );
    $("captions").dataset.key = ck;
  }
}
function stopPlay() {
  ed.playing = false;
  cancelAnimationFrame(raf);
  $("play").classList.remove("is-playing");
  for (const el of mediaNodes.values()) el.pause?.();
}
function togglePlay() {
  if (ed.playing) {
    stopPlay();
    return;
  }
  if (!endFrame()) return;
  if (ed.frame >= endFrame()) seek(0);
  ed.playing = true;
  clock = performance.now();
  startFrame = ed.frame;
  $("play").classList.add("is-playing");
  preview();
  function step(now) {
    if (!ed.playing) return;
    const f =
      startFrame +
      Math.floor(
        ((now - clock) * ed.p.fps * Number($("play-rate").value)) / 1000,
      );
    if (f >= endFrame()) {
      stopPlay();
      seek(endFrame());
      return;
    }
    if (f !== ed.frame) seek(f, true);
    raf = requestAnimationFrame(step);
  }
  raf = requestAnimationFrame(step);
}
function updateButtons() {
  for (const id of ["split", "duplicate", "delete"])
    $(id).disabled = !selected();
  $("undo").disabled = !ed.history.length;
  $("redo").disabled = !ed.future.length;
}
function bin() {
  const box = $("assets");
  box.replaceChildren();
  $("asset-count").textContent = ed.p.library.length;
  if (!ed.p.library.length)
    box.append(
      node(
        "div",
        "bin-empty",
        "Video, audio and still images appear here. Drag a file from the pool onto a track.",
      ),
    );
  for (const id of ed.p.library) {
    const a = ed.assets[id];
    if (!a) continue;
    const row = node(
      "div",
      "asset" + (ed.activeAsset === id ? " selected" : ""),
    );
    row.draggable = true;
    row.ondragstart = (e) =>
      e.dataTransfer.setData("application/x-nanocut-asset", id);
    row.onclick = () => {
      ed.activeAsset = id;
      bin();
    };
    const append = () => {
      checkpoint();
      addClip(id);
      changed("Clip appended");
    };
    row.ondblclick = append;
    const img = node("img");
    img.src = "thumb/" + id;
    img.draggable = false;
    const txt = node("div");
    txt.append(
      node("b", "", a.name),
      node(
        "small",
        "",
        (a.still ? "Image" : a.video ? "Video" : "Audio") +
          " · " +
          (a.still ? a.width + " × " + a.height : formatTime(a.duration)),
      ),
    );
    row.append(
      img,
      txt,
      button("+", "Append to timeline", (e) => {
        e.stopPropagation();
        append();
      }),
    );
    box.append(row);
  }
}
function refresh() {
  $("name").value = ed.p.name;
  $("welcome").hidden = !!ed.p.clips.length;
  $("monitor-meta").textContent =
    ed.p.width + " × " + ed.p.height + " · " + ed.p.fps + " fps";
  $("save-state").textContent = ed.dirty ? "Edited" : "";
  ed.frame = clamp(ed.frame, 0, Math.max(endFrame(), ed.p.fps * 4));
  bin();
  drawTimeline();
  inspector();
  updateButtons();
  layout();
  preview();
}
function formatTime(seconds) {
  const m = Math.floor(seconds / 60),
    s = Math.round(seconds) % 60;
  return m ? m + "m " + s + "s" : Math.max(1, Math.round(seconds)) + "s";
}
function inspectField(group, label, type, value, change, opts = {}) {
  const row = node("label", "row");
  row.append(node("span", "", label));
  const field = node(type === "select" ? "select" : "input");
  if (type === "select")
    for (const [val, text] of opts.options) field.add(new Option(text, val));
  else field.type = type;
  if (type === "checkbox") field.checked = value;
  else field.value = value;
  for (const [k, v] of Object.entries(opts)) if (k !== "options") field[k] = v;
  field.onchange = () => {
    if (
      !field.reportValidity() ||
      (type === "number" && !Number.isFinite(field.valueAsNumber))
    ) {
      inspector();
      return;
    }
    checkpoint();
    stopPlay();
    change(
      type === "checkbox"
        ? field.checked
        : type === "number"
          ? field.valueAsNumber
          : field.value,
    );
    changed();
  };
  row.append(field);
  group.append(row);
}
const styles = ["Studio", "Headline", "Cinema", "Boxed", "Signal"];
function inspector() {
  const host = $("inspect");
  host.replaceChildren();
  const c = selected();
  if (!c) {
    host.append(
      node(
        "div",
        "inspect-empty",
        "Select a timeline clip to adjust timing, position, audio or captions.",
      ),
    );
    return;
  }
  const a = ed.assets[c.asset],
    fps = ed.p.fps;
  const group = (title) => {
    const div = node("div", "group");
    div.append(node("h3", "", title));
    host.append(div);
    return div;
  };
  const g = group(a.name);
  inspectField(g, "Track", "select", c.track, (v) => (c.track = +v), {
    options: a.video
      ? [
          [2, "V2 · Overlay"],
          [1, "V1 · Video"],
          [0, "A1 · Audio"],
        ]
      : [[0, "A1 · Audio"]],
  });
  inspectField(g, "Start frame", "number", c.start, (v) => (c.start = v), {
    min: 0,
    max: 10000000,
    step: 1,
  });
  const arrange = button(
    "Close track gaps",
    "Move clips on this track together, starting at frame zero",
    () => {
      checkpoint();
      let next = 0;
      for (const item of ed.p.clips
        .filter((item) => item.track === c.track)
        .sort((a, b) => a.start - b.start)) {
        item.start = next;
        next += item.length;
      }
      changed("Track gaps closed");
    },
  );
  arrange.className = "wide";
  g.append(arrange);
  const available = a.still
    ? fps * 86400
    : Math.max(1, Math.round(((a.duration - c.offset) * fps) / c.rate));
  inspectField(
    g,
    "Length (frames)",
    "number",
    c.length,
    (v) => (c.length = v),
    { min: 1, max: available, step: 1 },
  );
  inspectField(
    g,
    "Source in (s)",
    "number",
    +c.offset.toFixed(4),
    (v) => {
      c.offset = v;
      if (!a.still)
        c.length = Math.min(
          c.length,
          Math.max(1, Math.round(((a.duration - v) * fps) / c.rate)),
        );
    },
    { min: 0, max: Math.max(0, a.duration - 0.001), step: "any" },
  );
  inspectField(
    g,
    "Clip speed",
    "number",
    c.rate,
    (v) => {
      c.length = Math.max(1, Math.round((c.length * c.rate) / v));
      c.rate = v;
    },
    { min: 0.25, max: 4, step: "any" },
  );
  if (a.video && c.track > 0) {
    const t = group("Transform");
    for (const [key, label, lo, hi] of [
      ["scale", "Size (%)", 5, 200],
      ["x", "Center X (%)", -100, 200],
      ["y", "Center Y (%)", -100, 200],
    ]) {
      inspectField(
        t,
        label,
        "number",
        Math.round(c[key] * 100),
        (v) => (c[key] = v / 100),
        { min: lo, max: hi, step: 1 },
      );
    }
    t.append(
      button("Center", "Align to canvas center", () => {
        checkpoint();
        c.x = c.y = 0.5;
        changed("Clip centered");
      }),
    );
  }
  if (a.audio) {
    const t = group("Audio");
    inspectField(
      t,
      "Volume (%)",
      "number",
      Math.round(c.volume * 100),
      (v) => (c.volume = v / 100),
      { min: 0, max: 100 },
    );
    inspectField(t, "Preview only", "checkbox", c.guide, (v) => (c.guide = v));
  }
  const t = group("Captions & local AI");
  inspectField(t, "Template", "select", c.style, (v) => (c.style = v), {
    options: styles.map((s) => [s, s]),
  });
  const actions = [["Edit captions", () => editCues(c)]];
  if (a.audio) actions.push(["Transcribe with Whisper", () => whisper(c)]);
  if (a.video) actions.push(["Remove background", () => background(c)]);
  for (const [label, fn] of actions) {
    const b = button(label, label, safe(fn));
    b.className = "wide";
    t.append(b);
  }
}
function showForm(title, fields, accept, submit = "Apply", note = "") {
  stopPlay();
  const dialog = $("modal");
  if (dialog.open) dialog.close();
  $("dialog-title").textContent = title;
  $("submit").textContent = submit;
  const container = $("fields");
  container.replaceChildren();
  const controls = {};
  for (const f of fields) {
    const label = node("label", "", f.label),
      input = node(f.options ? "select" : f.area ? "textarea" : "input");
    if (f.options)
      for (const o of f.options) {
        const [v, t] = Array.isArray(o) ? o : [o, o];
        input.add(new Option(t, v));
      }
    else if (!f.area) input.type = f.type || "text";
    if (f.area) input.rows = f.rows || 6;
    if (f.value !== undefined) input.value = f.value;
    for (const k of [
      "min",
      "max",
      "step",
      "placeholder",
      "required",
      "maxLength",
    ])
      if (f[k] !== undefined) input[k] = f[k];
    input.name = f.key;
    controls[f.key] = input;
    label.append(input);
    container.append(label);
  }
  const help = node("p", "", note),
    err = node("p", "error");
  container.append(help, err);
  $("form").onsubmit = async (e) => {
    e.preventDefault();
    const values = {};
    for (const [k, input] of Object.entries(controls)) values[k] = input.value;
    try {
      const next = accept(values);
      if (next instanceof Promise) {
        if ($("dialog-title").textContent === title) dialog.close();
        await next;
      } else dialog.close();
    } catch (error) {
      if (dialog.open) err.textContent = error.message;
      else message(error);
    }
  };
  dialog.showModal();
  return { controls, help };
}
async function task(kind, data, title) {
  if (taskRunning) throw Error("Another task is running.");
  stopPlay();
  taskRunning = true;
  $("busy").hidden = false;
  $("busy-title").textContent = title;
  $("change-model").hidden = kind !== "whisper";
  $("change-model").disabled = true;
  $("busy-label").textContent = "Preparing…";
  $("progress").removeAttribute("value");
  $("stop-job").disabled = true;
  try {
    const started = await api(kind, data);
    if (!started) return null;
    $("stop-job").disabled = false;
    $("change-model").disabled = false;
    while (true) {
      const j = await api("job");
      if (j.status === "done") return j.result;
      if (j.status === "error") throw Error(j.result);
      if (j.status === "cancelled") {
        status("Task cancelled");
        return null;
      }
      $("busy-label").textContent = j.label || "Working…";
      if (j.fraction == null) $("progress").removeAttribute("value");
      else $("progress").value = j.fraction;
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
  } finally {
    taskRunning = false;
    $("busy").hidden = true;
    $("change-model").hidden = true;
  }
}
function register(assets) {
  for (const a of assets) {
    ed.assets[a.id] = a;
    if (!ed.p.library.includes(a.id)) ed.p.library.push(a.id);
  }
}
async function importMedia() {
  const results = await task("import", {}, "Import media");
  if (!results?.length) return;
  checkpoint();
  const first = !ed.p.clips.length;
  register(results);
  if (first) {
    for (const a of results) addClip(a.id);
    seek(0);
  }
  changed(results.length + " media file(s) imported");
  if (first) fit();
}
function replaceProject(doc) {
  if (!doc) return;
  stopPlay();
  clearTimeout(autoTimer);
  revision++;
  Object.assign(ed, {
    p: doc.project,
    selected: doc.project.clips[0]?.id || null,
    activeAsset: null,
    frame: 0,
    history: [],
    future: [],
    dirty: false,
  });
  for (const a of doc.assets) ed.assets[a.id] = a;
  refresh();
  fit();
}
async function save(as = false) {
  const path = await api("save", { project: ed.p, as });
  if (path) {
    ed.dirty = false;
    $("save-state").textContent = "Saved";
    status("Saved · " + path);
  }
}
function permissionToSwitch() {
  return (
    !ed.dirty ||
    confirm("Leave this project? Save it first to keep a named copy.")
  );
}
async function fileAction(action) {
  $("file-menu").hidden = true;
  if (action === "save" || action === "save-as")
    return save(action === "save-as");
  if (!permissionToSwitch()) return;
  stopPlay();
  clearTimeout(autoTimer);
  if (action === "new") {
    await api("new");
    replaceProject({ project: blank(), assets: [] });
    return;
  }
  if (action === "demo" || action === "open" || action === "recover") {
    $("busy").hidden = false;
    $("busy-title").textContent =
      action === "demo" ? "Opening Orbital study" : "Opening project";
    $("busy-label").textContent =
      action === "demo"
        ? "Preparing the example footage on this computer…"
        : "Reading source media…";
    $("stop-job").disabled = true;
    $("progress").removeAttribute("value");
    try {
      replaceProject(await api(action));
    } finally {
      $("busy").hidden = true;
    }
  }
}
function projectSettings() {
  showForm(
    "Project settings",
    [
      {
        key: "size",
        label: "Canvas",
        options: canvasSizes(),
        value: ed.p.width + "x" + ed.p.height,
      },
      {
        key: "fps",
        label: "Timeline frame rate",
        options: [24, 25, 30, 48, 50, 60, 120],
        value: ed.p.fps,
      },
    ],
    (v) => {
      const fps = +v.fps,
        [w, h] = v.size.split("x").map(Number);
      checkpoint();
      for (const c of ed.p.clips) {
        const end = Math.round(((c.start + c.length) * fps) / ed.p.fps);
        c.start = Math.round((c.start * fps) / ed.p.fps);
        c.length = Math.max(1, end - c.start);
      }
      ed.frame = Math.round((ed.frame * fps) / ed.p.fps);
      Object.assign(ed.p, { width: w, height: h, fps });
      changed("Project settings applied");
      fit();
    },
    "Apply",
    "Changing the project frame rate rounds clip boundaries to the nearest new frame.",
  );
}
function canvasSizes() {
  return [
    ...new Set([
      ed.p.width + "x" + ed.p.height,
      "1920x1080",
      "1280x720",
      "3840x2160",
      "1080x1920",
      "720x1280",
      "1080x1080",
      "1080x1350",
      "854x480",
    ]),
  ].map((s) => [s, s.replace("x", " × ")]);
}
function exportDialog() {
  if (!ed.p.clips.length) return status("Add a clip before exporting.");
  const { controls } = showForm(
    "Export timeline",
    [
      {
        key: "format",
        label: "Format",
        options: [
          "mp4",
          "mov",
          "mkv",
          "webm",
          "mp3",
          "wav",
          "m4a",
          "flac",
          "srt",
        ].map((s) => [s, s.toUpperCase()]),
      },
      {
        key: "size",
        label: "Output resolution",
        options: canvasSizes(),
        value: ed.p.width + "x" + ed.p.height,
      },
      {
        key: "fps",
        label: "Output frame rate",
        options: [24, 25, 30, 48, 50, 60, 120],
        value: ed.p.fps,
      },
    ],
    async (v) => {
      if (v.format === "srt") {
        const path = await api("srt", { project: ed.p });
        if (path) status("Captions saved · " + path);
        return;
      }
      const [width, height] = v.size.split("x").map(Number);
      const result = await task(
        "export",
        { project: ed.p, format: v.format, width, height, fps: +v.fps },
        "Export timeline",
      );
      if (result) status("Exported · " + result);
    },
    "Choose destination…",
    "Exports use the original media. Preview-only clips are excluded.",
  );
  controls.format.onchange = () => {
    controls.size.disabled = controls.fps.disabled = ![
      "mp4",
      "mov",
      "mkv",
      "webm",
    ].includes(controls.format.value);
  };
}
function seconds(v) {
  if (!v.trim()) return null;
  if (!/^\d+(?::[0-5]?\d){0,2}(?:\.\d+)?$/.test(v.trim()))
    throw Error("Use seconds or HH:MM:SS.");
  return v
    .trim()
    .split(":")
    .reduce((acc, n) => acc * 60 + Number(n), 0);
}
function downloadDialog(guide = false) {
  showForm(
    guide ? "Import TikTok guide audio" : "Download media",
    [
      {
        key: "url",
        label: "YouTube or TikTok URL",
        type: "url",
        required: true,
        placeholder: "https://…",
      },
      { key: "from", label: "Start", value: "0:00" },
      {
        key: "to",
        label: "End",
        placeholder: "Leave empty for the full remainder",
      },
      {
        key: "transfer",
        label: "Transfer mode",
        options: [
          ["range", "Download the selected section"],
          ["full", "Download the full source, then trim locally"],
        ],
      },
      {
        key: "format",
        label: "Download format",
        options: guide ? ["mp3"] : ["mp4", "mp3"],
      },
      {
        key: "place",
        label: "Place downloaded media",
        options: guide
          ? [["guide", "Preview audio at playhead"]]
          : [
              ["append", "Append to timeline"],
              ["head", "Video or audio at playhead"],
              ["overlay", "Overlay at playhead"],
              ["guide", "Preview audio at playhead"],
              ["pool", "Media pool only"],
            ],
      },
    ],
    (v) => {
      const from = seconds(v.from) || 0,
        to = seconds(v.to);
      if (to !== null && to <= from) throw Error("End must be after start.");
      return (async () => {
        const results = await task(
          "download",
          { url: v.url, from, to, format: v.format, transfer: v.transfer },
          "Download media",
        );
        if (!results) return;
        checkpoint();
        register(results);
        const a = results[0];
        if (v.place !== "pool") {
          const c = addClip(
            a.id,
            v.place === "guide" ? 0 : v.place === "overlay" ? 2 : undefined,
            v.place === "append" ? undefined : ed.frame,
          );
          c.guide = v.place === "guide";
        }
        changed("Downloaded · " + a.name);
      })();
    },
    "Choose destination…",
    "Select the source interval, then choose the folder and filename.",
  );
}
function whisper(c) {
  const duration = (c.length * c.rate) / ed.p.fps;
  const { controls, help } = showForm(
    "Transcribe clip",
    [
      {
        key: "model",
        label: "Whisper model",
        options: Object.keys(settings.models),
        value: localStorage.getItem("model") || "base",
      },
      {
        key: "language",
        label: "Spoken language",
        placeholder: "Auto-detect, or enter en, ru, fa…",
      },
      {
        key: "style",
        label: "Caption template",
        options: styles,
        value: c.style,
      },
    ],
    async (v) => {
      localStorage.setItem("model", v.model);
      const result = await task(
        "whisper",
        {
          asset: c.asset,
          model: v.model,
          offset: c.offset,
          duration,
          language: v.language.trim().toLowerCase(),
        },
        "Local transcription",
      );
      if (!result) {
        if (changeModel) {
          changeModel = false;
          whisper(c);
        }
        return;
      }
      checkpoint();
      c.cues = result.cues;
      c.style = v.style;
      localStorage.setItem("speed-" + v.model, String(result.ratio));
      changed(result.cues.length + " caption segments created");
    },
    "Transcribe",
  );
  function estimate() {
    const m = controls.model.value,
      observed = Number(localStorage.getItem("speed-" + m)),
      ratio = observed || settings.models[m];
    help.className = "estimate";
    help.textContent =
      "Estimated recognition: " +
      formatTime(Math.max(1, duration * ratio * 0.65)) +
      "–" +
      formatTime(Math.max(2, duration * ratio * 1.6)) +
      " · " +
      (observed ? "based on your last run" : "rough CPU estimate") +
      ". Model loading time is extra. On Windows, add models in NanoCut Setup.";
  }
  controls.model.onchange = estimate;
  estimate();
}
function editCues(c) {
  const fps = ed.p.fps,
    a = ed.assets[c.asset];
  const content = c.cues
    .map(
      (q) =>
        q.in.toFixed(3) +
        " | " +
        q.out.toFixed(3) +
        " | " +
        q.text.replace(/\n/g, " "),
    )
    .join("\n");
  showForm(
    "Edit captions",
    [
      {
        key: "text",
        label: "Source start | source end | caption",
        area: true,
        rows: 10,
        value: content,
        placeholder:
          c.offset.toFixed(3) +
          " | " +
          (c.offset + Math.min(2, (c.length * c.rate) / fps)).toFixed(3) +
          " | Your caption",
      },
    ],
    (v) => {
      const cues = v.text
        .split("\n")
        .filter((s) => s.trim())
        .map((s, i) => {
          const parts = s.split("|"),
            start = seconds(parts.shift() || ""),
            end = seconds(parts.shift() || ""),
            text = parts.join("|").trim();
          if (
            start === null ||
            end === null ||
            end <= start ||
            !text ||
            (!a.still && end > a.duration + 0.05)
          )
            throw Error("Check timing and text on line " + (i + 1) + ".");
          return { in: start, out: end, text };
        });
      checkpoint();
      c.cues = cues;
      changed("Captions updated");
    },
    "Save captions",
    "Enter one cue per line. Source times are in seconds and follow the clip through splits, trims and speed changes.",
  );
}
function background(c) {
  showForm(
    "Remove background",
    [],
    async () => {
      const a = ed.assets[c.asset],
        offset = c.offset;
      const result = await task(
        "cutout",
        {
          asset: c.asset,
          offset,
          duration: (c.length * c.rate) / ed.p.fps,
          fps: ed.p.fps,
        },
        "Local background removal",
      );
      if (!result) return;
      checkpoint();
      register(result);
      c.asset = result[0].id;
      c.offset = 0;
      c.cues = c.cues.map((q) => ({
        ...q,
        in: q.in - offset,
        out: q.out - offset,
      }));
      changed("Background removed · original retained in media pool");
    },
    "Choose destination…",
    "Create a transparent foreground from the selected source interval. Videos render locally at up to 1280 px on the long edge. On Windows, select background removal in NanoCut Setup.",
  );
}
function tiktok() {
  const opts = [
    ["music", "Import guide audio from a TikTok video"],
    ["local", "Import a local guide track"],
    ["web", "Open TikTok web uploader"],
  ];
  if (settings.tiktok)
    opts.push([
      "draft",
      "Authorize and send an exported MP4 to my TikTok inbox",
    ]);
  showForm(
    "TikTok studio",
    [{ key: "action", label: "Action", options: opts }],
    async (v) => {
      if (v.action === "music") {
        downloadDialog(true);
        return;
      }
      if (v.action === "web") {
        window.open(
          "https://www.tiktok.com/upload",
          "_blank",
          "noopener,noreferrer",
        );
        return;
      }
      if (v.action === "local") {
        const r = await task("import", {}, "Import preview music");
        if (!r) return;
        checkpoint();
        register(r);
        for (const a of r)
          if (a.audio) {
            const c = addClip(a.id, 0, ed.frame);
            c.guide = true;
          }
        changed("Preview music imported");
        return;
      }
      const r = await task("tiktok", {}, "Send TikTok draft");
      if (r) status(r);
    },
    "Continue",
    "Guide audio plays in the editor and is omitted from export. Add the official sound in TikTok. In-app draft transfer requires an approved developer app configured on this computer.",
  );
}
function shortcuts() {
  showForm(
    "Keyboard shortcuts",
    [],
    () => {},
    "Done",
    "Space · play/pause. Left / Right · step one frame. Shift + arrow · step ten frames. S · split. Delete · remove. Ctrl D · duplicate. Ctrl Z / Ctrl Shift Z · undo/redo. + / − · zoom. Home / End · jump. Alt-drag · bypass snapping. Drag the edges of a clip to trim.",
  );
}
function initCanvasDrag() {
  const stage = $("stage");
  let drag = null;
  stage.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || !e.target.dataset.clip) return;
    stopPlay();
    ed.selected = e.target.dataset.clip;
    const c = selected();
    inspector();
    drawTimeline();
    updateButtons();
    drag = { c, x: c.x, y: c.y, px: e.clientX, py: e.clientY, moved: false };
    stage.setPointerCapture(e.pointerId);
  });
  stage.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const { c, px, py } = drag,
      rect = stage.getBoundingClientRect(),
      a = ed.assets[c.asset];
    if (!drag.moved && Math.hypot(e.clientX - px, e.clientY - py) < 3) return;
    if (!drag.moved) {
      checkpoint();
      drag.moved = true;
    }
    const fitScale =
      Math.min(rect.width / a.width, rect.height / a.height) * c.scale;
    function align(v, size, span) {
      const half = (size * fitScale) / (2 * span);
      if (ed.snap && !e.altKey)
        for (const point of [0.5, half, 1 - half])
          if (Math.abs(point - v) * span < 7) return point;
      return clamp(v, -1, 2);
    }
    c.x = align(drag.x + (e.clientX - px) / rect.width, a.width, rect.width);
    c.y = align(drag.y + (e.clientY - py) / rect.height, a.height, rect.height);
    stage.classList.toggle("guides", ed.snap && !e.altKey);
    preview();
  });
  function end() {
    stage.classList.remove("guides");
    if (drag?.moved) changed("Clip positioned");
    drag = null;
  }
  stage.addEventListener("pointerup", end);
  stage.addEventListener("pointercancel", end);
}
async function init() {
  initTimeline();
  initCanvasDrag();
  settings = await api("state");
  $("file-menu").querySelector('[data-action="recover"]').disabled =
    !settings.recover;
  for (const [id, action] of Object.entries({
    import: importMedia,
    "welcome-import": importMedia,
    download: () => downloadDialog(),
    demo: () => fileAction("demo"),
    "project-settings": projectSettings,
    export: exportDialog,
    shortcuts: shortcuts,
    tiktok: tiktok,
  })) {
    $(id).onclick = safe(action);
  }
  $("project-menu").onclick = (e) => {
    e.stopPropagation();
    $("file-menu").hidden = !$("file-menu").hidden;
  };
  for (const b of $("file-menu").querySelectorAll("button"))
    b.onclick = safe(() => fileAction(b.dataset.action));
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".menu-wrap")) $("file-menu").hidden = true;
  });
  $("name").onchange = () => {
    checkpoint();
    ed.p.name = $("name").value.trim() || "Untitled project";
    changed();
  };
  $("play").onclick = togglePlay;
  $("play-rate").onchange = () => {
    if (ed.playing) {
      stopPlay();
      togglePlay();
    }
  };
  $("prev").onclick = () => {
    stopPlay();
    seek(ed.frame - 1, true);
  };
  $("next").onclick = () => {
    stopPlay();
    seek(ed.frame + 1, true);
  };
  $("close-modal").onclick = $("modal-cancel").onclick = () =>
    $("modal").close();
  $("change-model").onclick = safe(async () => {
    changeModel = true;
    $("change-model").disabled = true;
    await api("cancel");
  });
  $("stop-job").onclick = safe(async () => {
    $("stop-job").disabled = true;
    await api("cancel");
  });
  window.addEventListener(
    "keydown",
    safe(async (e) => {
      if (
        $("modal").open ||
        !$("busy").hidden ||
        e.target.closest("input,select,textarea")
      )
        return;
      const mod = e.ctrlKey || e.metaKey,
        k = e.key.toLowerCase();
      if (mod && ["z", "y", "s", "o", "n", "d"].includes(k)) {
        e.preventDefault();
        if (k === "z" || k === "y") restore(k === "y" || e.shiftKey);
        else if (k === "d") duplicate();
        else
          await fileAction(
            { s: e.shiftKey ? "save-as" : "save", o: "open", n: "new" }[k],
          );
        return;
      }
      if (
        [
          " ",
          "arrowleft",
          "arrowright",
          "home",
          "end",
          "s",
          "delete",
          "backspace",
          "=",
          "+",
          "-",
        ].includes(k)
      ) {
        e.preventDefault();
        if (k === " ") togglePlay();
        else if (k === "s") splitClip();
        else if (k === "delete" || k === "backspace") removeClip();
        else if (["=", "+", "-"].includes(k))
          zoomTo(ed.zoom + (k === "-" ? -5 : 5));
        else {
          stopPlay();
          seek(
            k === "home"
              ? 0
              : k === "end"
                ? endFrame()
                : ed.frame +
                  (k === "arrowleft" ? -1 : 1) * (e.shiftKey ? 10 : 1),
            true,
          );
        }
      }
    }),
  );
  new ResizeObserver(() => {
    layout();
    drawTimeline();
  }).observe($("viewer"));
  window.addEventListener("beforeunload", (e) => {
    if (ed.dirty || taskRunning) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
  refresh();
  if (settings.recover)
    status("Previous session available in File → Recover last session");
}
init().catch(message);
