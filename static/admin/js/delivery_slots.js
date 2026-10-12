// ==========================================
// Delivery Slots Management (Admin)
// ==========================================
let cachedDeliverySlots = [];
let currentSlotStatusFilter = 'all';
let slotSearchTimeout = null;

async function loadDeliverySlots() {
  const tbody = document.getElementById('delivery-slots-table-body');
  if (!tbody) return;

  try {
    const queryParams = new URLSearchParams();
    if (currentSlotStatusFilter !== 'all') {
      queryParams.append('status', currentSlotStatusFilter);
    }
    const searchInput = document.getElementById('slot-search-input');
    if (searchInput && searchInput.value.trim()) {
      queryParams.append('search', searchInput.value.trim());
    }

    const res = await fetch(`/api/admin/delivery-slots/?${queryParams.toString()}`);
    if (!res.ok) throw new Error('Failed to fetch delivery slots');
    const data = await res.json();
    const list = data.slots || [];
    cachedDeliverySlots = list;

    if (list.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center py-8 text-slate-400">No delivery slots found matching current criteria.</td></tr>`;
      return;
    }

    tbody.innerHTML = list.map(s => {
      const startFormatted = formatTime12h(s.start_time);
      const endFormatted = formatTime12h(s.end_time);
      const duration = computeDurationHours(s.start_time, s.end_time);

      return `
        <tr class="hover:bg-slate-50 transition">
          <td class="py-3 px-4 font-mono font-bold text-slate-500 text-[11px]">#${s.id}</td>
          <td class="py-3 px-4 font-bold text-slate-900">${escapeHtml(s.name)}</td>
          <td class="py-3 px-4 font-semibold text-slate-800">
            <span class="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-slate-100 text-[11px]">
              <i data-lucide="clock" class="w-3 h-3 text-slate-500"></i>
              <span>${startFormatted} – ${endFormatted}</span>
            </span>
          </td>
          <td class="py-3 px-4 text-slate-500 text-[11px]">${duration}</td>
          <td class="py-3 px-4">
            <span class="font-bold text-slate-900">${s.orders_count}</span>
            <span class="text-slate-400 text-[11px]">orders</span>
          </td>
          <td class="py-3 px-4">
            <span class="font-bold text-slate-900">${s.subscriptions_count}</span>
            <span class="text-slate-400 text-[11px]">subs</span>
          </td>
          <td class="py-3 px-4">
            <button onclick="toggleSlotActive(${s.id})" class="px-2.5 py-1 rounded-full text-[11px] font-semibold transition ${s.is_active ? 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}">
              ${s.is_active ? '● Active in App' : '○ Deactivated'}
            </button>
          </td>
          <td class="py-3 px-4 text-right">
            <div class="flex items-center justify-end space-x-1.5">
              <button onclick="openEditSlotModal(${s.id})" class="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:text-brand hover:border-brand transition" title="Edit Slot Name & Time Window">
                <i data-lucide="edit" class="w-3.5 h-3.5"></i>
              </button>
              <button onclick="toggleSlotActive(${s.id})" class="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:text-amber-700 hover:border-amber-300 transition" title="${s.is_active ? 'Deactivate Slot Safely' : 'Activate Slot'}">
                <i data-lucide="power" class="w-3.5 h-3.5"></i>
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join('');

    if (window.lucide && typeof lucide.createIcons === 'function') {
      lucide.createIcons();
    }
  } catch (err) {
    console.error('Error loading delivery slots:', err);
    tbody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-red-500">Error loading delivery slots.</td></tr>`;
  }
}

function filterSlotStatus(status) {
  currentSlotStatusFilter = status;
  ['all', 'active', 'inactive'].forEach(s => {
    const btn = document.getElementById(`slot-filter-${s}`);
    if (btn) {
      btn.className = s === status
        ? 'px-2.5 py-1 rounded-md font-semibold bg-white text-slate-900 shadow-xs transition'
        : 'px-2.5 py-1 rounded-md font-medium text-slate-600 hover:text-slate-900 transition';
    }
  });
  loadDeliverySlots();
}

function debounceSlotSearch() {
  clearTimeout(slotSearchTimeout);
  slotSearchTimeout = setTimeout(loadDeliverySlots, 300);
}

// Helpers
function formatTime12h(timeStr) {
  if (!timeStr) return '';
  const parts = timeStr.split(':');
  let h = parseInt(parts[0], 10);
  const m = parts[1] || '00';
  const ampm = h >= 12 ? 'PM' : 'AM';
  h = h % 12;
  if (h === 0) h = 12;
  return `${h}:${m} ${ampm}`;
}

function computeDurationHours(startStr, endStr) {
  if (!startStr || !endStr) return '';
  const sParts = startStr.split(':').map(Number);
  const eParts = endStr.split(':').map(Number);
  const sMin = sParts[0] * 60 + sParts[1];
  const eMin = eParts[0] * 60 + eParts[1];
  const diffMin = eMin - sMin;
  if (diffMin <= 0) return '—';
  const hours = Math.floor(diffMin / 60);
  const mins = diffMin % 60;
  if (mins === 0) return `${hours} hr${hours > 1 ? 's' : ''}`;
  return `${hours}h ${mins}m`;
}

// Convert 24-hour time ("HH:MM:SS" or "HH:MM") to 12-hour object { hour: 1-12, minute: "00", ampm: "AM"/"PM" }
function parse24hTo12h(timeStr) {
  if (!timeStr) {
    return { hour: 6, minute: '00', ampm: 'AM' };
  }
  const parts = timeStr.split(':');
  let h = parseInt(parts[0], 10);
  const m = parts[1] ? parts[1].slice(0, 2) : '00';
  if (isNaN(h)) h = 6;
  const ampm = h >= 12 ? 'PM' : 'AM';
  let h12 = h % 12;
  if (h12 === 0) h12 = 12;
  return { hour: h12, minute: m, ampm };
}

// Convert 12-hour parts (hour: 1-12, minute: "00"-"59", ampm: "AM"/"PM") to backend 24-hour "HH:MM:SS"
function convert12hTo24h(hour, minute, ampm) {
  let h = parseInt(hour, 10);
  const m = String(minute).padStart(2, '0');
  const period = (ampm || 'AM').toUpperCase();

  if (period === 'PM' && h < 12) {
    h += 12;
  } else if (period === 'AM' && h === 12) {
    h = 0;
  }

  const hStr = String(h).padStart(2, '0');
  return `${hStr}:${m}:00`;
}

// Update live formatted preview text in modal
function updateSlotTimePreview() {
  const sHour = document.getElementById('slot-start-hour')?.value || '6';
  const sMin = document.getElementById('slot-start-minute')?.value || '00';
  const sAmpm = document.getElementById('slot-start-ampm')?.value || 'AM';

  const eHour = document.getElementById('slot-end-hour')?.value || '8';
  const eMin = document.getElementById('slot-end-minute')?.value || '00';
  const eAmpm = document.getElementById('slot-end-ampm')?.value || 'AM';

  const sFormatted = `${String(sHour).padStart(2, '0')}:${sMin} ${sAmpm}`;
  const eFormatted = `${String(eHour).padStart(2, '0')}:${eMin} ${eAmpm}`;

  const sPreview = document.getElementById('slot-start-preview');
  const ePreview = document.getElementById('slot-end-preview');
  const summary = document.getElementById('slot-window-summary');

  if (sPreview) sPreview.innerText = sFormatted;
  if (ePreview) ePreview.innerText = eFormatted;
  if (summary) summary.innerText = `${sFormatted} – ${eFormatted}`;
}

// Modal Handlers
function openCreateSlotModal() {
  const modal = document.getElementById('slot-modal');
  const errBox = document.getElementById('slot-modal-error');
  const title = document.getElementById('slot-modal-title');
  const form = document.getElementById('slot-form');
  if (!modal) return;

  if (errBox) errBox.classList.add('hidden');
  if (title) title.innerText = 'Add Delivery Slot';
  if (form) form.reset();

  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.value = val;
  };

  setVal('slot-id', '');
  setVal('slot-name', '');
  setVal('slot-start-time', '06:00:00');
  setVal('slot-end-time', '08:00:00');

  const activeCheck = document.getElementById('slot-is-active');
  if (activeCheck) activeCheck.checked = true;

  // Defaults: 06:00 AM to 08:00 AM
  setVal('slot-start-hour', '6');
  setVal('slot-start-minute', '00');
  setVal('slot-start-ampm', 'AM');

  setVal('slot-end-hour', '8');
  setVal('slot-end-minute', '00');
  setVal('slot-end-ampm', 'AM');

  updateSlotTimePreview();

  modal.classList.remove('hidden');
  if (window.lucide && typeof lucide.createIcons === 'function') {
    lucide.createIcons();
  }
}

function openEditSlotModal(slotId) {
  const modal = document.getElementById('slot-modal');
  const errBox = document.getElementById('slot-modal-error');
  const title = document.getElementById('slot-modal-title');
  if (!modal) return;

  const slot = cachedDeliverySlots.find(s => String(s.id) === String(slotId));
  if (!slot) {
    console.warn(`Delivery slot #${slotId} not found in cachedDeliverySlots.`);
    return;
  }

  if (errBox) errBox.classList.add('hidden');
  if (title) title.innerText = `Edit Slot #${slot.id}`;

  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.value = val;
  };

  setVal('slot-id', slot.id);
  setVal('slot-name', slot.name || '');
  setVal('slot-start-time', slot.start_time || '');
  setVal('slot-end-time', slot.end_time || '');

  const activeCheckbox = document.getElementById('slot-is-active');
  if (activeCheckbox) activeCheckbox.checked = Boolean(slot.is_active);

  // Convert saved 24h backend times to 12h picker controls
  const start12 = parse24hTo12h(slot.start_time);
  const end12 = parse24hTo12h(slot.end_time);

  setVal('slot-start-hour', String(start12.hour));
  setVal('slot-start-minute', String(start12.minute).padStart(2, '0'));
  setVal('slot-start-ampm', start12.ampm);

  setVal('slot-end-hour', String(end12.hour));
  setVal('slot-end-minute', String(end12.minute).padStart(2, '0'));
  setVal('slot-end-ampm', end12.ampm);

  updateSlotTimePreview();

  modal.classList.remove('hidden');
  if (window.lucide && typeof lucide.createIcons === 'function') {
    lucide.createIcons();
  }
}

