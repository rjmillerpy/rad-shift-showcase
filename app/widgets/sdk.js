/* RadShift widget SDK, added to every rendered widget (app/widgets/views.py).
 *
 *   await radshift.storage.set("best", 42);
 *   const best = await radshift.storage.get("best");   // undefined if never set
 *   await radshift.storage.remove("best");
 *   const keys = await radshift.storage.keys();
 *
 * Values are any JSON, saved for the signed-in viewer, per widget (100 keys,
 * 10 KB each). The widget runs in a sandboxed iframe with no storage of its
 * own, so each call asks the page around it, which saves through the API.
 */
(function () {
  "use strict";
  var REQUEST = "radshift:storage";
  var RESULT = "radshift:storage:result";
  var TIMEOUT_MS = 10000;
  var pending = {};
  var nextId = 0;

  function call(op, key, value) {
    return new Promise(function (resolve, reject) {
      var id = ++nextId;
      var timer = setTimeout(function () {
        delete pending[id];
        reject(new Error("radshift.storage: no answer from the page"));
      }, TIMEOUT_MS);
      pending[id] = { resolve: resolve, reject: reject, timer: timer };
      window.parent.postMessage({ type: REQUEST, id: id, op: op, key: key, value: value }, "*");
    });
  }

  window.addEventListener("message", function (event) {
    var message = event.data;
    if (event.source !== window.parent || !message || message.type !== RESULT) return;
    var request = pending[message.id];
    if (!request) return;
    delete pending[message.id];
    clearTimeout(request.timer);
    if (message.ok) request.resolve(message.value);
    else request.reject(new Error(message.error));
  });

  window.radshift = window.radshift || {};
  window.radshift.storage = {
    get: function (key) { return call("get", key); },
    set: function (key, value) { return call("set", key, value); },
    remove: function (key) { return call("remove", key); },
    keys: function () { return call("keys"); },
  };
})();
