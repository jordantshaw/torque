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
