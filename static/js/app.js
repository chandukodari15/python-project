/**
 * WattWise Application Core JavaScript
 * Modal management, live search, dynamic forms, and notification handling
 */

// Modal handlers
function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.add('open');
    document.body.style.overflow = 'hidden';
  }
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.remove('open');
    document.body.style.overflow = '';
  }
}

// Close modal on outside click
document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
  backdrop.addEventListener('click', e => {
    if (e.target === backdrop) {
      backdrop.classList.remove('open');
      document.body.style.overflow = '';
    }
  });
});

// Close modal on Escape key
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-backdrop.open').forEach(modal => {
      modal.classList.remove('open');
    });
    document.body.style.overflow = '';
  }
});

// Real-time table search
const searchInput = document.getElementById('tableSearch');
if (searchInput) {
  searchInput.addEventListener('input', () => {
    const query = searchInput.value.toLowerCase().trim();
    const rows = document.querySelectorAll('#dataTable tbody tr');
    rows.forEach(row => {
      if (row.classList.contains('empty-row')) return;
      const text = row.innerText.toLowerCase();
      row.style.display = text.includes(query) ? '' : 'none';
    });
  });
}

// Auto-dismiss toast flash alerts
setTimeout(() => {
  document.querySelectorAll('.flash-message').forEach(el => {
    el.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
    el.style.opacity = '0';
    el.style.transform = 'translateY(-6px)';
    setTimeout(() => el.remove(), 400);
  });
}, 5000);

// Dynamic meter previous reading preview on Reading Form
const meterSelect = document.getElementById('readingMeterSelect');
const meterHelper = document.getElementById('meterReadingHelper');
if (meterSelect && meterHelper) {
  meterSelect.addEventListener('change', () => {
    const selected = meterSelect.options[meterSelect.selectedIndex];
    const lastVal = selected.getAttribute('data-last-kwh');
    const lastDate = selected.getAttribute('data-last-date');
    if (lastVal && lastVal !== 'None' && lastVal !== '') {
      meterHelper.innerHTML = `Previous recorded cumulative reading: <b>${Number(lastVal).toLocaleString()} kWh</b> on <b>${lastDate}</b>. Your new reading must be ≥ ${Number(lastVal).toLocaleString()} kWh.`;
      meterHelper.style.display = 'block';
    } else {
      meterHelper.innerHTML = `First reading for this meter. This reading will establish the initial baseline.`;
      meterHelper.style.display = 'block';
    }
  });
}
