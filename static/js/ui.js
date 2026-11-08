/* STA — perilaku antarmuka sesuai Design Handoff: toast 3 detik, modal konfirmasi slide-up,
   menu sheet mobile, spinner submit. Tidak mengubah logika fitur. */
(function () {
  "use strict";
  var TOAST_MS = 3000;

  /* ---------- Toast ---------- */
  function dismiss(t) {
    if (!t || t.classList.contains("leaving")) return;
    t.classList.add("leaving");
    setTimeout(function () { t.remove(); }, 220);
  }
  function arm(t) {
    var x = t.querySelector(".toast-x");
    if (x) x.addEventListener("click", function () { dismiss(t); });
    // sukses/info hilang setelah 3 detik; galat/peringatan tetap sampai ditutup agar tidak terlewat
    if (t.classList.contains("success") || t.classList.contains("info")) {
      var timer = setTimeout(function () { dismiss(t); }, TOAST_MS);
      t.addEventListener("mouseenter", function () { clearTimeout(timer); });
      t.addEventListener("mouseleave", function () { timer = setTimeout(function () { dismiss(t); }, 1500); });
    }
  }
  function toast(msg, kind) {
    var box = document.getElementById("toasts");
    if (!box) return;
    var t = document.createElement("div");
    t.className = "toast " + (kind || "info");
    t.setAttribute("role", "status");
    var m = document.createElement("span"); m.className = "toast-msg"; m.textContent = msg;
    var b = document.createElement("button"); b.type = "button"; b.className = "toast-x";
    b.setAttribute("aria-label", "Tutup notifikasi"); b.textContent = "×";
    t.appendChild(m); t.appendChild(b); box.appendChild(t); arm(t);
  }
  window.staToast = toast;
  document.querySelectorAll("#toasts .toast").forEach(arm);
  window.addEventListener("offline", function () { toast("Terjadi kesalahan jaringan. Coba lagi nanti.", "error"); });

  /* ---------- Sheet (modal slide dari bawah) ---------- */
  var lastFocus = null;
  function openSheet(bd, focusEl) {
    lastFocus = document.activeElement;
    bd.classList.add("open"); bd.setAttribute("aria-hidden", "false");
    setTimeout(function () { (focusEl || bd.querySelector("button,a")).focus(); }, 50);
  }
  function closeSheet(bd) {
    bd.classList.remove("open"); bd.setAttribute("aria-hidden", "true");
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  document.addEventListener("keydown", function (e) {
    var open = document.querySelector(".modal-bd.open");
    if (!open) return;
    if (e.key === "Escape") { closeSheet(open); return; }
    if (e.key === "Tab") {   // jaga fokus tetap di dalam dialog
      var f = open.querySelectorAll("button,a[href]"); if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });

  /* menu sheet (mobile) */
  var menu = document.getElementById("menu-sheet");
  if (menu) {
    document.querySelectorAll("[data-menu-open]").forEach(function (b) { b.addEventListener("click", function () { openSheet(menu); }); });
    menu.querySelectorAll("[data-menu-close]").forEach(function (b) { b.addEventListener("click", function () { closeSheet(menu); }); });
    menu.addEventListener("click", function (e) { if (e.target === menu) closeSheet(menu); });
  }

  /* ---------- Modal konfirmasi: <form data-confirm="Judul" data-confirm-text="..." data-confirm-ok="..."> ---------- */
  var cm = null;
  function buildConfirm() {
    cm = document.createElement("div");
    cm.className = "modal-bd"; cm.setAttribute("aria-hidden", "true");
    cm.innerHTML = '<div class="sheet" role="alertdialog" aria-modal="true" aria-labelledby="cm-t" aria-describedby="cm-d">' +
      '<h2 id="cm-t"></h2><p id="cm-d"></p><div class="sheet-actions">' +
      '<button type="button" class="btn" data-cm-cancel>Batal</button>' +
      '<button type="button" class="btn primary" data-cm-ok></button></div></div>';
    document.body.appendChild(cm);
    cm.addEventListener("click", function (e) { if (e.target === cm) closeSheet(cm); });
    cm.querySelector("[data-cm-cancel]").addEventListener("click", function () { closeSheet(cm); });
  }
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (!f.matches || !f.matches("form[data-confirm]") || f.dataset.confirmed === "1") return;
    e.preventDefault(); e.stopImmediatePropagation();
    if (!cm) buildConfirm();
    var ok = cm.querySelector("[data-cm-ok]"), submitter = e.submitter;
    cm.querySelector("#cm-t").textContent = f.dataset.confirm;
    cm.querySelector("#cm-d").textContent = f.dataset.confirmText || "";
    ok.textContent = f.dataset.confirmOk || "Ya, lanjutkan";
    ok.className = "btn " + (f.dataset.confirmTone === "danger" ? "danger-solid" : "primary");
    ok.onclick = function () { closeSheet(cm); f.dataset.confirmed = "1"; f.requestSubmit ? f.requestSubmit(submitter) : f.submit(); };
    openSheet(cm, cm.querySelector("[data-cm-cancel]"));
  }, true);

  /* ---------- Spinner pada tombol submit (otomatis reset; tombol tidak di-disable agar data form tetap terkirim) ---------- */
  document.addEventListener("submit", function (e) {
    var f = e.target;
    setTimeout(function () {
      if (e.defaultPrevented) return;
      var b = e.submitter || f.querySelector("button[type=submit].primary,button[type=submit]");
      if (!b || b.classList.contains("link")) return;
      b.classList.add("is-loading"); b.setAttribute("aria-busy", "true");
      setTimeout(function () { b.classList.remove("is-loading"); b.removeAttribute("aria-busy"); }, 8000); // mis. respons berupa unduhan PDF
    }, 0);
  });
  window.addEventListener("pageshow", function () {
    document.querySelectorAll(".is-loading").forEach(function (b) { b.classList.remove("is-loading"); b.removeAttribute("aria-busy"); });
  });
})();
