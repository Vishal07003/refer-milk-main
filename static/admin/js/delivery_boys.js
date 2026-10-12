    // 4. Delivery Boys
cachedDeliveryBoys = [];
currentBoyStatusFilter = 'all';
boySearchTimeout = null;

    async function loadDeliveryBoys() {
      const tbody = document.getElementById('delivery-boys-table-body');
      try {
        const queryParams = new URLSearchParams();
        if (currentBoyStatusFilter !== 'all') queryParams.append('status', currentBoyStatusFilter);
        const searchInput = document.getElementById('boy-search-input');
        if (searchInput && searchInput.value.trim()) queryParams.append('search', searchInput.value.trim());

        const res = await fetch(`/api/admin/delivery-boys/?${queryParams.toString()}`);
        const data = await res.json();
        const list = data.delivery_boys || [];
        cachedDeliveryBoys = list;

        if (list.length === 0) {
          tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-slate-400">No delivery partners found matching current filters.</td></tr>`;
          return;
        }

        tbody.innerHTML = list.map(b => `
          <tr class="hover:bg-slate-50 transition">
            <td class="py-3 px-4 font-bold text-slate-900">
              <button onclick="openBoyDetailsModal(${b.id})" class="text-left font-bold text-slate-900 hover:text-brand transition flex items-center space-x-1.5">
                <span>${escapeHtml(b.name)}</span>
                <i data-lucide="external-link" class="w-3 h-3 text-slate-400"></i>
              </button>
            </td>
            <td class="py-3 px-4 text-slate-600 font-mono">${b.mobile}</td>
            <td class="py-3 px-4 text-slate-700">
              <div>${escapeHtml(b.zone)}</div>
              ${b.vehicle && b.vehicle !== '—' ? `<span class="text-[10px] text-slate-400 font-mono">${escapeHtml(b.vehicle)}</span>` : ''}
            </td>
            <td class="py-3 px-4">
              <button onclick="toggleBoyAvailability(${b.id})" class="px-2.5 py-1 rounded-full text-[11px] font-semibold transition ${b.is_available ? 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}">
                ${b.is_available ? '● On Duty' : '○ Off Duty'}
              </button>
            </td>
            <td class="py-3 px-4 font-bold text-sm ${b.cash_in_hand > 0 ? 'text-amber-700' : 'text-slate-600'}">₹${b.cash_in_hand.toFixed(2)}</td>
            <td class="py-3 px-4 font-semibold text-slate-800">${b.today_delivered} drops</td>
            <td class="py-3 px-4 text-right">
              <div class="flex items-center justify-end space-x-1.5">
                <button onclick="openBoyDetailsModal(${b.id})" class="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:text-brand hover:border-brand transition" title="View 360 Partner Profile">
                  <i data-lucide="eye" class="w-3.5 h-3.5"></i>
                </button>
                <button onclick="toggleBoyActiveStatus(${b.id})" class="p-1.5 rounded-lg border border-slate-200 ${b.is_active ? 'text-emerald-700 hover:bg-emerald-50' : 'text-red-600 hover:bg-red-50'} transition" title="Toggle Active Status">
                  <i data-lucide="power" class="w-3.5 h-3.5"></i>
                </button>
              </div>
            </td>
          </tr>
        `).join('');
        lucide.createIcons();
      } catch (e) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-6 text-red-500">Error loading partners.</td></tr>`;
      }
    }

    function debounceBoySearch() {
      clearTimeout(boySearchTimeout);
      boySearchTimeout = setTimeout(() => {
        loadDeliveryBoys();
      }, 300);
    }

    function filterBoyStatus(status) {
      currentBoyStatusFilter = status;
      ['all', 'on_duty', 'off_duty'].forEach(st => {
        const btn = document.getElementById(`boy-filter-${st}`);
        if (btn) {
          if (st === status) {
            btn.className = 'px-2.5 py-1 rounded-md font-semibold bg-white text-slate-900 shadow-xs transition';
          } else {
            btn.className = 'px-2.5 py-1 rounded-md font-medium text-slate-600 hover:text-slate-900 transition';
          }
        }
      });
      loadDeliveryBoys();
    }


    // Modal Control: Delivery Partner 360 Details
    async function openBoyDetailsModal(boyId) {
      document.getElementById('boy-details-modal').classList.remove('hidden');
      document.getElementById('detail-boy-name').innerText = 'Loading partner details...';
      try {
        const res = await fetch(`/api/admin/delivery-boys/${boyId}/`);
        const data = await res.json();
        const b = data.delivery_boy;
        if (!b) return showToast('Partner not found', true);

        document.getElementById('detail-boy-id').value = b.id;
        document.getElementById('detail-boy-name').innerText = b.name;
        document.getElementById('detail-boy-mobile').innerText = b.mobile;
        document.getElementById('detail-boy-fname').value = b.first_name || '';
        document.getElementById('detail-boy-lname').value = b.last_name || '';
        document.getElementById('detail-boy-vehicle-input').value = b.vehicle || '';
        document.getElementById('detail-boy-zone-input').value = b.zone || '';
        document.getElementById('detail-boy-cash').innerText = `₹${b.cash_in_hand.toFixed(2)}`;
        document.getElementById('detail-boy-total-collected').innerText = `₹${b.total_collected.toFixed(2)}`;
        document.getElementById('detail-boy-handed').innerText = `₹${b.total_handed_over.toFixed(2)}`;
        document.getElementById('detail-boy-on-duty').checked = !!b.is_available;
        document.getElementById('detail-boy-active').checked = !!b.is_active;
        lucide.createIcons();
      } catch (err) {
        showToast('Error loading partner details', true);
      }
    }

    function closeBoyDetailsModal() {
      document.getElementById('boy-details-modal').classList.add('hidden');
    }

    async function submitUpdateBoyProfile() {
      const id = document.getElementById('detail-boy-id').value;
      const fname = document.getElementById('detail-boy-fname').value.trim();
      const lname = document.getElementById('detail-boy-lname').value.trim();
      const vehicle = document.getElementById('detail-boy-vehicle-input').value.trim();
      const zone = document.getElementById('detail-boy-zone-input').value.trim();
      const isAvail = document.getElementById('detail-boy-on-duty').checked;
      const isActive = document.getElementById('detail-boy-active').checked;

      try {
        const res = await fetch(`/api/admin/delivery-boys/${id}/`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ first_name: fname, last_name: lname, vehicle, zone, is_available: isAvail, is_active: isActive })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Partner updated!');
          closeBoyDetailsModal();
          loadDeliveryBoys();
        } else {
          showToast(data.error || 'Failed to update partner', true);
        }
      } catch (err) {
        showToast('Network error', true);
      }
    }

    async function toggleBoyActiveStatus(id) {
      try {
        const res = await fetch('/api/admin/delivery-boys/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id, action: 'toggle_active' })
        });
        const data = await res.json();
        showToast(data.msg || 'Status updated');
        loadDeliveryBoys();
      } catch (err) {
        showToast('Failed to update status', true);
      }
    }


    // Add Delivery Partner Modal
    function openCreateBoyModal() {
      document.getElementById('boy-mobile').value = '';
      document.getElementById('boy-fname').value = '';
      document.getElementById('boy-lname').value = '';
      document.getElementById('boy-vehicle').value = '';
      document.getElementById('boy-zone').value = 'Sangola Central';
      document.getElementById('create-boy-modal').classList.remove('hidden');
      lucide.createIcons();
    }

    function closeCreateBoyModal() {
      document.getElementById('create-boy-modal').classList.add('hidden');
    }

    async function submitCreateBoy() {
      const mobile = document.getElementById('boy-mobile').value.trim();
      const fname = document.getElementById('boy-fname').value.trim();
      const lname = document.getElementById('boy-lname').value.trim();
      const vehicle = document.getElementById('boy-vehicle').value.trim();
      const zone = document.getElementById('boy-zone').value.trim();

      if (!mobile || mobile.length < 10) return showToast('Valid 10-digit mobile required', true);
      if (!fname) return showToast('First name is required', true);

      try {
        const res = await fetch('/api/admin/delivery-boys/create/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mobile_number: mobile, first_name: fname, last_name: lname, vehicle_number: vehicle, zone })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Partner created!');
          closeCreateBoyModal();
          refreshAllData();
        } else {
          showToast(data.error || 'Failed to create partner', true);
        }
      } catch (e) {
        showToast('Network error', true);
      }
    }

