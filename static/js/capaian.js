(function () {
  var sel = document.getElementById('id_proses'), info = document.getElementById('info-proses');
  if (!sel || !info) return;
  function update() {
    var o = sel.options[sel.selectedIndex];
    info.textContent = o && o.dataset.target
      ? 'Target harian ' + o.dataset.target + ' pcs · Durasi maks. training ' + o.dataset.durasi + ' hari (dari master proses)'
      : 'Pilih proses untuk melihat target harian dan durasi maksimal (dari master proses)';
  }
  sel.addEventListener('change', update);
})();
