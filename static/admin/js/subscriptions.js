    // 6B. Customer Subscriptions Management & Approvals
cachedSubscriptions = [];
currentSubStatusFilter = 'all';
subSearchTimeout = null;

    async function loadSubscriptions() {
      const tbody = document.getElementById('subscriptions-table-body');
      if (!tbody) return;
      try {
        const queryParams = new URLSearchParams();
        if (currentSubStatusFilter !== 'all') queryParams.append('status', currentSubStatusFilter);
        const searchInput = document.getElementById('sub-search-input');
        if (searchInput && searchInput.value.trim()) queryParams.append('search', searchInput.value.trim());

        const res = await fetch(`/api/admin/subscriptions/?${queryParams.toString()}`);
        const data = await res.json();
        const list = data.subscriptions || [];
        cachedSubscriptions = list;

        // Update pending approval counter badge (always reflects total pending across all subscriptions)
        const pendingCount = (typeof data.pending_count === 'number') ? data.pending_count : list.filter(s => s.status === 'pending').length;
        const pendingBadge = document.getElementById('sub-pending-badge');
        if (pendingBadge) {
          pendingBadge.textContent = pendingCount;
          if (pendingCount > 0) {
            pendingBadge.className = 'ml-1 px-1.5 py-0.2 rounded-full bg-red-600 text-white text-[10px] font-bold animate-pulse';
          } else {
            pendingBadge.className = 'ml-1 px-1.5 py-0.2 rounded-full bg-amber-200 text-amber-900 text-[10px]';
          }
        }

        if (list.length === 0) {
          tbody.innerHTML = `<tr><td colspan="9" class="text-center py-8 text-slate-400">No subscriptions found for current filter.</td></tr>`;
          return;
        }

        // Update pagination records counter display
        const totalCount = (typeof data.total_count === 'number') ? data.total_count : list.length;
        const countShownEl = document.getElementById('sub-count-shown');
        const countTotalEl = document.getElementById('sub-count-total');
        if (countShownEl) countShownEl.textContent = list.length;
        if (countTotalEl) countTotalEl.textContent = totalCount;

        tbody.innerHTML = list.map(s => {
          // Status Pill Badge
          let statusBadgeHtml = '<span class="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-700">Pending</span>';
          if (s.status === 'active') {
            statusBadgeHtml = '<span class="px-3 py-1 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/80">Active</span>';
          } else if (s.status === 'paused') {
            statusBadgeHtml = '<span class="px-3 py-1 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200/80">Paused</span>';
          } else if (s.status === 'cancelled') {
            statusBadgeHtml = '<span class="px-3 py-1 rounded-full text-[11px] font-semibold bg-rose-50 text-rose-600 border border-rose-200/80">Cancelled</span>';
          } else if (s.status === 'pending') {
            statusBadgeHtml = '<span class="px-3 py-1 rounded-full text-[11px] font-semibold bg-amber-100 text-amber-900 border border-amber-300">Pending</span>';
          }

          // Assigned Partner with Initials Avatar or Unassigned Pill
          let partnerHtml = '<span class="px-2.5 py-1 rounded-md text-[11px] font-semibold italic bg-amber-50 text-amber-600 border border-amber-200/60">Unassigned</span>';
          if (s.delivery_boy && s.delivery_boy !== 'Unassigned') {
            const parts = s.delivery_boy.trim().split(' ');
            const initials = parts.length > 1 ? (parts[0][0] + parts[1][0]).toUpperCase() : parts[0].slice(0, 2).toUpperCase();
            partnerHtml = `
              <div class="flex items-center space-x-2">
                <div class="w-6 h-6 rounded-full bg-slate-200 text-slate-600 text-[10px] font-bold flex items-center justify-center shrink-0">
                  ${initials}
                </div>
                <span class="text-slate-800 font-semibold text-xs capitalize">${escapeHtml(s.delivery_boy)}</span>
              </div>
            `;
          }

          // Delivery Slot Icon & Text
          const isEvening = (s.delivery_slot || '').toLowerCase().includes('evening') || (s.delivery_slot || '').toLowerCase().includes('night');
          const slotIcon = isEvening 
            ? '<i data-lucide="moon" class="w-3.5 h-3.5 text-indigo-500"></i>' 
            : '<i data-lucide="sun" class="w-3.5 h-3.5 text-amber-500"></i>';

          return `
          <tr class="hover:bg-slate-50/70 transition border-b border-slate-100 last:border-b-0">
            <td class="py-3.5 px-4 font-bold text-slate-800 text-xs">#${s.id}</td>
            <td class="py-3.5 px-4">
              <div class="font-bold text-slate-900 text-xs">${escapeHtml(s.customer_name)}</div>
              <div class="text-[11px] text-slate-400 font-mono mt-0.5">${s.customer_mobile}</div>
            </td>
            <td class="py-3.5 px-4">
              <div class="font-bold text-slate-900 text-xs">${escapeHtml(s.plan_name || s.product_name)}</div>
              <div class="flex items-center space-x-1.5 text-[11px] text-emerald-700 font-medium mt-0.5">
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-600 inline-block"></span>
                <span>${escapeHtml(s.product_name)}</span>
              </div>
            </td>
            <td class="py-3.5 px-4">
              <div class="font-bold text-slate-900 text-xs">${s.quantity} ${escapeHtml(s.unit)}</div>
              <div class="text-[11px] text-slate-500 font-medium mt-0.5">₹${s.rate}/${s.unit}</div>
            </td>
            <td class="py-3.5 px-4">
              <div class="flex items-center space-x-1.5 font-semibold text-slate-800 text-xs">
                ${slotIcon}
                <span>${escapeHtml(s.delivery_slot)}</span>
              </div>
              <div class="text-[11px] text-slate-400 mt-0.5">Starts: ${s.start_date}</div>
            </td>
            <td class="py-3.5 px-4 text-slate-600 max-w-[200px] truncate text-[11px]" title="${escapeHtml(s.delivery_address)}">
              ${escapeHtml(s.delivery_address)}
            </td>
            <td class="py-3.5 px-4">
              ${partnerHtml}
            </td>
            <td class="py-3.5 px-4">
              ${statusBadgeHtml}
            </td>
            <td class="py-3.5 px-4 text-right">
              <div class="flex items-center justify-end space-x-2 flex-nowrap whitespace-nowrap">
                ${s.status === 'pending' ? `
                  <button onclick="openApproveSubModal(${s.id})" class="px-2.5 py-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-800 text-white text-[11px] font-bold shadow-xs transition flex items-center space-x-1" title="Approve subscription request">
                    <i data-lucide="check" class="w-3.5 h-3.5 stroke-[2.5]"></i>
                    <span>Approve</span>
                  </button>
                  <button onclick="openAssignSubPartnerModal(${s.id})" class="px-2.5 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-[11px] font-semibold transition flex items-center space-x-1" title="${s.delivery_boy_id ? 'Change Assigned Delivery Partner' : 'Assign Delivery Partner'}">
                    <i data-lucide="edit-3" class="w-3.5 h-3.5 text-slate-400"></i>
                    <span>${s.delivery_boy_id ? 'Change' : 'Assign'}</span>
                  </button>
                  <button onclick="openDeleteSubModal(${s.id})" class="px-2.5 py-1.5 rounded-lg bg-white border border-rose-200 text-rose-600 hover:bg-rose-50 text-[11px] font-semibold transition flex items-center space-x-1" title="Delete pending subscription request">
                    <i data-lucide="trash-2" class="w-3.5 h-3.5 text-rose-500"></i>
                    <span>Delete</span>
                  </button>
                ` : ''}
                ${s.status === 'active' ? `
                  <button onclick="openAssignSubPartnerModal(${s.id})" class="px-2.5 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-[11px] font-semibold transition flex items-center space-x-1" title="${s.delivery_boy_id ? 'Change Delivery Partner' : 'Assign Delivery Partner'}">
                    <i data-lucide="edit-3" class="w-3.5 h-3.5 text-slate-400"></i>
                    <span>${s.delivery_boy_id ? 'Change' : 'Assign'}</span>
                  </button>
                  <button onclick="updateSubStatus(${s.id}, 'pause')" class="px-2.5 py-1.5 rounded-lg bg-white border border-amber-300 text-amber-700 hover:bg-amber-50 text-[11px] font-semibold transition flex items-center space-x-1" title="Pause daily deliveries">
                    <i data-lucide="pause-circle" class="w-3.5 h-3.5 text-amber-600"></i>
                    <span>Pause</span>
                  </button>
                  <button onclick="openDeleteSubModal(${s.id})" class="px-2.5 py-1.5 rounded-lg bg-white border border-rose-200 text-rose-600 hover:bg-rose-50 text-[11px] font-semibold transition flex items-center space-x-1" title="Archive subscription">
                    <i data-lucide="trash-2" class="w-3.5 h-3.5 text-rose-500"></i>
                    <span>Delete</span>
                  </button>
                ` : ''}
                ${s.status === 'paused' ? `
                  <button onclick="openViewSubscriptionModal(${s.id})" class="px-2.5 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-[11px] font-semibold transition flex items-center space-x-1" title="View details">
                    <i data-lucide="eye" class="w-3.5 h-3.5 text-slate-400"></i>
                    <span>View</span>
                  </button>
                  <button onclick="updateSubStatus(${s.id}, 'resume')" class="px-2.5 py-1.5 rounded-lg bg-white border border-emerald-300 text-emerald-700 hover:bg-emerald-50 text-[11px] font-semibold transition flex items-center space-x-1" title="Resume daily deliveries">
                    <i data-lucide="play-circle" class="w-3.5 h-3.5 text-emerald-600"></i>
                    <span>Resume</span>
                  </button>
                  <button onclick="openDeleteSubModal(${s.id})" class="px-2.5 py-1.5 rounded-lg bg-white border border-rose-200 text-rose-600 hover:bg-rose-50 text-[11px] font-semibold transition flex items-center space-x-1" title="Archive subscription">
                    <i data-lucide="trash-2" class="w-3.5 h-3.5 text-rose-500"></i>
                    <span>Delete</span>
                  </button>
                ` : ''}
                ${s.status === 'cancelled' ? `
                  <button onclick="openViewSubscriptionModal(${s.id})" class="px-2.5 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-[11px] font-semibold transition flex items-center space-x-1" title="View historical subscription details">
                    <i data-lucide="eye" class="w-3.5 h-3.5 text-slate-400"></i>
                    <span>View</span>
                  </button>
                  <button onclick="openDeleteSubModal(${s.id})" class="px-2.5 py-1.5 rounded-lg bg-white border border-rose-200 text-rose-600 hover:bg-rose-50 text-[11px] font-semibold transition flex items-center space-x-1" title="Archive subscription record">
                    <i data-lucide="trash-2" class="w-3.5 h-3.5 text-rose-500"></i>
                    <span>Delete</span>
                  </button>
                ` : ''}
              </div>
            </td>
          </tr>
        `;
        }).join('');
        lucide.createIcons();
      } catch (e) {
        tbody.innerHTML = `<tr><td colspan="9" class="text-center py-6 text-red-500">Error loading subscriptions.</td></tr>`;
      }
    }

    function filterSubStatus(status) {
      currentSubStatusFilter = status;
      ['all', 'pending', 'active', 'paused', 'cancelled'].forEach(s => {
        const btn = document.getElementById(`sub-filter-${s}`);
        if (btn) {
          if (s === status) {
            btn.className = 'px-4 py-2 rounded-xl text-xs font-bold bg-emerald-800 text-white shadow-xs transition';
          } else {
            btn.className = 'px-3.5 py-2 rounded-xl text-xs font-semibold bg-white text-slate-700 border border-slate-200 hover:bg-slate-50 transition';
          }
        }
      });
      loadSubscriptions();
    }

    function debounceSubSearch() {
      clearTimeout(subSearchTimeout);
      subSearchTimeout = setTimeout(loadSubscriptions, 300);
    }


    // Modal Control: Approve & Activate Subscription
    function openApproveSubModal(subId) {
      const sub = cachedSubscriptions.find(s => s.id === subId);
      if (!sub) return showToast('Subscription not found', true);

      document.getElementById('approve-sub-id').value = sub.id;
      document.getElementById('approve-modal-title').innerText = `Approve Subscription #${sub.id}`;
      document.getElementById('approve-cust-name').innerText = `${sub.customer_name} (${sub.customer_mobile})`;
      document.getElementById('approve-plan-name').innerText = `${sub.plan_name} (${sub.product_name})`;
      document.getElementById('approve-addr-text').innerText = sub.delivery_address;
      document.getElementById('approve-sub-qty').value = sub.quantity;

      const todayStr = new Date().toISOString().slice(0, 10);
      document.getElementById('approve-sub-start-date').value = sub.start_date_raw || todayStr;

      // Delivery Partner options
      const boySelect = document.getElementById('approve-sub-boy');
      if (boySelect) {
        boySelect.innerHTML = '<option value="">-- Select Delivery Partner --</option>' +
          cachedDeliveryBoys.map(b => `<option value="${b.id}" ${b.id === sub.delivery_boy_id ? 'selected' : ''}>${escapeHtml(b.name)} (${b.mobile}) - ${escapeHtml(b.zone)}</option>`).join('');
      }

      document.getElementById('approve-sub-modal').classList.remove('hidden');
    }

    function closeApproveSubModal() {
      document.getElementById('approve-sub-modal').classList.add('hidden');
    }

    async function submitApproveSub() {
      const subId = document.getElementById('approve-sub-id').value;
      const qty = document.getElementById('approve-sub-qty').value;
      const startDate = document.getElementById('approve-sub-start-date').value;
      const boyId = document.getElementById('approve-sub-boy').value;

      if (!qty || !startDate) {
        return showToast('Quantity and start date are required.', true);
      }

      try {
        const res = await fetch('/api/admin/subscriptions/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id: subId,
            action: 'approve',
            quantity: qty,
            start_date: startDate,
            delivery_boy_id: boyId || null
          })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Subscription approved and activated!');
          closeApproveSubModal();
          loadSubscriptions();
          loadStatsAndTrends();
        } else {
          showToast(data.error || 'Failed to approve subscription', true);
        }
      } catch (err) {
        showToast('Network error during approval', true);
      }
    }

    // Modal Control: Assign / Reassign Partner to Subscription
    function openAssignSubPartnerModal(subId) {
      const sub = cachedSubscriptions.find(s => s.id === subId);
      if (!sub) return showToast('Subscription not found', true);

      document.getElementById('assign-sub-id').value = sub.id;
      document.getElementById('assign-partner-modal-title').innerText = `Assign Partner: Sub #${sub.id}`;
      document.getElementById('assign-sub-num').innerText = `#${sub.id} (${sub.plan_name})`;
      document.getElementById('assign-sub-cust').innerText = `${sub.customer_name} (${sub.customer_mobile})`;
      document.getElementById('assign-sub-addr').innerText = sub.delivery_address;
      document.getElementById('assign-sub-current-boy').innerText = sub.delivery_boy || 'Unassigned';

      const boySelect = document.getElementById('assign-sub-boy-select');
      if (boySelect) {
        const activeBoys = cachedDeliveryBoys.filter(b => b.is_active !== false);
        boySelect.innerHTML = '<option value="">-- Unassigned --</option>' +
          activeBoys.map(b => `<option value="${b.id}" ${b.id === sub.delivery_boy_id ? 'selected' : ''}>${escapeHtml(b.name)} (${b.mobile}) - ${escapeHtml(b.zone)}</option>`).join('');
      }

      document.getElementById('assign-sub-partner-modal').classList.remove('hidden');
      if (window.lucide && typeof lucide.createIcons === 'function') {
        lucide.createIcons();
      }
    }

    function closeAssignSubPartnerModal() {
      document.getElementById('assign-sub-partner-modal').classList.add('hidden');
    }

    async function submitAssignSubPartner() {
      const subId = document.getElementById('assign-sub-id').value;
      const boyId = document.getElementById('assign-sub-boy-select').value;

      try {
        const res = await fetch('/api/admin/subscriptions/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id: subId,
            action: 'assign_partner',
            delivery_boy_id: boyId ? parseInt(boyId) : null
          })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Delivery partner updated successfully!');
          closeAssignSubPartnerModal();
          loadSubscriptions();
        } else {
          showToast(data.error || 'Failed to assign delivery partner', true);
        }
      } catch (err) {
        showToast('Network error updating delivery partner', true);
      }
    }

    // Modal Control: View Subscription 360
    function openViewSubscriptionModal(subId) {
      const sub = cachedSubscriptions.find(s => s.id === subId);
      if (!sub) return showToast('Subscription not found', true);

      document.getElementById('view-sub-id').innerText = `#${sub.id}`;
      document.getElementById('view-sub-cust').innerText = sub.customer_name;
      document.getElementById('view-sub-phone').innerText = sub.customer_mobile;
      document.getElementById('view-sub-address').innerText = sub.delivery_address;
      const planProdDisplay = (sub.plan_name && sub.product_name && sub.plan_name.toLowerCase() !== sub.product_name.toLowerCase()) 
        ? `${sub.plan_name} • ${sub.product_name}` 
        : (sub.plan_name || sub.product_name);
      document.getElementById('view-sub-product').innerText = planProdDisplay;
      document.getElementById('view-sub-rate').innerText = `${sub.quantity} ${sub.unit} @ ₹${sub.rate}/${sub.unit}`;
      document.getElementById('view-sub-slot').innerText = sub.delivery_slot;
      document.getElementById('view-sub-partner').innerText = sub.delivery_boy || 'Unassigned';

      let statusBadgeClass = 'bg-slate-100 text-slate-700';
      if (sub.status === 'active') statusBadgeClass = 'bg-emerald-100 text-emerald-800';
      else if (sub.status === 'pending') statusBadgeClass = 'bg-amber-100 text-amber-900';
      else if (sub.status === 'paused') statusBadgeClass = 'bg-sky-100 text-sky-800';
      else if (sub.status === 'cancelled') statusBadgeClass = 'bg-red-100 text-red-800';

      const badge = document.getElementById('view-sub-status-badge');
      badge.className = `px-2.5 py-0.5 rounded-full text-[11px] font-bold uppercase ${statusBadgeClass}`;
      badge.innerText = sub.status_display || sub.status;

      document.getElementById('view-sub-start').innerText = sub.start_date || '—';
      document.getElementById('view-sub-end').innerText = sub.end_date || '—';

      const editBtn = document.getElementById('view-sub-edit-btn');
      if (editBtn) {
        editBtn.onclick = () => {
          closeViewSubscriptionModal();
          openAssignSubPartnerModal(sub.id);
        };
      }

      document.getElementById('view-subscription-modal').classList.remove('hidden');
      if (window.lucide && typeof lucide.createIcons === 'function') {
        lucide.createIcons();
      }
    }

    function closeViewSubscriptionModal() {
      document.getElementById('view-subscription-modal').classList.add('hidden');
    }

    // Modal Control: Confirm Delete / Archive Subscription
    function openDeleteSubModal(subId) {
      const sub = cachedSubscriptions.find(s => s.id === subId);
      if (!sub) return showToast('Subscription not found', true);

      document.getElementById('delete-sub-id').value = sub.id;
      document.getElementById('delete-sub-title-text').innerText = `#${sub.id} (${sub.plan_name || 'Direct'})`;
      document.getElementById('delete-sub-cust-name').innerText = `${sub.customer_name} (${sub.customer_mobile})`;
      document.getElementById('delete-sub-status-text').innerText = sub.status_display || sub.status;

      const subtitle = document.getElementById('delete-sub-subtitle');
      const note = document.getElementById('delete-sub-note');
      const confirmBtn = document.getElementById('delete-sub-confirm-btn');

      if (sub.status === 'pending') {
        subtitle.innerText = 'Permanently discard this unapproved pending subscription request?';
        note.innerText = 'This subscription has not started yet. Removing it will cleanly delete the request without affecting any customer account data.';
        confirmBtn.querySelector('span').innerText = 'Delete Request';
      } else {
        subtitle.innerText = 'Safely archive this subscription and stop future morning deliveries?';
        note.innerText = 'Historical deliveries, orders, payments, and cash handover reconciliation records are permanently preserved.';
        confirmBtn.querySelector('span').innerText = 'Archive Subscription';
      }

      document.getElementById('confirm-delete-sub-modal').classList.remove('hidden');
      if (window.lucide && typeof lucide.createIcons === 'function') {
        lucide.createIcons();
      }
    }

    function closeDeleteSubModal() {
      document.getElementById('confirm-delete-sub-modal').classList.add('hidden');
    }

    async function executeDeleteSubscription() {
      const subId = document.getElementById('delete-sub-id').value;
      if (!subId) return;

      try {
        const res = await fetch('/api/admin/subscriptions/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: subId, action: 'delete' })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Subscription removed successfully.');
          closeDeleteSubModal();
          loadSubscriptions();
          loadStatsAndTrends();
        } else {
          showToast(data.error || 'Failed to remove subscription', true);
        }
      } catch (err) {
        showToast('Network error deleting subscription', true);
      }
    }

    // Modal Control: Assign Plan to Customer
    function openCreateSubscriptionModal() {
      const custSelect = document.getElementById('sub-customer-select');
      if (custSelect) {
        custSelect.innerHTML = cachedCustomers.map(c => `<option value="${c.id}">${escapeHtml(c.name)} (${c.mobile})</option>`).join('');
      }

      const planSelect = document.getElementById('sub-plan-select');
      if (planSelect) {
        planSelect.innerHTML = '<option value="">-- Choose a Predefined Plan --</option>' +
          cachedSubscriptionPlans.filter(p => p.is_active).map(p =>
            `<option value="${p.id}" data-prodid="${p.product_id}" data-qty="${p.quantity}" data-price="${p.price_per_unit}">${escapeHtml(p.name)} (${p.quantity} ${p.unit} - ₹${p.price_per_unit}/${p.unit})</option>`
          ).join('');
      }

      const prodSelect = document.getElementById('sub-product-select');
      if (prodSelect) {
        prodSelect.innerHTML = cachedProducts.map(p => `<option value="${p.id}">${escapeHtml(p.name)} (₹${p.price}/${p.unit})</option>`).join('');
      }

      const boySelect = document.getElementById('sub-boy-select');
      if (boySelect) {
        boySelect.innerHTML = '<option value="">-- Unassigned --</option>' + cachedDeliveryBoys.map(b => `<option value="${b.id}">${escapeHtml(b.name)}</option>`).join('');
      }
      const today = new Date().toISOString().slice(0, 10);
      document.getElementById('sub-start-date').value = today;
      const future = new Date();
      future.setDate(future.getDate() + 30);
      document.getElementById('sub-end-date').value = future.toISOString().slice(0, 10);
      document.getElementById('create-subscription-modal').classList.remove('hidden');
    }

    function onSubPlanDropdownChange() {
      const planSelect = document.getElementById('sub-plan-select');
      if (!planSelect || !planSelect.selectedOptions[0]) return;
      const opt = planSelect.selectedOptions[0];
      const prodId = opt.getAttribute('data-prodid');
      const qty = opt.getAttribute('data-qty');
      if (prodId) {
        document.getElementById('sub-product-select').value = prodId;
      }
      if (qty) {
        document.getElementById('sub-quantity-input').value = qty;
      }
    }

    function closeCreateSubscriptionModal() {
      document.getElementById('create-subscription-modal').classList.add('hidden');
    }

    async function submitCreateSubscription() {
      const userId = document.getElementById('sub-customer-select').value;
      const planId = document.getElementById('sub-plan-select').value;
      const prodId = document.getElementById('sub-product-select').value;
      const qty = document.getElementById('sub-quantity-input').value;
      const startDate = document.getElementById('sub-start-date').value;
      const endDate = document.getElementById('sub-end-date').value;
      const boyId = document.getElementById('sub-boy-select').value;

      if (!userId || (!prodId && !planId) || !qty) return showToast('Customer, plan/product, and quantity required', true);

      try {
        const res = await fetch('/api/admin/subscriptions/create/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: userId,
            plan_id: planId || null,
            product_id: prodId,
            quantity: qty,
            start_date: startDate,
            end_date: endDate,
            delivery_boy_id: boyId || null
          })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Subscription plan activated successfully!');
          closeCreateSubscriptionModal();
          loadSubscriptions();
          loadStatsAndTrends();
        } else {
          showToast(data.error || 'Failed to create subscription', true);
        }
      } catch (e) {
        showToast('Network error', true);
      }
    }

    async function updateSubStatus(subId, action) {
      try {
        const res = await fetch('/api/admin/subscriptions/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: subId, action })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Subscription updated');
          loadSubscriptions();
          loadStatsAndTrends();
        } else {
          showToast(data.error || 'Failed to update subscription', true);
        }
      } catch (err) {
        showToast('Failed to update subscription', true);
      }
    }

    async function cancelSubPrompt(subId) {
      if (!confirm(`Are you sure you want to cancel Subscription #${subId}? Future deliveries will be stopped. Historical records are preserved.`)) return;
      updateSubStatus(subId, 'cancel');
    }

    function closeEditSubscriptionModal() {
      const modal = document.getElementById('edit-subscription-modal');
      if (modal) modal.classList.add('hidden');
    }

    async function submitUpdateSubscription() {
      const subId = document.getElementById('edit-sub-id')?.value;
      const qty = document.getElementById('edit-sub-quantity')?.value;
      const status = document.getElementById('edit-sub-status')?.value;
      const boyId = document.getElementById('edit-sub-boy')?.value;
      const startDate = document.getElementById('edit-sub-start-date')?.value;
      const endDate = document.getElementById('edit-sub-end-date')?.value;

      if (!subId) return;
      try {
        const res = await fetch('/api/admin/subscriptions/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id: subId,
            action: 'update',
            quantity: qty,
            status,
            delivery_boy_id: boyId || null,
            start_date: startDate,
            end_date: endDate
          })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Subscription updated');
          closeEditSubscriptionModal();
          loadSubscriptions();
          loadStatsAndTrends();
        } else {
          showToast(data.error || 'Failed to update subscription', true);
        }
      } catch (err) {
        showToast('Network error updating subscription', true);
      }
    }

