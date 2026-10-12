    // 3. Orders & Dispatch
cachedOrders = [];
orderSearchTimeout = null;

    async function loadOrders() {
      const tbody = document.getElementById('orders-table-body');
      const filter = document.getElementById('orders-status-filter')?.value || 'all';
      const searchVal = document.getElementById('order-search-input')?.value.trim() || '';
      try {
        const queryParams = new URLSearchParams();
        if (filter !== 'all') queryParams.append('status', filter);
        if (searchVal) queryParams.append('search', searchVal);

        const res = await fetch(`/api/admin/orders/?${queryParams.toString()}`);
        const data = await res.json();
        let orders = data.orders || [];
        cachedOrders = orders;

        if (orders.length === 0) {
          tbody.innerHTML = `<tr><td colspan="8" class="text-center py-8 text-slate-400">No matching orders found.</td></tr>`;
          return;
        }

        tbody.innerHTML = orders.map(o => `
          <tr class="hover:bg-slate-50 transition">
            <td class="py-3 px-4 font-bold text-slate-900">
              <button onclick="openOrderDetailsModal(${o.id})" class="text-brand hover:underline font-bold">#${o.id}</button>
            </td>
            <td class="py-3 px-4 font-semibold text-slate-800">${escapeHtml(o.customer_name)}<div class="text-[11px] text-slate-400">${o.customer_mobile}</div></td>
            <td class="py-3 px-4 text-slate-600 truncate max-w-xs">${escapeHtml(o.items_summary)}</td>
            <td class="py-3 px-4 font-bold text-slate-900">₹${o.total_amount.toFixed(2)}</td>
            <td class="py-3 px-4 text-slate-700">${escapeHtml(o.delivery_boy || 'Unassigned')}</td>
            <td class="py-3 px-4"><span class="px-2 py-0.5 bg-emerald-50 text-emerald-800 rounded font-semibold text-[10px] uppercase border border-emerald-200">Cash</span></td>
            <td class="py-3 px-4">
              <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${o.status === 'delivered' ? 'bg-emerald-100 text-emerald-800' : o.status === 'cancelled' ? 'bg-red-100 text-red-800' : 'bg-amber-100 text-amber-800'}">
                ${o.status}
              </span>
            </td>
            <td class="py-3 px-4 text-right">
              <div class="flex items-center justify-end space-x-1.5">
                <button onclick="openOrderDetailsModal(${o.id})" class="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:text-brand hover:border-brand transition" title="View / Edit Order">
                  <i data-lucide="edit-3" class="w-3.5 h-3.5"></i>
                </button>
                ${o.status !== 'delivered' && o.status !== 'cancelled' ? `
                  <button onclick="cancelOrderPrompt(${o.id})" class="p-1.5 rounded-lg border border-red-200 text-red-600 hover:bg-red-50 transition" title="Cancel Order">
                    <i data-lucide="x-circle" class="w-3.5 h-3.5"></i>
                  </button>
                ` : ''}
              </div>
            </td>
          </tr>
        `).join('');
        lucide.createIcons();
      } catch (e) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-red-500">Error loading orders.</td></tr>`;
      }
    }

    function debounceOrderSearch() {
      clearTimeout(orderSearchTimeout);
      orderSearchTimeout = setTimeout(() => {
        loadOrders();
      }, 300);
    }

    function filterOrdersStatus() {
      loadOrders();
    }


    // Modal Control: Order Details & Edit
    async function openOrderDetailsModal(orderId) {
      document.getElementById('order-details-modal').classList.remove('hidden');
      document.getElementById('order-modal-title').innerText = `Order #${orderId}`;
      document.getElementById('manage-order-id').value = orderId;

      try {
        const res = await fetch(`/api/admin/orders/${orderId}/`);
        const data = await res.json();
        const o = data.order;
        if (!o) return showToast('Order not found', true);

        document.getElementById('manage-order-customer').innerText = `${o.customer_name} (${o.customer_mobile})`;
        document.getElementById('manage-order-address').innerText = o.address;
        document.getElementById('manage-order-amount').innerText = `₹${o.total_amount.toFixed(2)}`;
        document.getElementById('manage-order-items').innerText = (o.items || []).map(i => `${i.product_name} x${i.quantity}`).join(', ') || 'Milk Order';

        const boySelect = document.getElementById('manage-order-boy');
        boySelect.innerHTML = '<option value="">-- Unassigned --</option>' + cachedDeliveryBoys.map(b => `<option value="${b.id}" ${o.delivery_boy_id === b.id ? 'selected' : ''}>${escapeHtml(b.name)}</option>`).join('');

        document.getElementById('manage-order-status').value = o.status;
        document.getElementById('manage-order-pay-status').value = o.payment_status;
      } catch (err) {
        showToast('Error loading order', true);
      }
    }

    function closeOrderDetailsModal() {
      document.getElementById('order-details-modal').classList.add('hidden');
    }

    async function submitUpdateOrder() {
      const id = document.getElementById('manage-order-id').value;
      const boyId = document.getElementById('manage-order-boy').value;
      const status = document.getElementById('manage-order-status').value;
      const payStatus = document.getElementById('manage-order-pay-status').value;

      try {
        const res = await fetch(`/api/admin/orders/${id}/`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ delivery_boy_id: boyId || null, status, payment_status: payStatus })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Order updated!');
          closeOrderDetailsModal();
          loadOrders();
          loadStatsAndTrends();
        } else {
          showToast(data.error || 'Failed to update order', true);
        }
      } catch (err) {
        showToast('Network error', true);
      }
    }

    async function cancelOrderPrompt(orderId) {
      if (!confirm(`Are you sure you want to cancel Order #${orderId}? Historical record will be kept.`)) return;
      try {
        const res = await fetch(`/api/admin/orders/${orderId}/`, {
          method: 'DELETE'
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Order cancelled');
          loadOrders();
          loadStatsAndTrends();
        } else {
          showToast(data.error || 'Cannot cancel order', true);
        }
      } catch (e) {
        showToast('Network error', true);
      }
    }

    async function cancelCurrentOrder() {
      const id = document.getElementById('manage-order-id').value;
      if (id) {
        closeOrderDetailsModal();
        cancelOrderPrompt(id);
      }
    }


    async function assignOrder(orderId, boyId) {
      if (!boyId) return;
      try {
        const res = await fetch(`/api/admin/orders/${orderId}/assign/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ delivery_boy_id: boyId })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Order assigned!');
          refreshAllData();
        } else {
          showToast(data.error || 'Failed to assign order', true);
        }
      } catch (e) {
        showToast('Network error', true);
      }
    }

