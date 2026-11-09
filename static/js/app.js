document.addEventListener("click", function (event) {
  var trigger = event.target.closest("[data-menu-toggle]");
  var closeButton = event.target.closest("[data-menu-close]");
  var panel = document.getElementById("mobile-nav");
  if (!panel) return;

  function setMenuOpen(open) {
    panel.classList.toggle("hidden", !open);
    panel.setAttribute("aria-hidden", open ? "false" : "true");
    document.querySelectorAll("[data-menu-toggle]").forEach(function (button) {
      button.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.body.classList.toggle("store-menu-open", open);
  }

  if (trigger) {
    setMenuOpen(panel.classList.contains("hidden"));
  } else if (closeButton || (panel.contains(event.target) && event.target === panel)) {
    setMenuOpen(false);
  } else if (panel.contains(event.target) && event.target.closest("a")) {
    setMenuOpen(false);
  }
});

document.addEventListener("keydown", function (event) {
  if (event.key !== "Escape") return;
  var panel = document.getElementById("mobile-nav");
  if (!panel || panel.classList.contains("hidden")) return;
  panel.classList.add("hidden");
  panel.setAttribute("aria-hidden", "true");
  document.querySelectorAll("[data-menu-toggle]").forEach(function (button) {
    button.setAttribute("aria-expanded", "false");
  });
  document.body.classList.remove("store-menu-open");
});

(function () {
  var sidebar = document.getElementById("staff-sidebar");
  var backdrop = document.getElementById("staff-sidebar-backdrop");
  var toggles = document.querySelectorAll("[data-sidebar-toggle]");
  if (!sidebar) return;

  function setOpen(open) {
    sidebar.classList.toggle("is-open", open);
    if (backdrop) backdrop.hidden = !open;
    toggles.forEach(function (btn) {
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-sidebar-toggle]")) {
      setOpen(!sidebar.classList.contains("is-open"));
      return;
    }
    if (event.target.closest("[data-sidebar-close]") || event.target === backdrop) {
      setOpen(false);
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") setOpen(false);
  });
})();
