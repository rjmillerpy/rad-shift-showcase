"""Starter widget code for state management and WebGL (product roadmap Phase 1).

Self-contained: no libraries from a CDN, so a starter never loads a script
whose version isn't pinned. Each one marks itself ready (data-* on <body>)
so the end-to-end tests can see it working in a real browser.
"""

# A Redux-style store in ~40 lines: one state object, changed only by
# dispatching actions through a reducer, with subscribers that re-render.
# It saves the state with radshift.storage, so it survives a reload.
STATE_STORE_CODE = """<div id="app">
  <h3>Counter (Redux-style store)</h3>
  <p><span id="count">0</span> &middot; <small id="status">loading</small></p>
  <button data-action="increment">+1</button>
  <button data-action="decrement">-1</button>
  <button data-action="reset">Reset</button>
</div>
<style>
  body { font-family: system-ui, sans-serif; padding: 12px; }
  button { margin-right: 6px; padding: 6px 12px; }
  #count { font-size: 28px; font-weight: 600; }
</style>
<script>
  // The reducer: (state, action) -> new state. The only place state changes.
  function reducer(state, action) {
    switch (action.type) {
      case "increment": return { count: state.count + 1 };
      case "decrement": return { count: state.count - 1 };
      case "reset": return { count: 0 };
      case "load": return action.state;
      default: return state;
    }
  }

  function createStore(reducer, initial) {
    var state = initial;
    var listeners = [];
    return {
      getState: function () { return state; },
      dispatch: function (action) {
        state = reducer(state, action);
        listeners.forEach(function (listener) { listener(state, action); });
      },
      subscribe: function (listener) { listeners.push(listener); },
    };
  }

  var store = createStore(reducer, { count: 0 });
  // Not `var status`: at the top level that is window.status, which turns
  // anything assigned to it into a string, so the element would be lost.
  var statusText = document.getElementById("status");

  // Render on every change; save every change the user makes.
  store.subscribe(function (state, action) {
    document.getElementById("count").textContent = String(state.count);
    if (action.type === "load") return;
    radshift.storage.set("state", state)
      .then(function () { statusText.textContent = "saved"; })
      .catch(function (error) { statusText.textContent = error.message; });
  });

  document.getElementById("app").addEventListener("click", function (event) {
    var type = event.target.getAttribute("data-action");
    if (type) store.dispatch({ type: type });
  });

  radshift.storage.get("state")
    .then(function (saved) {
      if (saved) store.dispatch({ type: "load", state: saved });
      statusText.textContent = saved ? "restored" : "new";
    })
    .catch(function (error) { statusText.textContent = error.message; })
    .then(function () { document.body.dataset.ready = "yes"; });
</script>
"""

# A spinning triangle drawn with raw WebGL (no library): shaders, a vertex
# buffer and an animation loop. Shows a message where WebGL is unavailable.
WEBGL_CODE = """<canvas id="scene" width="300" height="220"></canvas>
<p id="status">starting</p>
<style>
  body { margin: 0; padding: 8px; font-family: system-ui, sans-serif; background: #111; color: #ddd; }
  canvas { display: block; background: #000; border-radius: 6px; }
</style>
<script>
  var canvas = document.getElementById("scene");
  // Not `var status`: at the top level that is window.status, which turns
  // anything assigned to it into a string, so the element would be lost.
  var statusText = document.getElementById("status");
  // preserveDrawingBuffer: the pixels stay readable after a frame (tests check one).
  var gl = canvas.getContext("webgl", { preserveDrawingBuffer: true });

  function compile(type, source) {
    var shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
    return shader;
  }

  if (!gl) {
    statusText.textContent = "WebGL isn't available in this browser";
    document.body.dataset.webgl = "unavailable";
  } else {
    var program = gl.createProgram();
    gl.attachShader(program, compile(gl.VERTEX_SHADER,
      "attribute vec2 position; attribute vec3 color; uniform float angle; varying vec3 tint;" +
      "void main() { float c = cos(angle), s = sin(angle);" +
      "  gl_Position = vec4(c * position.x - s * position.y, s * position.x + c * position.y, 0.0, 1.0);" +
      "  tint = color; }"));
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER,
      "precision mediump float; varying vec3 tint; void main() { gl_FragColor = vec4(tint, 1.0); }"));
    gl.linkProgram(program);
    gl.useProgram(program);

    // x, y, r, g, b for each corner.
    var vertices = new Float32Array([0, 0.8, 1, 0.2, 0.3,  -0.7, -0.5, 0.2, 1, 0.4,  0.7, -0.5, 0.3, 0.4, 1]);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);
    var stride = 5 * 4;
    var position = gl.getAttribLocation(program, "position");
    var color = gl.getAttribLocation(program, "color");
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, stride, 0);
    gl.enableVertexAttribArray(color);
    gl.vertexAttribPointer(color, 3, gl.FLOAT, false, stride, 2 * 4);
    var angle = gl.getUniformLocation(program, "angle");

    function frame(time) {
      gl.clearColor(0, 0, 0, 1);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform1f(angle, time / 1000);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(function (time) {
      frame(time);
      // The centre pixel is inside the triangle at every angle: lit means it drew.
      var pixel = new Uint8Array(4);
      gl.readPixels(canvas.width / 2, canvas.height / 2, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
      var drew = pixel[0] + pixel[1] + pixel[2] > 0;
      statusText.textContent = drew ? "WebGL drawing" : "WebGL started, nothing drawn";
      document.body.dataset.webgl = drew ? "drawing" : "blank";
    });
  }
</script>
"""
