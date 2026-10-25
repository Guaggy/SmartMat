"use strict";
// SmartMat dashboard: the pressure map. Plain JS, no libraries.
//  - heat layer: a WebGL fragment shader (Catmull-Rom bicubic, 9 texture taps, colour ramp as a 1D texture) on a canvas
//    sized to its CSS size x devicePixelRatio; without WebGL the same picture is built on a 2D canvas (bicubic 4x
//    upsample, then the browser scales it smoothly);
//  - overlay layer (2D canvas): the outline of every hotspot follows the real shape of its cell set (marching squares on
//    a blurred mask, then smoothed), a small label, the selected state and the centre of pressure;
//  - motion: the grid and the outlines are tweened between consecutive polls with requestAnimationFrame. The loop only
//    runs while something is moving and the tab is visible, so an idle page costs nothing.
// The caller gives grids in the API's orientation (row 0 = back of the seat); the map is turned half a turn (front on
// top, the sitter's left and right stay on the viewer's left and right) in here.
const HeatMap = (() => {
  const PAD = 2;            // mask padding in cells, so outlines at the seat edge run off the map instead of closing on it
  const LEVEL = 0.4;        // contour level of the blurred mask: the outline sits just outside the outer cells
  const MAX_HEAT_PX = 720;  // backing-store cap of the heat canvas (it is smooth, so this is invisible and a Pi 4 copes)
  const FRAME_MS = 30;      // the tween redraws at most ~30 times a second
  const MAX_OVERLAY_PX = 1800;
  const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);

  // ---------- hotspot shapes ----------
  function maskField(cells, rows, cols) { // blurred 0..1 mask of a cell list, (rows + 2 PAD) x (cols + 2 PAD)
    const W = cols + 2 * PAD, H = rows + 2 * PAD, m = new Float32Array(W * H);
    for (const [r, c] of cells) m[(r + PAD) * W + c + PAD] = 1;
    for (let i = 0; i < H; i++) {
      const si = clamp(i, PAD, rows - 1 + PAD);
      for (let j = 0; j < W; j++) {
        if (i >= PAD && i < rows + PAD && j >= PAD && j < cols + PAD) continue;
        m[i * W + j] = m[si * W + clamp(j, PAD, cols - 1 + PAD)];
      }
    }
    const t = new Float32Array(W * H);
    for (let i = 0; i < H; i++) for (let j = 0; j < W; j++) {
      t[i * W + j] = (m[i * W + Math.max(j - 1, 0)] + 2 * m[i * W + j] + m[i * W + Math.min(j + 1, W - 1)]) / 4;
    }
    for (let i = 0; i < H; i++) for (let j = 0; j < W; j++) {
      m[i * W + j] = (t[Math.max(i - 1, 0) * W + j] + 2 * t[i * W + j] + t[Math.min(i + 1, H - 1) * W + j]) / 4;
    }
    for (let i = 0; i < H; i++) for (let j = 0; j < W; j++) if (i === 0 || j === 0 || i === H - 1 || j === W - 1) m[i * W + j] = 0;
    return m;
  }

  // Marching squares at LEVEL; the segments are chained into closed loops of [x, y] in cell units.
  function contours(f, W, H) {
    const pts = new Map(), adj = new Map(), NV = W * H;
    const point = (key, ax, ay, av, bx, by, bv) => {
      if (!pts.has(key)) { const u = (LEVEL - av) / (bv - av); pts.set(key, [ax + (bx - ax) * u, ay + (by - ay) * u]); }
      return key;
    };
    const link = (a, b) => {
      if (!adj.has(a)) adj.set(a, []);
      if (!adj.has(b)) adj.set(b, []);
      adj.get(a).push(b);
      adj.get(b).push(a);
    };
    for (let i = 0; i < H - 1; i++) for (let j = 0; j < W - 1; j++) {
      const tl = f[i * W + j], tr = f[i * W + j + 1], br = f[(i + 1) * W + j + 1], bl = f[(i + 1) * W + j];
      const c = (tl >= LEVEL ? 1 : 0) | (tr >= LEVEL ? 2 : 0) | (br >= LEVEL ? 4 : 0) | (bl >= LEVEL ? 8 : 0);
      if (c === 0 || c === 15) continue;
      const T = () => point(i * W + j, j, i, tl, j + 1, i, tr);
      const R = () => point(NV + i * W + j + 1, j + 1, i, tr, j + 1, i + 1, br);
      const B = () => point((i + 1) * W + j, j, i + 1, bl, j + 1, i + 1, br);
      const L = () => point(NV + i * W + j, j, i, tl, j, i + 1, bl);
      const inside = (tl + tr + br + bl) / 4 >= LEVEL;
      let segs;
      switch (c) {
        case 1: case 14: segs = [[L, T]]; break;
        case 2: case 13: segs = [[T, R]]; break;
        case 3: case 12: segs = [[L, R]]; break;
        case 4: case 11: segs = [[R, B]]; break;
        case 6: case 9: segs = [[T, B]]; break;
        case 7: case 8: segs = [[L, B]]; break;
        case 5: segs = inside ? [[T, R], [B, L]] : [[L, T], [R, B]]; break;
        default: segs = inside ? [[L, T], [R, B]] : [[T, R], [B, L]]; // 10
      }
      for (const [a, b] of segs) link(a(), b());
    }
    const loops = [], seen = new Set();
    for (const start of adj.keys()) {
      if (seen.has(start)) continue;
      const loop = [];
      let prev = -1, cur = start;
      while (!seen.has(cur)) {
        seen.add(cur);
        const p = pts.get(cur);
        loop.push([p[0] - PAD + 0.5, p[1] - PAD + 0.5]);
        const [a, b] = adj.get(cur);
        const next = a !== prev ? a : b;
        prev = cur;
        cur = next;
      }
      if (loop.length >= 3) loops.push(loop);
    }
    return loops;
  }

  function chaikin(loop, rounds) { // corner cutting: a polygon becomes a smooth closed curve
    for (; rounds > 0; rounds--) {
      const out = [];
      for (let k = 0; k < loop.length; k++) {
        const a = loop[k], b = loop[(k + 1) % loop.length];
        out.push([0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]], [0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]]);
      }
      loop = out;
    }
    return loop;
  }

  // ---------- heat layer ----------
  const VERT = "attribute vec2 p; void main() { gl_Position = vec4(p, 0.0, 1.0); }";
  const FRAG = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform sampler2D uV; uniform sampler2D uRamp; uniform vec2 uRes; uniform vec2 uTex;
