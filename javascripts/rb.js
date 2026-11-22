/* rbrooksdk.github.io — course filters and the Ctrl K palette.
   Works with Material's instant navigation (document$) and without it. */
(function () {
  "use strict";

  /* ------------------------------------------------------------ filters */
  function initFilters() {
    document.querySelectorAll(".rb-chips[data-rb-target]").forEach(function (group) {
      var target = document.getElementById(group.dataset.rbTarget);
      if (!target || group.dataset.rbReady) return;
      group.dataset.rbReady = "1";
      var chips = group.querySelectorAll(".rb-chip");
      function apply(key) {
        target.dataset.filter = key;
        chips.forEach(function (c) { c.setAttribute("aria-pressed", String(c.dataset.filter === key)); });
        // hide empty year sections on the Courses page
        target.querySelectorAll(".rb-year").forEach(function (sec) {
          var visible = Array.prototype.some.call(sec.querySelectorAll(".rb-card"), function (card) {
            return card.offsetParent !== null;
          });
          sec.hidden = !visible;
        });
        // empty-state line on the home grid
        var empty = target.querySelector(".rb-grid__empty");
        if (empty) {
          var any = Array.prototype.some.call(target.querySelectorAll(".rb-card"), function (card) {
            return getComputedStyle(card).display !== "none";
          });
          empty.style.display = any ? "none" : "block";
        }
      }
      chips.forEach(function (c) { c.addEventListener("click", function () { apply(c.dataset.filter); }); });
      apply(target.dataset.filter || chips[0].dataset.filter);
    });
  }

  /* ------------------------------------------------------------ palette */
  var items = null, sel = 0, shown = [], lastFocus = null;

  function el(id) { return document.getElementById(id); }

  function loadItems() {
    var node = el("rb-palette-data");
    try { items = node ? JSON.parse(node.textContent) : []; } catch (e) { items = []; }
  }

  function score(item, q) {
    if (!q) return item.deep ? 0 : 1;
    var hay = (item.kind + " " + item.label + " " + item.hint).toLowerCase();
    var words = q.toLowerCase().split(/\s+/).filter(Boolean);
    var s = 0;
    for (var i = 0; i < words.length; i++) {
      var at = hay.indexOf(words[i]);
      if (at < 0) return 0;
      s += at === 0 ? 3 : (hay.charAt(at - 1) === " " ? 2 : 1);
    }
    return s;
  }

  function render() {
    var list = el("rb-palette-list"), q = el("rb-palette-q").value.trim();
    shown = items
      .map(function (it, i) { return { it: it, s: score(it, q), i: i }; })
      .filter(function (x) { return x.s > 0; })
      .sort(function (a, b) { return b.s - a.s || a.i - b.i; })
      .slice(0, 40)
      .map(function (x) { return x.it; });
    if (sel >= shown.length) sel = 0;
    list.innerHTML = "";
    if (!shown.length) {
      var li = document.createElement("li");
      li.className = "rb-palette__none";
      li.textContent = "Nothing matches “" + q + "”.";
      list.appendChild(li);
      return;
    }
    shown.forEach(function (it, i) {
      var li = document.createElement("li");
      li.setAttribute("role", "option");
      li.id = "rb-opt-" + i;
      li.setAttribute("aria-selected", String(i === sel));
      var a = document.createElement("a");
      a.href = it.href;
      a.className = "rb-palette__item";
      a.tabIndex = -1;
      a.innerHTML = '<span class="rb-palette__kind"></span><span class="rb-palette__label"></span><span class="rb-palette__hint"></span>';
      a.children[0].textContent = it.kind;
      a.children[1].textContent = it.label;
      a.children[2].textContent = it.hint;
      a.addEventListener("mousemove", function () { if (sel !== i) { sel = i; mark(); } });
      li.appendChild(a);
      list.appendChild(li);
    });
    mark();
  }

  function mark() {
    var list = el("rb-palette-list");
    Array.prototype.forEach.call(list.children, function (li, i) {
      li.setAttribute("aria-selected", String(i === sel));
    });
    el("rb-palette-q").setAttribute("aria-activedescendant", shown.length ? "rb-opt-" + sel : "");
    var cur = el("rb-opt-" + sel);
    if (cur) cur.scrollIntoView({ block: "nearest" });
  }

  function open() {
    var p = el("rb-palette");
    if (!p) return;
    if (!items) loadItems();
    lastFocus = document.activeElement;
    p.hidden = false;
    document.documentElement.classList.add("rb-noscroll");
    var q = el("rb-palette-q");
    q.value = "";
    sel = 0;
    render();
    q.focus();
  }

  function close() {
    var p = el("rb-palette");
    if (!p || p.hidden) return;
    p.hidden = true;
    document.documentElement.classList.remove("rb-noscroll");
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  function go(it) {
    close();
    if (it.href.charAt(0) === "/" || it.href.indexOf(location.origin) === 0 || it.href.indexOf("mailto:") === 0) {
      location.href = it.href;
    } else {
      window.open(it.href, "_blank", "noopener");
    }
  }

  function initPalette() {
    items = null;
    var p = el("rb-palette");
    if (!p || p.dataset.rbReady) return;
    p.dataset.rbReady = "1";
    p.querySelectorAll("[data-rb-close]").forEach(function (b) { b.addEventListener("click", close); });
    var q = el("rb-palette-q");
    q.addEventListener("input", function () { sel = 0; render(); });
    q.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(sel + 1, shown.length - 1); mark(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(sel - 1, 0); mark(); }
      else if (e.key === "Enter" && shown[sel]) { e.preventDefault(); go(shown[sel]); }
    });
    el("rb-palette-list").addEventListener("click", function (e) {
      var a = e.target.closest("a.rb-palette__item");
      if (!a) return;
      e.preventDefault();
      var i = Array.prototype.indexOf.call(this.children, a.parentNode);
      if (shown[i]) go(shown[i]);
    });

    // header button, so the palette is discoverable without the shortcut
    var inner = document.querySelector(".md-header__inner");
    if (inner && !inner.querySelector(".rb-explore")) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "rb-explore";
      btn.setAttribute("aria-label", "Explore (Ctrl K)");
      btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg><span class="rb-explore__text">Explore</span><kbd>Ctrl K</kbd>';
      btn.addEventListener("click", open);
      var search = inner.querySelector(".md-search");
      inner.insertBefore(btn, search || null);
    }
  }

  // one global shortcut listener for the whole session
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      var p = el("rb-palette");
      if (p && p.hidden) open(); else close();
    } else if (e.key === "Escape") {
      close();
    }
  });

  function init() { initFilters(); initPalette(); }

  if (typeof window.document$ !== "undefined" && window.document$.subscribe) {
    window.document$.subscribe(init);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
