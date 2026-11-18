/* Back / Forward button helpers shared by every page.
   - Smooth scrolling + scroll-snap fight the browser while it restores your
     scroll position, which looks like the page "jumping" or "glitching".
     We keep them OFF while the page is loading/restoring and switch them on after. */
(function () {
  var root = document.documentElement;
  var t = null;
  function settle() {
    clearTimeout(t);
    root.classList.remove('eh-ready');
    t = setTimeout(function () { root.classList.add('eh-ready'); }, 600);
  }
  settle();
  window.addEventListener('pageshow', function (e) { if (e.persisted) settle(); });
  // Page is being left: stop snapping so a half-finished animation is not frozen into history.
  window.addEventListener('pagehide', function () { root.classList.remove('eh-ready'); });
})();
