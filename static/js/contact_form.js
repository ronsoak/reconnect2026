// ===== ===== ===== ===== ===== ===== ===== =====
// Contact form helpers (About page)
// ===== ===== ===== ===== ===== ===== ===== =====
// The server does all real validation. This file only improves the experience:
//   - After a valid submit, the button is disabled to prevent double sends.
//   - When the server returns errors, focus moves to the first problem so
//     keyboard and screen reader users land on it straight away.
(function () {
  const form = document.querySelector(".contact-form");
  if (!form) return;

  const firstProblem = form.querySelector('.contact-form__alert, [aria-invalid="true"]');
  if (firstProblem) {
    if (!firstProblem.matches("input, textarea")) firstProblem.setAttribute("tabindex", "-1");
    // Wait for load so the browser's #contact jump doesn't take focus back.
    const focusProblem = function () { firstProblem.focus(); };
    if (document.readyState === "complete") focusProblem();
    else window.addEventListener("load", focusProblem, { once: true });
  }

  form.addEventListener("submit", function () {
    const button = form.querySelector(".contact-form__submit");
    if (!button) return;
    // Wait a tick so the browser includes the form data before disabling.
    window.setTimeout(function () {
      button.disabled = true;
      button.textContent = "Sending…";
    }, 0);
  });
})();
