// =====================================================================
// RECYCLE BIN JAVASCRIPT MODULE
// =====================================================================

let currentRecycleTab = 'all';
let recycleSearchTimeout = null;
let cachedRecycleData = {
  retention_days: 30,
  customers: [],
  delivery_boys: [],
  products: [],
  subscriptions: [],
  counts: { customers: 0, delivery_boys: 0, products: 0, subscriptions: 0, total: 0 }
};

async function loadRecycleBin(searchVal = '') {
  const tbody = document.getElementById('recycle-bin-table-body');
  if (!tbody) return;

  const searchInput = document.getElementById('recycle-search-input');
  const search = searchVal || (searchInput ? searchInput.value.trim() : '');

  try {
    const query = new URLSearchParams({ type: currentRecycleTab });
    if (search) query.append('search', search);

    const res = await fetch(`/api/admin/recycle-bin/?${query.toString()}`);
    const data = await res.json();
    cachedRecycleData = data;

    // Update retention days display
    const retDaysEl = document.getElementById('recycle-retention-days-display');
    if (retDaysEl) retDaysEl.innerText = data.retention_days || 30;

    // Update counts on badges
    updateRecycleBadges(data.counts);

    // Collect records to render based on current tab
    let items = [];
    if (currentRecycleTab === 'all') {
      items = [
        ...(data.customers || []),
        ...(data.delivery_boys || []),
        ...(data.products || []),
        ...(data.subscriptions || [])
      ];
    } else {
      items = data[currentRecycleTab] || [];
    }

    if (items.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center py-12 text-slate-400">
            <div class="flex flex-col items-center justify-center space-y-2">
              <i data-lucide="trash-2" class="w-8 h-8 text-slate-300 stroke-1"></i>
              <p class="font-medium">Recycle Bin is empty</p>
              <p class="text-[11px] text-slate-400">No soft-deleted records matching this category.</p>
            </div>
          </td>
        </tr>
      `;
      if (window.lucide && typeof lucide.createIcons === 'function') {
        lucide.createIcons();
      }
      return;
    }

    tbody.innerHTML = items.map(it => {
      const isEligible = it.is_eligible_for_purge;
      const typeBadgeClass = getTypeBadgeClass(it.type);

      const statusBadge = isEligible
        ? `<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-200">Eligible for Purge</span>`
        : `<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">${it.remaining_retention_days} Days Left</span>`;

      return `
        <tr class="hover:bg-slate-50/80 transition">
          <td class="py-3 px-4">
            <span class="px-2.5 py-1 rounded-md text-[11px] font-bold ${typeBadgeClass}">
              ${it.type_display}
            </span>
          </td>
          <td class="py-3 px-4">
            <p class="font-bold text-slate-900">${escapeHtml(it.title)}</p>
            <p class="text-[11px] text-slate-500 font-mono">${escapeHtml(it.subtitle || '')}</p>
          </td>
          <td class="py-3 px-4 text-slate-600 font-mono text-[11px]">
            ${it.deleted_at}
          </td>
          <td class="py-3 px-4 text-slate-700 font-medium">
            <span class="inline-flex items-center space-x-1">
              <i data-lucide="shield" class="w-3 h-3 text-slate-400"></i>
              <span>${escapeHtml(it.deleted_by || 'Admin')}</span>
            </span>
          </td>
          <td class="py-3 px-4 text-slate-600 font-mono text-[11px]">
            ${it.scheduled_permanent_deletion_date}
          </td>
          <td class="py-3 px-4">
            ${statusBadge}
          </td>
          <td class="py-3 px-4 text-right">
            <div class="flex items-center justify-end space-x-2">
              <button onclick="promptRestoreRecord('${it.type}', ${it.id}, '${escapeHtml(it.title)}')" class="px-2.5 py-1.5 rounded-lg border border-emerald-300 bg-white text-emerald-700 hover:bg-emerald-50 text-[11px] font-bold shadow-xs transition flex items-center space-x-1" title="Restore this record to active status">
                <i data-lucide="rotate-ccw" class="w-3.5 h-3.5"></i>
                <span>Restore</span>
              </button>
              <button onclick="openPermanentDeleteModal('${it.type}', ${it.id}, '${escapeHtml(it.title)}')" class="px-2.5 py-1.5 rounded-lg border border-rose-300 bg-white text-rose-600 hover:bg-rose-50 text-[11px] font-bold shadow-xs transition flex items-center space-x-1" title="Permanently delete record">
                <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
                <span>Delete Permanently</span>
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
    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-6 text-red-500">Error loading Recycle Bin.</td></tr>`;
  }
}

function updateRecycleBadges(counts) {
  if (!counts) return;
  const countAll = document.getElementById('recycle-count-all');
  const countCust = document.getElementById('recycle-count-customers');
  const countBoys = document.getElementById('recycle-count-delivery_boys');
  const countProds = document.getElementById('recycle-count-products');
  const countSubs = document.getElementById('recycle-count-subscriptions');
  const sidebarBadge = document.getElementById('recycle-bin-badge');

  if (countAll) countAll.innerText = counts.total || 0;
  if (countCust) countCust.innerText = counts.customers || 0;
  if (countBoys) countBoys.innerText = counts.delivery_boys || 0;
  if (countProds) countProds.innerText = counts.products || 0;
  if (countSubs) countSubs.innerText = counts.subscriptions || 0;

  if (sidebarBadge) {
    sidebarBadge.innerText = counts.total || 0;
    if (counts.total > 0) {
      sidebarBadge.classList.remove('hidden');
    } else {
      sidebarBadge.classList.add('hidden');
    }
  }
}

function getTypeBadgeClass(type) {
  switch (type) {
    case 'customer':
      return 'bg-blue-50 text-blue-700 border border-blue-200';
    case 'delivery_boy':
      return 'bg-purple-50 text-purple-700 border border-purple-200';
    case 'product':
      return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
    case 'subscription':
      return 'bg-amber-50 text-amber-700 border border-amber-200';
    default:
      return 'bg-slate-100 text-slate-700';
  }
}

function setRecycleTab(tab) {
  currentRecycleTab = tab;
  ['all', 'customers', 'delivery_boys', 'products', 'subscriptions'].forEach(t => {
    const btn = document.getElementById(`recycle-tab-${t}`);
    if (btn) {
      if (t === tab) {
        btn.className = 'px-3 py-1.5 rounded-xl font-bold bg-slate-900 text-white shadow-xs transition flex items-center space-x-1.5';
      } else {
        btn.className = 'px-3 py-1.5 rounded-xl font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition flex items-center space-x-1.5';
      }
    }
  });
  loadRecycleBin();
}

function debounceRecycleSearch() {
  clearTimeout(recycleSearchTimeout);
  recycleSearchTimeout = setTimeout(() => {
    loadRecycleBin();
  }, 300);
}

// ==========================================
// Restore Logic
// ==========================================
async function promptRestoreRecord(type, id, title) {
  if (!confirm(`Restore ${title} back to active platform lists?`)) return;

  try {
    const res = await fetch('/api/admin/recycle-bin/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'restore', type, id })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.msg || 'Record restored successfully.');
      loadRecycleBin();
      refreshEntitySource(type);
    } else {
      showToast(data.error || 'Failed to restore record.', true);
    }
  } catch (err) {
    showToast('Network error restoring record.', true);
  }
}

// ==========================================
// Permanent Delete Modal & Logic
// ==========================================
function openPermanentDeleteModal(type, id, title) {
  document.getElementById('perm-delete-type').value = type;
  document.getElementById('perm-delete-id').value = id;
  document.getElementById('perm-delete-title').innerText = `${title} (${type.toUpperCase()})`;
  document.getElementById('perm-delete-checkbox').checked = false;
  const pwdInput = document.getElementById('perm-delete-password');
  if (pwdInput) pwdInput.value = '';

  document.getElementById('permanent-delete-modal').classList.remove('hidden');
  if (window.lucide && typeof lucide.createIcons === 'function') {
    lucide.createIcons();
  }
}

function closePermanentDeleteModal() {
  document.getElementById('permanent-delete-modal').classList.add('hidden');
}

async function executePermanentDelete() {
  const type = document.getElementById('perm-delete-type').value;
  const id = document.getElementById('perm-delete-id').value;
  const checked = document.getElementById('perm-delete-checkbox').checked;
  const password = (document.getElementById('perm-delete-password')?.value || '').trim();

  if (!checked) {
    alert('Please check the confirmation box acknowledging that permanent deletion cannot be undone.');
    return;
  }

  if (!password) {
    alert('Please enter your administrator password to authorize permanent deletion.');
    document.getElementById('perm-delete-password')?.focus();
    return;
  }

  const confirmBtn = document.getElementById('perm-delete-confirm-btn');
  if (confirmBtn) confirmBtn.disabled = true;

  try {
    const res = await fetch('/api/admin/recycle-bin/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'permanent_delete',
        type,
        id,
        confirmed: true,
        admin_password: password
      })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.msg || 'Record permanently deleted.');
      closePermanentDeleteModal();
      loadRecycleBin();
    } else {
      alert(data.error || 'Failed to permanently delete record.');
      showToast(data.error || 'Permanent deletion blocked.', true);
    }
  } catch (err) {
    showToast('Network error deleting record permanently.', true);
  } finally {
    if (confirmBtn) confirmBtn.disabled = false;
  }
}

