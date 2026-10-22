// The Garage page: the "Add a bike" panel and the bulk-selection bar.

(function () {
  // Add-a-bike panel. The server renders it hidden unless there is a reason to
  // show it (no bikes yet, or a failed submission); without JavaScript the
  // button is a plain #add-bike link and CSS shows the panel on :target.
  var panel = document.getElementById("add-bike");
  var toggle = document.getElementById("add-bike-toggle");
  if (panel && toggle) {
    var setOpen = function (open) {
      panel.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
      if (open) {
        var field = document.getElementById("nickname");
        if (field) field.focus();
      }
    };
    setOpen(!panel.hidden || location.hash === "#add-bike");
    toggle.addEventListener("click", function (event) {
      event.preventDefault();
      setOpen(panel.hidden);
    });
    window.addEventListener("hashchange", function () {
      if (location.hash === "#add-bike") setOpen(true);
    });
  }
})();

(function () {
  // Select bikes and clear their history or delete them together.
  var form = document.getElementById("bulk-form");
  if (!form) return;
  var boxes = Array.prototype.slice.call(document.querySelectorAll(".bike-select"));
  var all = document.getElementById("select-all");
  var count = document.getElementById("bulk-count");
  var buttons = form.querySelectorAll("[data-needs-selection]");

  function selected() {
    return boxes.filter(function (box) { return box.checked; }).length;
  }
  function update() {
    var n = selected();
    count.textContent = n ? n + " selected" : "None selected";
    buttons.forEach(function (button) { button.disabled = !n; });
    all.checked = n > 0 && n === boxes.length;
    all.indeterminate = n > 0 && n < boxes.length;
  }

  boxes.forEach(function (box) { box.addEventListener("change", update); });
  all.addEventListener("change", function () {
    boxes.forEach(function (box) { box.checked = all.checked; });
    update();
  });
  form.addEventListener("submit", function (event) {
    var n = selected();
    var noun = n === 1 ? "bike" : "bikes";
    var action = event.submitter && event.submitter.value;
    var message = action === "delete"
      ? "Delete " + n + " " + noun + " and all of their rides, hours and service history? This cannot be undone."
      : "Clear all maintenance history for " + n + " " + noun + "? Their rides and hours are kept.";
    if (!n || !window.confirm(message)) event.preventDefault();
  });
  update();
})();
