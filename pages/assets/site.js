(function () {
  "use strict";

  var copyButtons = document.querySelectorAll("[data-copy]");

  function legacyCopy(text) {
    var input = document.createElement("textarea");
    input.value = text;
    input.setAttribute("readonly", "");
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.appendChild(input);
    input.select();
    var copied = document.execCommand("copy");
    input.remove();
    return copied ? Promise.resolve() : Promise.reject(new Error("copy failed"));
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return legacyCopy(text);
  }

  copyButtons.forEach(function (button) {
    var idleLabel = button.getAttribute("data-label-idle") || "Copy";
    var successLabel = button.getAttribute("data-label-success") || "Copied";
    var errorLabel = button.getAttribute("data-label-error") || "Select command";
    var label = button.querySelector("[data-copy-label]");
    var timer;

    button.addEventListener("click", function () {
      window.clearTimeout(timer);
      copyText(button.getAttribute("data-copy") || "").then(function () {
        button.setAttribute("data-state", "success");
        label.textContent = successLabel;
      }).catch(function () {
        button.setAttribute("data-state", "error");
        label.textContent = errorLabel;
      }).finally(function () {
        timer = window.setTimeout(function () {
          button.removeAttribute("data-state");
          label.textContent = idleLabel;
        }, 1800);
      });
    });
  });
}());
