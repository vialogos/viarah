(function () {
  var body = document.body;
  var track = body.getAttribute("data-track") || "unknown-track";
  var viewport = body.getAttribute("data-viewport") || "unknown-viewport";
  var stamp = document.querySelector("[data-js='stamp']");
  if (stamp) {
    stamp.textContent = "Track: " + track + " | Viewport: " + viewport + " | Static HTML mockup";
  }
})();
