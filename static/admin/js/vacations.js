// ==========================================
// Admin Vacation Mode JS Module
// ==========================================

let currentVacationStatus = 'all';
let vacationSearchQuery = '';
let vacationSearchTimeout = null;

async function loadVacationsData() {
  const tableBody = document.getElementById('vacations-table-body');
  if (!tableBody) return;

  try {
    let url = `/api/admin/vacations/?status=${currentVacationStatus}`;
    if (vacationSearchQuery.trim()) {
      url += `&search=${encodeURIComponent(vacationSearchQuery.trim())}`;
    }

    const res = await fetch(url);
    if (!res.ok) {
      if (res.status === 401 || res.status === 403) {
        window.location.href = '/dairypanel/login/';
        return;
      }
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    const vacations = data.vacations || [];
    const activeCount = data.active_vacations_count || 0;
    const totalCount = data.total_count || 0;

    // Update badges
    const activeBadge = document.getElementById('vacation-active-badge');
    if (activeBadge) {
      activeBadge.innerText = `${activeCount} Active`;
    }

    const sidebarBadge = document.getElementById('sidebar-vacations-badge');
    if (sidebarBadge) {
      if (activeCount > 0) {
        sidebarBadge.innerText = activeCount;
        sidebarBadge.classList.remove('hidden');
      } else {
        sidebarBadge.classList.add('hidden');
      }
    }

    const countDisplay = document.getElementById('vac-total-count');
    if (countDisplay) {
      countDisplay.innerText = totalCount;
    }

    if (vacations.length === 0) {
      tableBody.innerHTML = `
        <tr>
          <td colspan="9" class="text-center py-10 text-slate-400">
            <div class="flex flex-col items-center justify-center space-y-2">
              <i data-lucide="palmtree" class="w-8 h-8 text-slate-300"></i>
              <span class="text-sm font-medium">No vacation records found</span>
            </div>
          </td>
        </tr>
      `;
      if (window.lucide) lucide.createIcons();
      return;
    }

    tableBody.innerHTML = vacations.map(v => {
      let statusBadge = '';
      if (v.status === 'active') {
        statusBadge = '<span class="px-2 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-200">Active</span>';
      } else if (v.status === 'completed') {
        statusBadge = '<span class="px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">Completed</span>';
      } else {
        statusBadge = '<span class="px-2 py-0.5 rounded-full text-[11px] font-bold bg-rose-100 text-rose-800 border border-rose-200">Cancelled</span>';
      }

      const subsList = (v.affected_subscriptions || []).map(s => {
        return `<span class="inline-block px-1.5 py-0.5 text-[10px] bg-slate-100 text-slate-700 rounded mr-1 mb-1 font-mono">${s.plan_name} (#${s.subscription_id})</span>`;
      }).join('') || '<span class="text-slate-400 text-[11px]">None</span>';

      const partnerName = v.delivery_partner ? `${v.delivery_partner.name} (${v.delivery_partner.phone})` : '<span class="text-slate-400">Unassigned</span>';

      const actionButton = v.status === 'active' ? `
        <button onclick="adminCancelVacation(${v.id}, '${v.customer ? v.customer.name : 'Customer'}')" class="px-2.5 py-1 rounded-lg border border-rose-200 bg-rose-50 hover:bg-rose-100 text-rose-700 font-bold text-[11px] transition">
          Cancel Early
        </button>
      ` : '<span class="text-slate-400 text-[11px]">—</span>';

      return `
        <tr class="hover:bg-slate-50/60 transition">
          <td class="py-3 px-4 font-mono font-bold text-slate-900">#VAC-${v.id}</td>
          <td class="py-3 px-4">
            <div class="font-bold text-slate-900">${v.customer ? v.customer.name : 'Unknown'}</div>
            <div class="text-[11px] text-slate-500 font-mono">${v.customer ? v.customer.phone : ''}</div>
          </td>
          <td class="py-3 px-4 font-medium text-slate-700">${v.start_date}</td>
          <td class="py-3 px-4 font-medium text-slate-700">${v.end_date}</td>
          <td class="py-3 px-4 max-w-xs">${subsList}</td>
          <td class="py-3 px-4 text-slate-700">${partnerName}</td>
          <td class="py-3 px-4">${statusBadge}</td>
          <td class="py-3 px-4 text-slate-500 text-[11px] font-mono">${(v.created_at || '').substring(0, 10)}</td>
          <td class="py-3 px-4 text-right">${actionButton}</td>
        </tr>
      `;
    }).join('');

    if (window.lucide) lucide.createIcons();
  } catch (err) {
    console.error('Error loading vacations:', err);
    tableBody.innerHTML = `
      <tr>
        <td colspan="9" class="text-center py-6 text-rose-500 text-xs font-semibold">
          Failed to load vacations data. Please try again.
        </td>
      </tr>
    `;
  }
}

function filterVacationStatus(status) {
  currentVacationStatus = status;
  const buttons = ['all', 'active', 'completed', 'cancelled'];
  buttons.forEach(b => {
    const btn = document.getElementById(`vac-filter-${b}`);
    if (btn) {
      if (b === status) {
        btn.className = 'px-4 py-2 rounded-xl text-xs font-bold bg-emerald-800 text-white shadow-xs transition';
      } else {
        btn.className = 'px-3.5 py-2 rounded-xl text-xs font-semibold bg-white text-slate-700 border border-slate-200 hover:bg-slate-50 transition';
      }
    }
  });
  loadVacationsData();
}

function debounceVacationSearch() {
  clearTimeout(vacationSearchTimeout);
  vacationSearchTimeout = setTimeout(() => {
    const input = document.getElementById('vac-search-input');
    vacationSearchQuery = input ? input.value : '';
    loadVacationsData();
  }, 350);
}

async function adminCancelVacation(vacationId, customerName) {
  if (!confirm(`Are you sure you want to cancel Vacation Mode for ${customerName}? This will resume their eligible subscriptions and recreate daily deliveries starting today.`)) {
    return;
  }

  try {
    const res = await fetch('/api/admin/vacations/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ vacation_id: vacationId }),
    });

    const data = await res.json();
    if (res.ok) {
      showToast(data.message || 'Vacation cancelled successfully.');
      loadVacationsData();
      if (typeof loadStatsAndTrends === 'function') {
        loadStatsAndTrends();
      }
    } else {
      showToast(data.error || 'Failed to cancel vacation.', 'error');
    }
  } catch (err) {
    console.error('Admin cancel error:', err);
    showToast('Network error while cancelling vacation.', 'error');
  }
}