float tap(vec2 q) { return texture2D(uV, q).r; }
void main() {
  vec2 uv = vec2(gl_FragCoord.x / uRes.x, 1.0 - gl_FragCoord.y / uRes.y);
  vec2 pos = uv * uTex;
  vec2 p1 = floor(pos - 0.5) + 0.5;
  vec2 f = pos - p1;
  vec2 w0 = f * (-0.5 + f * (1.0 - 0.5 * f));
  vec2 w1 = 1.0 + f * f * (-2.5 + 1.5 * f);
  vec2 w2 = f * (0.5 + f * (2.0 - 1.5 * f));
  vec2 w3 = f * f * (-0.5 + 0.5 * f);
  vec2 w12 = w1 + w2;
  vec2 p0 = (p1 - 1.0) / uTex, p3 = (p1 + 2.0) / uTex, p12 = (p1 + w2 / w12) / uTex;
  float v = tap(vec2(p0.x, p0.y)) * w0.x * w0.y + tap(vec2(p12.x, p0.y)) * w12.x * w0.y + tap(vec2(p3.x, p0.y)) * w3.x * w0.y
          + tap(vec2(p0.x, p12.y)) * w0.x * w12.y + tap(vec2(p12.x, p12.y)) * w12.x * w12.y + tap(vec2(p3.x, p12.y)) * w3.x * w12.y
          + tap(vec2(p0.x, p3.y)) * w0.x * w3.y + tap(vec2(p12.x, p3.y)) * w12.x * w3.y + tap(vec2(p3.x, p3.y)) * w3.x * w3.y;
  v = clamp(v, 0.0, 1.0);
  vec3 rgb = texture2D(uRamp, vec2(v * (255.0 / 256.0) + 0.5 / 256.0, 0.5)).rgb;
  float a = clamp((v - 0.02) / 0.16, 0.0, 1.0);
  a = a * a * (3.0 - 2.0 * a);   // low pressure fades out: the seat and its dot grid show through
  gl_FragColor = vec4(rgb * a, a);
}`;

  function glLayer(canvas, allowSoftware) { // null when WebGL is not available
    const probe = document.createElement("canvas").getContext("webgl");   // on a spare canvas: a canvas keeps its first context type
    if (!probe) return null;
    const info = probe.getExtension("WEBGL_debug_renderer_info");   // a software GL (no GPU) is slower than the 2D path
    const soft = info && /swiftshader|llvmpipe|softpipe|software/i.test(String(probe.getParameter(info.UNMASKED_RENDERER_WEBGL)));
    if (soft && !allowSoftware) return null;
    let gl = null, prog = null, texV = null, texR = null, loc = null, shape = [0, 0], ramp = null;
    const init = () => {
      gl = canvas.getContext("webgl", { alpha: true, premultipliedAlpha: true, antialias: false, depth: false, stencil: false, powerPreference: "low-power" });
      if (!gl) return false;
      const shader = (type, src) => {
        const s = gl.createShader(type);
        gl.shaderSource(s, src);
        gl.compileShader(s);
        if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
        return s;
      };
      prog = gl.createProgram();
      gl.attachShader(prog, shader(gl.VERTEX_SHADER, VERT));
      gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, FRAG));
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error("link");
      gl.useProgram(prog);
      gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
      const p = gl.getAttribLocation(prog, "p");
      gl.enableVertexAttribArray(p);
      gl.vertexAttribPointer(p, 2, gl.FLOAT, false, 0, 0);
      loc = { res: gl.getUniformLocation(prog, "uRes"), tex: gl.getUniformLocation(prog, "uTex") };
      const make = (unit) => {
        const t = gl.createTexture();
        gl.activeTexture(gl.TEXTURE0 + unit);
        gl.bindTexture(gl.TEXTURE_2D, t);
        for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
        return t;
      };
      texV = make(0);
      texR = make(1);
      gl.uniform1i(gl.getUniformLocation(prog, "uV"), 0);
      gl.uniform1i(gl.getUniformLocation(prog, "uRamp"), 1);
      gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
      shape = [0, 0];
      if (ramp) uploadRamp(ramp);
      return true;
    };
    const uploadRamp = (bytes) => {
      ramp = bytes;
      if (!gl) return;
      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_2D, texR);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, 256, 1, 0, gl.RGB, gl.UNSIGNED_BYTE, bytes);
    };
    try { if (!init()) return null; } catch (e) { return null; }
    canvas.addEventListener("webglcontextlost", (ev) => { ev.preventDefault(); gl = null; });
    canvas.addEventListener("webglcontextrestored", () => { try { init(); layer.restored(); } catch (e) { /* stays blank */ } });
    const layer = {
      kind: "webgl", restored: () => {},
      setRamp: uploadRamp,
      draw(values, rows, cols) { // values 0..1, rows x cols, display orientation
        if (!gl || !canvas.width) return;
        const bytes = new Uint8Array(rows * cols);
        for (let k = 0; k < bytes.length; k++) bytes[k] = Math.round(clamp(values[k], 0, 1) * 255);
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, texV);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.LUMINANCE, cols, rows, 0, gl.LUMINANCE, gl.UNSIGNED_BYTE, bytes);
        gl.viewport(0, 0, canvas.width, canvas.height);
        gl.uniform2f(loc.res, canvas.width, canvas.height);
        gl.uniform2f(loc.tex, cols, rows);
        gl.clearColor(0, 0, 0, 0);
        gl.clear(gl.COLOR_BUFFER_BIT);
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      },
    };
    return layer;
  }

  function canvasLayer(canvas) { // the same picture without WebGL: bicubic 4x upsample, the browser scales it up smoothly
    const ctx = canvas.getContext("2d"), small = document.createElement("canvas");
    const U = 4;
    const weights = Array.from({ length: U }, (_, k) => { // Catmull-Rom weights of the 4 neighbours at phase k / U
      const f = ((k + 0.5) / U + 0.5) % 1;
      return [f * (-0.5 + f * (1 - 0.5 * f)), 1 + f * f * (-2.5 + 1.5 * f), f * (0.5 + f * (2 - 1.5 * f)), f * f * (-0.5 + 0.5 * f)];
    });
    let lut = null;
    return {
      kind: "2d",
      setRamp(bytes) { lut = bytes; },
      draw(values, rows, cols) {
        if (!lut || !canvas.width) return;
        const R = rows * U, C = cols * U;
        const at = (r, c) => values[clamp(r, 0, rows - 1) * cols + clamp(c, 0, cols - 1)];
        const tmp = new Float32Array(R * cols); // vertical pass
        for (let y = 0; y < R; y++) {
          const w = weights[y % U], base = Math.floor((y + 0.5) / U - 0.5);
          for (let c = 0; c < cols; c++) tmp[y * cols + c] = at(base - 1, c) * w[0] + at(base, c) * w[1] + at(base + 1, c) * w[2] + at(base + 2, c) * w[3];
        }
        small.width = C; small.height = R;
        const sctx = small.getContext("2d"), img = sctx.createImageData(C, R);
        for (let y = 0; y < R; y++) for (let x = 0; x < C; x++) {
          const base = Math.floor((x + 0.5) / U - 0.5), w = weights[x % U];
          const g = (c) => tmp[y * cols + clamp(c, 0, cols - 1)];
          const v = clamp(g(base - 1) * w[0] + g(base) * w[1] + g(base + 1) * w[2] + g(base + 2) * w[3], 0, 1);
          let a = clamp((v - 0.02) / 0.16, 0, 1);
          a = a * a * (3 - 2 * a);
          const li = Math.round(v * 255) * 3, p = (y * C + x) * 4;
          img.data[p] = lut[li]; img.data[p + 1] = lut[li + 1]; img.data[p + 2] = lut[li + 2]; img.data[p + 3] = Math.round(a * 255);
        }
        sctx.putImageData(img, 0, 0);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = "high";
        ctx.drawImage(small, 0, 0, canvas.width, canvas.height);
      },
    };
  }

  // ---------- the map ----------
  function create({ seat, canvas, overlay, onPick, forceFallback = false }) {
    const heat = (!forceFallback && glLayer(canvas, /[?&]gl=force/.test(location.search))) || canvasLayer(canvas);
    const octx = overlay.getContext("2d");
    const reduceMotion = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)");
    let rows = 0, cols = 0, cur = null, from = null, to = null;
    let spots = new Map(), cop = null, copFrom = null, copTo = null, selected = null;
    let lastFrame = 0, t0 = 0, dur = 0, raf = 0, lastSet = 0, interval = 700, css = [0, 0], dpr = 1, colors = {}, drawMs = 0;

    const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    const refreshColors = () => {
      colors = { bad: cssVar("--bad") || "#A8231B", halo: cssVar("--panel") || "#fff", ink: cssVar("--ink") || "#10182B", on: cssVar("--on-fill") || "#fff" };
    };
    refreshColors();

    function setRamp(stops) { // [[position 0..1, [r,g,b]], ...]
      const bytes = new Uint8Array(256 * 3);
      for (let k = 0; k < 256; k++) {
        const v = k / 255;
        let i = 1;
        while (i < stops.length - 1 && v > stops[i][0]) i++;
        const f = clamp((v - stops[i - 1][0]) / (stops[i][0] - stops[i - 1][0] || 1), 0, 1);
        for (let q = 0; q < 3; q++) bytes[k * 3 + q] = Math.round(stops[i - 1][1][q] + (stops[i][1][q] - stops[i - 1][1][q]) * f);
      }
      heat.setRamp(bytes);
      redraw();
    }
    if (heat.kind === "webgl") heat.restored = () => redraw();

    function resize() { // canvases follow the CSS size x devicePixelRatio, so the map is sharp on any screen
      const w = seat.clientWidth, h = seat.clientHeight;
      if (!w || !h) return;
      dpr = window.devicePixelRatio || 1;
      const fit = (cap) => Math.min(1, cap / Math.max(w * dpr, h * dpr));
      const sized = (c, cap) => {
        const k = dpr * fit(cap), pw = Math.max(1, Math.round(w * k)), ph = Math.max(1, Math.round(h * k));
        if (c.width !== pw || c.height !== ph) { c.width = pw; c.height = ph; }
      };
      css = [w, h];
      sized(canvas, MAX_HEAT_PX);
      sized(overlay, MAX_OVERLAY_PX);
      redraw();
    }
    if (window.ResizeObserver) new ResizeObserver(resize).observe(seat); else window.addEventListener("resize", resize);

    // ---- data in
    const turn = (grid, scale) => { // half a turn and 0..1; unknown cells are empty
      const r = grid.length, c = grid[0].length, out = new Float32Array(r * c);
      for (let i = 0; i < r; i++) for (let j = 0; j < c; j++) {
        const v = grid[r - 1 - i][c - 1 - j];
        out[i * c + j] = v == null || !(scale > 0) ? 0 : v / scale;
      }
      return out;
    };
    const centroidOf = (cells) => {
      let y = 0, x = 0;
      for (const [r, c] of cells) { y += r; x += c; }
      return [x / cells.length + 0.5, y / cells.length + 0.5];
    };

    // set({grid, scale, spots: [{id, peak, persistent, cells}], cop: [row, col] | null, snap})
    function set(d) {
      const r = d.grid.length, c = d.grid[0].length, now = performance.now();
      const fresh = r !== rows || c !== cols || !cur;
      if (fresh) { rows = r; cols = c; spots = new Map(); cop = null; cur = null; }
      const target = turn(d.grid, d.scale);
      const copTarget = d.cop ? [cols - 1 - d.cop[1] + 0.5, rows - 1 - d.cop[0] + 0.5] : null;   // [x, y] in cell units
      const snap = d.snap || fresh || !!(reduceMotion && reduceMotion.matches);
      interval = lastSet ? clamp(now - lastSet, 120, 1200) : interval;
      lastSet = now;
      from = snap ? target : Float32Array.from(cur);
      to = target;
      copFrom = snap || !cop ? copTarget : cop.slice();
      copTo = copTarget;
      const seen = new Set();
      for (const s of d.spots) {
        const cells = s.cells.map(([a, b]) => [rows - 1 - a, cols - 1 - b]);
        let st = spots.get(s.id);
        const field = maskField(cells, rows, cols);
        if (!st) st = { id: s.id, cur: new Float32Array(field.length), c: centroidOf(cells), cFrom: null, cTo: null, set: new Set(), alpha: 0 };
        st.from = snap ? field : Float32Array.from(st.cur);
        st.to = field;
        st.cFrom = snap ? centroidOf(cells) : st.c.slice();
        st.cTo = centroidOf(cells);
        st.aFrom = snap ? 1 : st.alpha;
        st.aTo = 1;
        st.peak = s.peak; st.persistent = !!s.persistent; st.gone = false;
        st.set = new Set(cells.map(([a, b]) => a * cols + b));
        spots.set(s.id, st);
        seen.add(s.id);
      }
      for (const st of spots.values()) {
        if (seen.has(st.id)) continue;
        if (snap) { spots.delete(st.id); continue; }
        st.from = Float32Array.from(st.cur);
        st.to = new Float32Array(st.cur.length);
        st.cFrom = st.c.slice(); st.cTo = st.c.slice(); st.aFrom = st.alpha; st.aTo = 0; st.gone = true;
        st.set = new Set();
      }
      t0 = now;
      dur = snap ? 0 : interval;
      if (raf) { cancelAnimationFrame(raf); raf = 0; }
      lastFrame = 0;
      step(now);
    }

    // ---- motion: one rAF loop, only while something is moving
    function blend(e) {
      if (!cur || cur.length !== to.length) cur = new Float32Array(to.length);
      for (let k = 0; k < cur.length; k++) cur[k] = from[k] + (to[k] - from[k]) * e;
      for (const st of spots.values()) {
        for (let k = 0; k < st.cur.length; k++) st.cur[k] = st.from[k] + (st.to[k] - st.from[k]) * e;
        st.c = [st.cFrom[0] + (st.cTo[0] - st.cFrom[0]) * e, st.cFrom[1] + (st.cTo[1] - st.cFrom[1]) * e];
        st.alpha = st.aFrom + (st.aTo - st.aFrom) * e;
      }
      cop = copTo ? (copFrom ? [copFrom[0] + (copTo[0] - copFrom[0]) * e, copFrom[1] + (copTo[1] - copFrom[1]) * e] : copTo.slice()) : null;
    }
    function step(now) {
      raf = 0;
      const e = dur > 0 ? clamp((now - t0) / dur, 0, 1) : 1;
      if (e < 1 && now - lastFrame < FRAME_MS) { if (!document.hidden) raf = requestAnimationFrame(step); return; }
      lastFrame = now;
      blend(e);
      draw();
      if (e >= 1) {
        for (const [id, st] of spots) if (st.gone) spots.delete(id);
        return;
      }
      if (!document.hidden) raf = requestAnimationFrame(step);
    }
    document.addEventListener("visibilitychange", () => { if (!document.hidden && dur > 0 && !raf) raf = requestAnimationFrame(step); });

    // ---- drawing
    function draw() {
      if (!cur) return;
      const t = performance.now();
      heat.draw(cur, rows, cols);
      drawOverlay();
      drawMs = performance.now() - t;
    }
    function redraw() { if (cur && !raf) draw(); }

    function pathOf(loop, k) {
      octx.beginPath();
      loop.forEach(([x, y], i) => (i ? octx.lineTo(x * k[0], y * k[1]) : octx.moveTo(x * k[0], y * k[1])));
      octx.closePath();
    }
    function drawOverlay() {
      const W = overlay.width, H = overlay.height;
      octx.setTransform(1, 0, 0, 1, 0, 0);
      octx.clearRect(0, 0, W, H);
      if (!W) return;
      const k = [W / cols, H / rows], px = W / (css[0] || W); // px: canvas pixels per CSS pixel
      const order = [...spots.values()].sort((a, b) => (a.id === selected) - (b.id === selected));
      octx.lineJoin = octx.lineCap = "round";
      const loops = new Map();
      for (const st of order) {
        if (st.alpha <= 0.02) continue;
        const raw = contours(st.cur, cols + 2 * PAD, rows + 2 * PAD).map((l) => chaikin(l, 2));
        loops.set(st.id, raw);
        const sel = st.id === selected, dim = selected != null && !sel;
        octx.globalAlpha = clamp(st.alpha, 0, 1) * (dim ? 0.7 : 1);
        for (const loop of raw) {
          pathOf(loop, k);
          octx.setLineDash([]);
          octx.strokeStyle = colors.halo;
          octx.lineWidth = (sel ? 6 : st.persistent ? 4.4 : 3.8) * px;
          octx.stroke();
          octx.setLineDash(sel ? [] : [6 * px, 4 * px]);
          octx.strokeStyle = colors.bad;
          octx.lineWidth = (sel ? 3 : st.persistent ? 2.4 : 1.8) * px;
          octx.stroke();
        }
      }
      octx.globalAlpha = 1;
      octx.setLineDash([]);
      for (const st of order) if (st.alpha > 0.3) label(st, k, px, css[0] < 260);
      if (cop) marker(cop[0] * k[0], cop[1] * k[1], px);
    }
    function label(st, k, px, short) {
      const sel = st.id === selected, text = "#" + st.id + (short || st.peak == null ? "" : " " + Math.round(st.peak));
      octx.font = `600 ${11 * px}px "Segoe UI", system-ui, sans-serif`;
      const w = octx.measureText(text).width + 10 * px, h = 17 * px;
      const x = clamp(st.c[0] * k[0] - w / 2, 2 * px, overlay.width - w - 2 * px), y = clamp(st.c[1] * k[1] - h / 2, 2 * px, overlay.height - h - 2 * px);
      octx.globalAlpha = clamp(st.alpha, 0, 1);
      octx.beginPath();
      octx.roundRect ? octx.roundRect(x, y, w, h, h / 2) : octx.rect(x, y, w, h);
      octx.fillStyle = sel ? colors.bad : colors.halo;
      octx.fill();
      octx.lineWidth = 1.5 * px;
      octx.strokeStyle = colors.bad;
      octx.stroke();
      octx.fillStyle = sel ? colors.on : colors.bad;
      octx.textBaseline = "middle";
      octx.textAlign = "center";
      octx.fillText(text, x + w / 2, y + h / 2 + 0.5 * px);
      octx.globalAlpha = 1;
    }
    function marker(x, y, px) { // centre of pressure: a small cross in a ring
      const r = 6 * px, arms = (width, style) => {
        octx.lineWidth = width; octx.strokeStyle = style;
        octx.beginPath(); octx.arc(x, y, r, 0, 2 * Math.PI);
        octx.moveTo(x - r * 1.7, y); octx.lineTo(x + r * 1.7, y); octx.moveTo(x, y - r * 1.7); octx.lineTo(x, y + r * 1.7);
        octx.stroke();
      };
      arms(4 * px, colors.halo);
      arms(1.6 * px, colors.ink);
    }

    // ---- picking: a click inside (or near) a hotspot selects it
    overlay.addEventListener("click", (ev) => {
      if (!onPick || !cols) return;
      const b = overlay.getBoundingClientRect(), x = (ev.clientX - b.left) / b.width * cols, y = (ev.clientY - b.top) / b.height * rows;
      let best = null, bestD = 2.2;
      for (const st of spots.values()) {
        if (st.gone) continue;
        const inside = st.set.has(Math.floor(y) * cols + Math.floor(x));
        const d = inside ? 0 : Math.hypot(st.cTo[0] - x, st.cTo[1] - y);
        if (d < bestD) { best = st.id; bestD = d; }
      }
      onPick(best);
    });

    return {
      kind: heat.kind, setRamp, set, resize, refreshColors: () => { refreshColors(); redraw(); },
      select(id) { selected = id; redraw(); },
      reset() { cur = null; spots = new Map(); cop = null; selected = null; rows = cols = 0; octx.clearRect(0, 0, overlay.width, overlay.height); },
      drawNow: draw,
      get lastDrawMs() { return drawMs; },
      get moving() { return !!raf; },
    };
  }

  return { create };
})();
