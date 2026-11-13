const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "../../../static/js/filters.js"), "utf8");

function render() {
  const handlers = {};
  const document = {
    activeElement: null,
    addEventListener: (name, callback) => { handlers[name] = callback; },
  };
  const menus = Array.from({ length: 2 }, () => {
    const listeners = {};
    const panel = { hidden: true };
    const checkbox = {};
    const button = {
      expanded: "false",
      focusWhileOpen: false,
      getAttribute() { return this.expanded; },
      setAttribute(_, value) { this.expanded = value; },
      addEventListener: (name, callback) => { listeners[name] = callback; },
      focus() {
        this.focusWhileOpen = !panel.hidden;
        document.activeElement = this;
      },
    };
    return {
      button, panel, checkbox,
      contains: element => element === button || element === checkbox,
      querySelector: selector => selector.endsWith("__button") ? button
        : selector.endsWith("__menu") ? panel : null,
      querySelectorAll: () => [checkbox],
      open: () => listeners.click(),
    };
  });
  document.querySelectorAll = () => menus;
  vm.runInNewContext(source, { document });
  handlers.DOMContentLoaded();
  return {
    document, menus,
    escape() { handlers.keydown({ key: "Escape", preventDefault() {} }); },
    outsideClick(target) { handlers.click({ target }); },
  };
}

test("Escape returns focus to the correct trigger before hiding its checkbox menu", () => {
  for (const index of [0, 1]) {
    const fixture = render();
    const menu = fixture.menus[index];
    menu.open();
    fixture.document.activeElement = menu.checkbox;
    fixture.escape();
    assert.equal(fixture.document.activeElement, menu.button);
    assert.equal(menu.button.focusWhileOpen, true);
    assert.equal(menu.button.expanded, "false");
    assert.equal(menu.panel.hidden, true);
  }
});

test("outside dismissal does not steal focus from an external control", () => {
  for (const action of ["escape", "outsideClick"]) {
    const fixture = render();
    const menu = fixture.menus[0];
    menu.open();
    const outside = {};
    fixture.document.activeElement = outside;
    fixture[action](outside);
    assert.equal(fixture.document.activeElement, outside);
    assert.equal(menu.panel.hidden, true);
  }
});
