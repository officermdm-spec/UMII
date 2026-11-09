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
