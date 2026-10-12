// Filter dropdowns: open and close the floating menu, a "Select all" toggle,
// and closing a menu when clicking elsewhere or pressing Escape.
document.addEventListener("DOMContentLoaded", function () {
  var menus = document.querySelectorAll(".filter-multiselect");

  function setOpen(menu, open) {
    menu.querySelector(".filter-multiselect__button").setAttribute("aria-expanded", open ? "true" : "false");
    menu.querySelector(".filter-multiselect__menu").hidden = !open;
  }

  menus.forEach(function (menu) {
    var button = menu.querySelector(".filter-multiselect__button");
    var toggle = menu.querySelector("[data-select-all]");
    var boxes = menu.querySelectorAll("input[type=checkbox]:not([data-select-all])");

    button.addEventListener("click", function () {
      var willOpen = button.getAttribute("aria-expanded") !== "true";
      menus.forEach(function (other) { setOpen(other, false); });
      setOpen(menu, willOpen);
    });

    if (!toggle) return;

    // Keeps the toggle ticked only while every option is ticked
    function syncToggle() {
      toggle.checked = boxes.length > 0 && Array.prototype.every.call(boxes, function (box) { return box.checked; });
    }

    toggle.addEventListener("change", function () {
      boxes.forEach(function (box) { box.checked = toggle.checked; });
    });
    boxes.forEach(function (box) { box.addEventListener("change", syncToggle); });
    syncToggle();
  });

  document.addEventListener("click", function (event) {
    menus.forEach(function (menu) {
      if (!menu.contains(event.target)) setOpen(menu, false);
    });
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") menus.forEach(function (menu) { setOpen(menu, false); });
  });
});
