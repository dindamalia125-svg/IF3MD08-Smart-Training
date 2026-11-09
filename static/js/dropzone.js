// Drag & drop dokumen recruitment: validasi ringan di browser, lalu kirim otomatis.
// Validasi sebenarnya (ekstensi, ukuran, isi file) tetap dilakukan server.
(function () {
  var zone = document.getElementById("dz");
  if (!zone) return;
  var form = document.getElementById("dz-form");
  var input = document.getElementById("dz-input");
  var status = document.getElementById("dz-status");
  var maxBytes = (parseInt(zone.dataset.maxMb, 10) || 10) * 1024 * 1024;
  var busy = false;

  function say(text, isError) {
    status.textContent = text;
    status.className = "dz-status" + (isError ? " err" : "");
  }

  function submitFile(file) {
    if (busy) return;
    var ext = (file.name.split(".").pop() || "").toLowerCase();
    if (ext !== "docx" && ext !== "pdf") { say("⚠ Hanya file Word (.docx) atau PDF (.pdf) yang diterima.", true); return; }
    if (file.size === 0) { say("⚠ File kosong.", true); return; }
    if (file.size > maxBytes) { say("⚠ Ukuran file maksimal " + (maxBytes / 1048576) + " MB.", true); return; }
    busy = true;
    zone.classList.add("busy");
    say("AI membaca " + file.name + " secara otomatis … memisahkan karyawan per section", false);
    form.submit();
  }

  function pick(files) {
    if (!files || !files.length) return;
    if (files.length > 1) { say("⚠ Unggah satu file saja per proses.", true); return; }
    try {
      var dt = new DataTransfer();
      dt.items.add(files[0]);
      input.files = dt.files;
    } catch (e) { /* browser lama: jatuh ke pemilihan file manual */ }
    if (input.files && input.files.length) submitFile(input.files[0]);
  }

  input.addEventListener("change", function () { pick(input.files); });
  ["dragenter", "dragover"].forEach(function (name) {
    zone.addEventListener(name, function (e) { e.preventDefault(); zone.classList.add("over"); });
  });
  ["dragleave", "drop"].forEach(function (name) {
    zone.addEventListener(name, function (e) { e.preventDefault(); zone.classList.remove("over"); });
  });
  zone.addEventListener("drop", function (e) { pick(e.dataTransfer && e.dataTransfer.files); });
  // File yang dilepas di luar area tidak boleh membuka file di tab browser.
  ["dragover", "drop"].forEach(function (name) {
    window.addEventListener(name, function (e) { if (!zone.contains(e.target)) e.preventDefault(); });
  });
})();
