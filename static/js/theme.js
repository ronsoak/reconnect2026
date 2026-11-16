// Auto / Light / Dark theme control in the footer.
// Auto (no saved value) follows the device; Light or Dark is saved in
// localStorage and applied before paint by the inline script in base.html.
(function () {
  var KEY = "color-scheme";
  var root = document.documentElement;
  var media = window.matchMedia("(prefers-color-scheme: dark)");
  var schemeMeta = document.querySelector('meta[name="color-scheme"]');
  var themeColorMeta = document.querySelector('meta[name="theme-color"]');
  var control = document.querySelector("[data-theme-switch]");
  var autoState = document.querySelector("[data-theme-auto-state]");
  var current = "auto";

  function saved() {
    try {
      var value = window.localStorage.getItem(KEY);
      return value === "light" || value === "dark" ? value : "auto";
    } catch (error) {
      return "auto";
    }
  }

  function save(choice) {
    try {
      if (choice === "auto") window.localStorage.removeItem(KEY);
      else window.localStorage.setItem(KEY, choice);
    } catch (error) {
      // Private browsing can block storage; the choice still applies to this page.
    }
  }

  function render(choice) {
    if (control) {
      control.querySelectorAll("input").forEach(function (input) {
        input.checked = input.value === choice;
      });
    }
    if (autoState) autoState.textContent = " (" + (media.matches ? "dark" : "light") + ")";
    // Browser chrome follows the page colour the theme actually produced.
    if (themeColorMeta && document.body) {
      themeColorMeta.content = window.getComputedStyle(document.body).backgroundColor;
    }
  }

  function apply(choice) {
    current = choice;
    if (choice === "auto") delete root.dataset.theme;
    else root.dataset.theme = choice;
    if (schemeMeta) schemeMeta.content = choice === "auto" ? "light dark" : choice;
    render(choice);
  }

  if (control) {
    control.hidden = false;
    control.addEventListener("change", function (event) {
      var choice = event.target.value;
      save(choice);
      apply(choice);
    });
  }

  media.addEventListener("change", function () {
    render(current);
  });

  // Keep other open tabs in step with a choice made here.
  window.addEventListener("storage", function (event) {
    if (event.key === KEY || event.key === null) apply(saved());
  });

  apply(saved());
})();
