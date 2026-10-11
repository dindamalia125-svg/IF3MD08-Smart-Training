(function () {
  // Tombol Cetak aktif hanya bila ada proses yang direkomendasikan Qualified DAN disetujui Trainer.
  var form = document.getElementById('form-evaluasi'), btn = document.getElementById('btn-cetak');
  if (!form || !btn) return;
  function refresh() {
    var ok = false;
    form.querySelectorAll('tbody tr').forEach(function (tr) {
      var rek = tr.querySelector('[data-rek]');
      var setuju = tr.querySelector('input[value="setuju"]');
      if (rek && rek.dataset.rek === '1' && setuju && setuju.checked) ok = true;
    });
    btn.disabled = !ok;
  }
  form.addEventListener('change', refresh);
  refresh();
})();
