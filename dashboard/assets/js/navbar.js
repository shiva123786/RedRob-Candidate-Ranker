/**
 * navbar.js
 * Single source of truth for the site nav. Every page includes this file
 * and an empty <div id="navbar-root"></div>; this script renders the bar
 * and marks the current page active, so the navbar only ever needs to be
 * edited in one place.
 */
(function () {
  const LINKS = [
    { href: "index.html", label: "Home", page: "home" },
    { href: "rankings.html", label: "Rankings", page: "rankings" },
    { href: "methodology.html", label: "Methodology", page: "methodology" },
  ];

  function render() {
    const root = document.getElementById("navbar-root");
    if (!root) return;
    const current = root.dataset.page || "home";

    const navHtml = LINKS.map((link) => {
      const activeClass = link.page === current ? " active" : "";
      return `<a class="${activeClass.trim()}" href="${link.href}"><span class="full">${link.label}</span></a>`;
    }).join("");

    root.innerHTML = `
      <div class="navbar">
        <div class="wrap">
          <a class="brand" href="index.html">
            <span class="dot"></span>
            REDROB <span class="sep">/</span> RANKER
          </a>
          <nav>${navHtml}</nav>
        </div>
      </div>
    `;
  }

  document.addEventListener("DOMContentLoaded", render);
})();
