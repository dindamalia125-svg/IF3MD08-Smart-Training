(function () {
  var form = document.getElementById('form-ekspor');
  if (!form) return;
  var harian = document.getElementById('periode_harian'), bulanan = document.getElementById('periode_bulanan');
  function sync() {
    var isBulan = form.querySelector('input[name="jenis"]:checked').value === 'bulanan';
    harian.hidden = isBulan; bulanan.hidden = !isBulan;
  }
  form.querySelectorAll('input[name="jenis"]').forEach(function (r) { r.addEventListener('change', sync); });
  sync();
})();