// ==========================================
// Soft Delete Modal (from table views)
// ==========================================
function promptSoftDelete(type, id, title) {
  document.getElementById('soft-delete-type').value = type;
  document.getElementById('soft-delete-id').value = id;
  document.getElementById('soft-delete-title').innerText = title;

  let desc = 'This record will be moved to the Recycle Bin and retained for 30 days before permanent cleanup.';
  if (type === 'customer') {
    desc = 'The customer account will be deactivated and cannot log in. Any active subscriptions will be cancelled. Order and payment history is preserved.';
  } else if (type === 'delivery_boy') {
    desc = 'The delivery partner will be marked off-duty and cannot receive order/subscription assignments. Cash ledger history is 100% preserved.';
  } else if (type === 'product') {
    desc = 'The product will disappear from mobile catalogs and new orders. Historical order item details remain intact.';
  } else if (type === 'subscription') {
    desc = 'Future scheduled morning deliveries will stop immediately. Historical completed deliveries and billing records remain intact.';
  }
  document.getElementById('soft-delete-desc').innerText = desc;

  document.getElementById('soft-delete-modal').classList.remove('hidden');
  if (window.lucide && typeof lucide.createIcons === 'function') {
    lucide.createIcons();
  }
}

function closeSoftDeleteModal() {
  document.getElementById('soft-delete-modal').classList.add('hidden');
}

