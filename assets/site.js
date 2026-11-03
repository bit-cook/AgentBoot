(function () {
  "use strict";

  var root = document.documentElement;
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- 复制按钮（原有逻辑保留） ---------- */
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

  /* ---------- 粘性导航：滚动状态 ---------- */
  var nav = document.querySelector(".site-nav");
  if (nav) {
    var syncNav = function () {
      nav.classList.toggle("is-scrolled", window.scrollY > 8);
    };
    syncNav();
    window.addEventListener("scroll", syncNav, { passive: true });
  }

  /* ---------- 章节高亮（scrollspy） ---------- */
  var navLinks = Array.prototype.slice.call(document.querySelectorAll(".nav-link[href^='#']"));
  var spyTargets = navLinks
    .map(function (link) {
      var id = link.getAttribute("href").slice(1);
      var section = id ? document.getElementById(id) : null;
      return section ? { link: link, section: section } : null;
    })
    .filter(Boolean);

  if (spyTargets.length > 0) {
    var setActive = function (link) {
      navLinks.forEach(function (item) {
        item.classList.toggle("is-active", item === link);
      });
    };
    var spyObserver = new IntersectionObserver(
      function (entries) {
        var visible = entries
          .filter(function (entry) { return entry.isIntersecting; })
          .sort(function (a, b) { return b.intersectionRatio - a.intersectionRatio; })[0];
        if (!visible) { return; }
        var match = spyTargets.filter(function (item) { return item.section === visible.target; })[0];
        if (match) { setActive(match.link); }
      },
      { rootMargin: "-45% 0px -50% 0px", threshold: [0, 0.25, 0.5, 1] }
    );
    spyTargets.forEach(function (item) { spyObserver.observe(item.section); });
  }

  /* ---------- 滚动显现 ---------- */
  var revealSelectors = [
    ".section-heading",
    ".command-card",
    ".steps .step",
    ".feature-spotlight",
    ".feature-row",
    ".agent-panel",
    ".detail-block",
    ".docs-link",
    ".faq-item",
    ".final-call",
    ".stat"
  ];

  if ("IntersectionObserver" in window && !reduceMotion) {
    root.classList.add("js");
    var revealTargets = Array.prototype.slice.call(
      document.querySelectorAll(revealSelectors.join(","))
    );
    // 同一容器内的相邻元素依次显现，形成层次感
    var seenGroups = {};
    revealTargets.forEach(function (element) {
      var group = element.parentElement;
      var index = seenGroups[group] || 0;
      seenGroups[group] = index + 1;
      element.classList.add("reveal");
      element.style.setProperty("--reveal-delay", Math.min(index * 70, 420) + "ms");
    });
    var revealObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            revealObserver.unobserve(entry.target);
          }
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
    );
    revealTargets.forEach(function (element) { revealObserver.observe(element); });
  }

  /* ---------- 数据带数字滚动 ---------- */
  var counters = document.querySelectorAll("[data-count-to]");
  if (counters.length > 0 && !reduceMotion) {
    var runCounter = function (element) {
      var target = parseInt(element.getAttribute("data-count-to"), 10);
      if (isNaN(target)) { return; }
      var startedAt = null;
      var duration = 900;
      var tick = function (now) {
        if (startedAt === null) { startedAt = now; }
        var progress = Math.min((now - startedAt) / duration, 1);
        var eased = 1 - Math.pow(1 - progress, 3);
        element.textContent = String(Math.round(target * eased));
        if (progress < 1) {
          window.requestAnimationFrame(tick);
        }
      };
      window.requestAnimationFrame(tick);
    };
    if ("IntersectionObserver" in window) {
      var counterObserver = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              runCounter(entry.target);
              counterObserver.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.4 }
      );
      counters.forEach(function (element) { counterObserver.observe(element); });
    } else {
      counters.forEach(runCounter);
    }
  }

  /* ---------- FAQ：单开模式（打开一个自动收起其他） ---------- */
  var faqItems = document.querySelectorAll(".faq-item");
  faqItems.forEach(function (item) {
    item.addEventListener("toggle", function () {
      if (!item.open) { return; }
      faqItems.forEach(function (other) {
        if (other !== item) { other.open = false; }
      });
    });
  });
}());
