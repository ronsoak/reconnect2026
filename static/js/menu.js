// Collapses the main navigation into a toggle button on narrow screens.
//
// The breakpoint lives in CSS (.site-menu--collapsible rules in custom.css);
// this script only shows the button and opens/closes the list. Without
// JavaScript the button stays hidden and the links remain visible.
(function () {
  const menu = document.querySelector(".site-menu");
  if (!menu) return;

  const toggle = menu.querySelector(".site-menu__toggle");
  const list = menu.querySelector(".site-menu__list");
  if (!toggle || !list) return;

  menu.classList.add("site-menu--collapsible");
  toggle.hidden = false;

  function setOpen(open, returnFocus) {
    toggle.setAttribute("aria-expanded", String(open));
    menu.classList.toggle("is-open", open);
    if (!open && returnFocus) toggle.focus();
  }

  toggle.addEventListener("click", function () {
    setOpen(toggle.getAttribute("aria-expanded") !== "true", false);
  });

  // Escape closes the menu and returns focus to the toggle.
  menu.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && menu.classList.contains("is-open")) {
      setOpen(false, true);
    }
  });

  // Clicking or tabbing outside the menu closes it.
  document.addEventListener("click", function (event) {
    if (!menu.contains(event.target)) setOpen(false, false);
  });
  menu.addEventListener("focusout", function (event) {
    if (event.relatedTarget && !menu.contains(event.relatedTarget)) setOpen(false, false);
  });

  // Growing past the breakpoint resets the menu so it never reopens unexpectedly.
  const wide = window.matchMedia("(min-width: 769px)");
  wide.addEventListener("change", function () {
    setOpen(false, false);
  });
})();