async function executeSoftDelete() {
  const type = document.getElementById('soft-delete-type').value;
  const id = document.getElementById('soft-delete-id').value;

  const btn = document.getElementById('soft-delete-confirm-btn');
  if (btn) btn.disabled = true;

  try {
    let url = '';
    let payload = {};
    if (type === 'customer') {
      url = '/api/admin/customers/';
      payload = { action: 'delete', id };
    } else if (type === 'delivery_boy') {
      url = '/api/admin/delivery-boys/';
      payload = { action: 'delete', id };
    } else if (type === 'product') {
      url = '/api/admin/products/';
      payload = { id };
    } else if (type === 'subscription') {
      url = '/api/admin/subscriptions/';
      payload = { action: 'delete', id };
    }

    const res = await fetch(url, {
      method: (type === 'product') ? 'DELETE' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.msg || 'Moved to Recycle Bin.');
      closeSoftDeleteModal();
      refreshEntitySource(type);
      loadRecycleBin();
      if (typeof loadStatsAndTrends === 'function') {
        loadStatsAndTrends();
      }
    } else {
      showToast(data.error || 'Failed to soft-delete item.', true);
    }
  } catch (err) {
    showToast('Network error soft-deleting item.', true);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function refreshEntitySource(type) {
  if (type === 'customer' && typeof loadCustomers === 'function') loadCustomers();
  if (type === 'delivery_boy' && typeof loadDeliveryBoys === 'function') loadDeliveryBoys();
  if (type === 'product' && typeof loadProducts === 'function') loadProducts();
  if (type === 'subscription' && typeof loadSubscriptions === 'function') loadSubscriptions();
}