function closeSlotModal() {
  const modal = document.getElementById('slot-modal');
  if (modal) modal.classList.add('hidden');
}

async function handleSlotSubmit(e) {
  e.preventDefault();
  const slotId = document.getElementById('slot-id').value.trim();
  const name = document.getElementById('slot-name').value.trim();
  const isActive = document.getElementById('slot-is-active').checked;

  const sHour = document.getElementById('slot-start-hour')?.value || '6';
  const sMin = document.getElementById('slot-start-minute')?.value || '00';
  const sAmpm = document.getElementById('slot-start-ampm')?.value || 'AM';

  const eHour = document.getElementById('slot-end-hour')?.value || '8';
  const eMin = document.getElementById('slot-end-minute')?.value || '00';
  const eAmpm = document.getElementById('slot-end-ampm')?.value || 'AM';

  const errBox = document.getElementById('slot-modal-error');
  const errText = document.getElementById('slot-modal-error-text');
  const btn = document.getElementById('slot-submit-btn');

  if (!name) {
    if (errBox) errBox.classList.remove('hidden');
    if (errText) errText.innerText = 'Please enter a slot name.';
    return;
  }

  // Convert 12h selection to standard 24h backend format
  const startTime24 = convert12hTo24h(sHour, sMin, sAmpm);
  const endTime24 = convert12hTo24h(eHour, eMin, eAmpm);

  // Validate start time is strictly earlier than end time
  const sMinutes = (parseInt(startTime24.split(':')[0], 10) * 60) + parseInt(startTime24.split(':')[1], 10);
  const eMinutes = (parseInt(endTime24.split(':')[0], 10) * 60) + parseInt(endTime24.split(':')[1], 10);

  if (sMinutes >= eMinutes) {
    if (errBox) errBox.classList.remove('hidden');
    const sFormatted = `${String(sHour).padStart(2, '0')}:${sMin} ${sAmpm}`;
    const eFormatted = `${String(eHour).padStart(2, '0')}:${eMin} ${eAmpm}`;
    if (errText) errText.innerText = `Start time (${sFormatted}) must be earlier than end time (${eFormatted}).`;
    return;
  }

  try {
    if (btn) btn.disabled = true;
    const url = slotId ? `/api/admin/delivery-slots/${slotId}/` : '/api/admin/delivery-slots/';
    const method = slotId ? 'PUT' : 'POST';

    const res = await fetch(url, {
      method: method,
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        name: name,
        start_time: startTime24,
        end_time: endTime24,
        is_active: isActive
      })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || data.msg || 'Failed to save delivery slot.');
    }

    closeSlotModal();
    if (typeof showToast === 'function') {
      showToast(data.msg || 'Delivery slot saved successfully.');
    }
    loadDeliverySlots();
  } catch (err) {
    if (errBox) errBox.classList.remove('hidden');
    if (errText) errText.innerText = err.message;
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function toggleSlotActive(slotId) {
  try {
    const res = await fetch(`/api/admin/delivery-slots/${slotId}/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'toggle_active' })
    });
    const data = await res.json();
    if (!res.ok) {
      if (typeof showToast === 'function') {
        showToast(data.error || 'Failed to toggle slot status.', 'error');
      }
      return;
    }
    if (typeof showToast === 'function') {
      showToast(data.msg || 'Slot status updated.');
    }
    loadDeliverySlots();
  } catch (err) {
    console.error('Error toggling slot status:', err);
    if (typeof showToast === 'function') {
      showToast('Network error while updating slot.', 'error');
    }
  }
}
