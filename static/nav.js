/*
 * Shared site navigation bar, injected into every static page via
 * <script src="/nav.js"></script> right after the opening <body> tag.
 * Single source of truth so the link set only needs updating in one
 * place. Relies on the Tailwind Play CDN's MutationObserver to pick up
 * classes on this injected markup - each page must load
 * https://cdn.tailwindcss.com in <head> BEFORE this script runs.
 */
(function () {
  const NAV_LINKS = [
    { href: "/player.html", label: "Play" },
    { href: "/playground.html", label: "Playground" },
    { href: "/leaderboard.html", label: "Leaderboard" },
    { href: "/rules.html", label: "Rules" },
    { href: "/api.html", label: "API" },
    { href: "/docs.html", label: "Quickstart" },
    { href: "/spectator.html", label: "Broadcast" },
  ];

  const currentPath = window.location.pathname.replace(/\/index\.html$/, "/");

  function linkClass(href, mobile) {
    const isActive = currentPath === href;
    const base = mobile ? "block px-3 py-2 rounded-lg transition" : "px-3 py-1.5 rounded-lg transition";
    return isActive
      ? `${base} bg-slate-900 text-indigo-400 font-bold`
      : `${base} text-slate-400 hover:text-white hover:bg-slate-800`;
  }

  const desktopLinks = NAV_LINKS.map(
    (l) => `<a href="${l.href}" class="${linkClass(l.href, false)}">${l.label}</a>`
  ).join("");

  const mobileLinks = NAV_LINKS.map(
    (l) => `<a href="${l.href}" class="${linkClass(l.href, true)}">${l.label}</a>`
  ).join("");

  const navHTML = `
<nav class="sticky top-0 z-50 bg-slate-950/95 backdrop-blur border-b border-slate-800">
  <div class="max-w-6xl mx-auto px-4 h-12 flex items-center justify-between gap-4">
    <a href="/" class="flex items-center gap-2 font-black text-sm text-white uppercase tracking-wider shrink-0">
      <span class="text-indigo-400">&#9876;&#65039;</span> Micro-Diplomacy
    </a>
    <div class="hidden lg:flex items-center gap-1 text-xs">${desktopLinks}</div>
    <button id="mdNavToggle" type="button" class="lg:hidden text-slate-300 hover:text-white p-2 -mr-2" aria-label="Toggle navigation" aria-expanded="false">
      <svg id="mdNavIconOpen" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" /></svg>
      <svg id="mdNavIconClose" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 hidden" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
    </button>
  </div>
  <div id="mdNavMobilePanel" class="lg:hidden hidden absolute left-0 right-0 top-12 bg-slate-950/95 backdrop-blur border-b border-slate-800 flex flex-col gap-1 px-4 pb-3 text-xs z-40">${mobileLinks}</div>
</nav>`;

  document.currentScript.insertAdjacentHTML("afterend", navHTML);

  const toggleBtn = document.getElementById("mdNavToggle");
  const panel = document.getElementById("mdNavMobilePanel");
  const iconOpen = document.getElementById("mdNavIconOpen");
  const iconClose = document.getElementById("mdNavIconClose");

  toggleBtn.addEventListener("click", () => {
    const willOpen = panel.classList.contains("hidden");
    panel.classList.toggle("hidden");
    iconOpen.classList.toggle("hidden");
    iconClose.classList.toggle("hidden");
    toggleBtn.setAttribute("aria-expanded", String(willOpen));
  });
})();
