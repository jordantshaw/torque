// Loaded on every page (deferred, after htmx). No inline scripts are allowed
// by the Content-Security-Policy, so all page behaviour lives in /static.

// htmx configuration -------------------------------------------------------
// Swap 4xx/5xx bodies too (while still firing htmx:responseError). Without
// this, routes that re-render a partial with a 400 to show inline validation
// errors would never update the page, since htmx treats 4xx/5xx as errors.
htmx.config.responseHandling = [
  {code: "204", swap: false},
  {code: "[23]..", swap: true},
  {code: "[45]..", swap: true, error: true}
];
// Never run scripts or evaluate code that arrives in a response.
htmx.config.allowScriptTags = false;
htmx.config.allowEval = false;
// The indicator styles htmx injects would need an inline-style exception.
htmx.config.includeIndicatorStyles = false;

// A swap replaces the whole panel, which would collapse every <details> the
// reader had opened. Remember each one marked data-keep-open by its key (open
// or closed) and put it back once the new panel is in place.
var keptOpen = null;
document.addEventListener("htmx:beforeSwap", function (event) {
  var target = event.detail.target;
  keptOpen = null;
  if (!target || !target.querySelectorAll) return;
  var groups = target.querySelectorAll("details[data-keep-open]");
  if (!groups.length) return;
  keptOpen = {};
  groups.forEach(function (group) {
    keptOpen[group.dataset.keepOpen] = group.open;
  });
});
document.addEventListener("htmx:afterSwap", function () {
  if (!keptOpen) return;
  document.querySelectorAll("details[data-keep-open]").forEach(function (group) {
    var was = keptOpen[group.dataset.keepOpen];
    if (was !== undefined) group.open = was;
  });
  keptOpen = null;
});

// Confirm before anything marked data-confirm (deleting, clearing history).
document.addEventListener("submit", function (event) {
  var message = event.target.dataset && event.target.dataset.confirm;
  if (message && !window.confirm(message)) event.preventDefault();
});

// /bikes/N#hours (from the hour counter) lands in the reading field.
if (location.hash === "#hours") {
  var field = document.getElementById("hours");
  if (field) { field.focus(); field.select(); }
}
