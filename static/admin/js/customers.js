    // 5. Customers
cachedCustomers = [];
currentCustomerStatusFilter = 'all';

    async function loadCustomers(searchQuery = null) {
      const tbody = document.getElementById('customers-table-body');
      try {
        const query = searchQuery !== null ? searchQuery : (document.getElementById('customer-search-input')?.value.trim() || '');
        const queryParams = new URLSearchParams();
        if (query) queryParams.append('search', query);
        if (currentCustomerStatusFilter !== 'all') queryParams.append('status', currentCustomerStatusFilter);

        const url = `/api/admin/customers/?${queryParams.toString()}`;
        const res = await fetch(url);
        const data = await res.json();
        const list = data.customers || [];
        cachedCustomers = list;

        if (list.length === 0) {
          tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-slate-400">No customers found matching current filters.</td></tr>`;
          return;
        }

        tbody.innerHTML = list.map(u => `
          <tr class="hover:bg-slate-50 transition">
            <td class="py-3 px-4 font-bold text-slate-900">
              <button onclick="openCustomerDetails(${u.id})" class="text-left font-bold text-slate-900 hover:text-brand transition flex items-center space-x-1.5">
                <span>${escapeHtml(u.name)}</span>
                <i data-lucide="external-link" class="w-3 h-3 text-slate-400"></i>
              </button>
              ${u.email && u.email !== '—' ? `<div class="text-[11px] text-slate-400 font-normal">${escapeHtml(u.email)}</div>` : ''}
            </td>
            <td class="py-3 px-4 text-slate-600 font-mono">${u.mobile}</td>
            <td class="py-3 px-4 text-slate-600 truncate max-w-xs">
              <div>${escapeHtml(u.address)}</div>
              ${u.area ? `<span class="inline-block px-1.5 py-0.5 rounded text-[10px] bg-slate-100 text-slate-600 mt-0.5">${escapeHtml(u.area)}</span>` : ''}
            </td>
            <td class="py-3 px-4 font-mono font-bold text-brand">${escapeHtml(u.referral_code)}</td>
            <td class="py-3 px-4 font-semibold text-slate-700">${u.total_orders} orders</td>
            <td class="py-3 px-4">
              <button onclick="toggleCustomerActive(${u.id})" class="px-2.5 py-1 rounded-full text-[11px] font-semibold transition ${u.is_active ? 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200' : 'bg-red-100 text-red-800 hover:bg-red-200'}">
                ${u.is_active ? 'Active' : 'Inactive'}
              </button>
            </td>
            <td class="py-3 px-4 text-right">
              <div class="flex items-center justify-end space-x-1.5">
                <button onclick="openCustomerDetails(${u.id})" class="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:text-brand hover:border-brand transition" title="View 360 Details">
                  <i data-lucide="eye" class="w-3.5 h-3.5"></i>
                </button>
                <button onclick="openEditCustomerModal(${u.id})" class="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:text-blue-600 hover:border-blue-400 transition" title="Edit Profile">
                  <i data-lucide="edit" class="w-3.5 h-3.5"></i>
                </button>
                <button onclick="promptSoftDelete('customer', ${u.id}, '${escapeHtml(u.name)} (${escapeHtml(u.mobile)})')" class="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:text-rose-600 hover:border-rose-400 transition" title="Move Customer to Recycle Bin">
                  <i data-lucide="trash-2" class="w-3.5 h-3.5 text-rose-500"></i>
                </button>
              </div>
            </td>
          </tr>
        `).join('');
        lucide.createIcons();
      } catch (e) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-6 text-red-500">Error loading customers.</td></tr>`;
      }
    }

    function handleCustomerSearch(val) {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        loadCustomers(val.trim());
      }, 300);
    }

    function filterCustomerStatus(status) {
      currentCustomerStatusFilter = status;
      ['all', 'active', 'inactive'].forEach(st => {
        const btn = document.getElementById(`customer-filter-${st}`);
        if (btn) {
          if (st === status) {
            btn.className = 'px-2.5 py-1 rounded-md font-semibold bg-white text-slate-900 shadow-xs transition';
          } else {
            btn.className = 'px-2.5 py-1 rounded-md font-medium text-slate-600 hover:text-slate-900 transition';
          }
        }
      });
      loadCustomers();
    }

    // Modal Control: Add Customer
    function openCreateCustomerModal() {
      document.getElementById('cust-fname').value = '';
      document.getElementById('cust-lname').value = '';
      document.getElementById('cust-mobile').value = '';
      document.getElementById('cust-email').value = '';
      document.getElementById('cust-house').value = '';
      document.getElementById('cust-street').value = '';
      document.getElementById('cust-area').value = '';
      document.getElementById('cust-city').value = 'Sangola';
      document.getElementById('cust-pincode').value = '413307';
      document.getElementById('cust-active').checked = true;
      document.getElementById('create-customer-modal').classList.remove('hidden');
    }

    function closeCreateCustomerModal() {
      document.getElementById('create-customer-modal').classList.add('hidden');
    }

    async function submitCreateCustomer() {
      const fname = document.getElementById('cust-fname').value.trim();
      const lname = document.getElementById('cust-lname').value.trim();
      const mobile = document.getElementById('cust-mobile').value.trim();
      const email = document.getElementById('cust-email').value.trim();
      const house = document.getElementById('cust-house').value.trim();
      const street = document.getElementById('cust-street').value.trim();
      const area = document.getElementById('cust-area').value.trim();
      const city = document.getElementById('cust-city').value.trim();
      const pincode = document.getElementById('cust-pincode').value.trim();
      const isActive = document.getElementById('cust-active').checked;

      if (!fname) {
        showToast('Please enter customer first / full name.', true);
        return;
      }
      if (!mobile) {
        showToast('Please enter customer mobile number.', true);
        return;
      }
      const digits = mobile.replace(/\D/g, '');
      if (digits.length < 10 || digits.length > 15) {
        showToast('Valid 10 to 15 digit mobile number required.', true);
        return;
      }
      if (!house || !street) {
        showToast('Please provide complete delivery address (House & Street).', true);
        return;
      }

      try {
        const res = await fetch('/api/admin/customers/create/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            first_name: fname,
            last_name: lname,
            mobile_number: mobile,
            email: email,
            house_number: house,
            street: street,
            area: area,
            city: city,
            pincode: pincode,
            is_active: isActive
          })
        });

        const data = await res.json();
        if (res.ok && data.success) {
          showToast(data.msg || 'Customer created successfully!');
          closeCreateCustomerModal();
          loadCustomers();
          loadStatsAndTrends();
        } else {
          showToast(data.error || 'Failed to create customer.', true);
        }
      } catch (err) {
        showToast('Network error while saving customer.', true);
      }
    }

    // Modal Control: Edit Customer
    function openEditCustomerModal(customerId) {
      const cust = cachedCustomers.find(c => c.id === customerId);
      if (!cust) return;

      document.getElementById('edit-cust-id').value = cust.id;
      document.getElementById('edit-cust-fname').value = cust.first_name || cust.name.split(' ')[0] || '';
      document.getElementById('edit-cust-lname').value = cust.last_name || cust.name.split(' ').slice(1).join(' ') || '';
      document.getElementById('edit-cust-mobile').value = cust.mobile;
      document.getElementById('edit-cust-email').value = cust.email === '—' ? '' : cust.email;
      
      const addrParts = (cust.address || '').split(',').map(s => s.trim());
      document.getElementById('edit-cust-house').value = addrParts[0] || '';
      document.getElementById('edit-cust-street').value = addrParts[1] || '';
      document.getElementById('edit-cust-area').value = cust.area || '';
      document.getElementById('edit-cust-city').value = addrParts[2] || 'Sangola';
      document.getElementById('edit-cust-pincode').value = '413307';
      document.getElementById('edit-cust-active').checked = !!cust.is_active;

      document.getElementById('edit-customer-modal').classList.remove('hidden');
    }

    function closeEditCustomerModal() {
      document.getElementById('edit-customer-modal').classList.add('hidden');
    }

    async function submitEditCustomer() {
      const id = document.getElementById('edit-cust-id').value;
      const fname = document.getElementById('edit-cust-fname').value.trim();
      const lname = document.getElementById('edit-cust-lname').value.trim();
      const email = document.getElementById('edit-cust-email').value.trim();
      const house = document.getElementById('edit-cust-house').value.trim();
      const street = document.getElementById('edit-cust-street').value.trim();
      const area = document.getElementById('edit-cust-area').value.trim();
      const city = document.getElementById('edit-cust-city').value.trim();
      const pincode = document.getElementById('edit-cust-pincode').value.trim();
      const isActive = document.getElementById('edit-cust-active').checked;

      if (!fname) {
        showToast('Customer first name cannot be empty.', true);
        return;
      }

      try {
        const res = await fetch('/api/admin/customers/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action: 'update',
            user_id: id,
            first_name: fname,
            last_name: lname,
            email: email,
            house_number: house,
            street: street,
            area: area,
            city: city,
            pincode: pincode,
            is_active: isActive
          })
        });

        const data = await res.json();
        if (res.ok && data.success) {
          showToast(data.msg || 'Customer profile updated!');
          closeEditCustomerModal();
          loadCustomers();
        } else {
          showToast(data.error || 'Failed to update customer.', true);
        }
      } catch (err) {
        showToast('Network error while updating customer.', true);
      }
    }

    // Modal Control: Customer 360 Details
    async function openCustomerDetails(customerId) {
      document.getElementById('customer-details-modal').classList.remove('hidden');
      document.getElementById('detail-cust-name').innerText = 'Loading...';
      document.getElementById('detail-cust-mobile').innerText = '';
      document.getElementById('detail-cust-status').innerText = '';
      document.getElementById('detail-cust-addresses').innerHTML = '<p class="text-slate-400">Loading addresses...</p>';
      document.getElementById('detail-cust-orders').innerHTML = '<tr><td colspan="5" class="py-3 text-center text-slate-400">Loading orders...</td></tr>';
      document.getElementById('detail-cust-subs').innerHTML = '<tr><td colspan="5" class="py-3 text-center text-slate-400">Loading subscriptions...</td></tr>';
      document.getElementById('detail-cust-collections').innerHTML = '<tr><td colspan="5" class="py-3 text-center text-slate-400">Loading collections...</td></tr>';
      document.getElementById('detail-cust-referrals').innerHTML = '<p class="text-slate-400">Loading referrals...</p>';

      try {
        const res = await fetch(`/api/admin/customers/${customerId}/`);
        const data = await res.json();
        const c = data.customer;

        if (!c) {
          showToast('Customer profile not found.', true);
          closeCustomerDetailsModal();
          return;
        }

        document.getElementById('detail-cust-name').innerText = c.name;
        document.getElementById('detail-cust-mobile').innerText = c.mobile + (c.email && c.email !== '—' ? ` • ${c.email}` : '');
        document.getElementById('detail-cust-avatar').innerText = (c.first_name ? c.first_name[0] : 'C') + (c.last_name ? c.last_name[0] : 'U');
        
        const statusSpan = document.getElementById('detail-cust-status');
        statusSpan.innerText = c.is_active ? 'Active' : 'Inactive';
        statusSpan.className = `px-2 py-0.5 rounded-full text-[10px] font-bold ${c.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800'}`;

        document.getElementById('detail-cust-ref').innerText = c.referral_code;
        document.getElementById('detail-cust-orders-count').innerText = c.total_orders_count || 0;
        document.getElementById('detail-cust-spent').innerText = `₹${c.total_spent.toFixed(2)}`;
        document.getElementById('detail-cust-joined').innerText = c.joined_at;

        // Addresses
        const addrsList = c.addresses || [];
        if (addrsList.length === 0) {
          document.getElementById('detail-cust-addresses').innerHTML = '<p class="text-slate-400">No delivery address saved.</p>';
        } else {
          document.getElementById('detail-cust-addresses').innerHTML = addrsList.map(a => `
            <div class="p-2 rounded-lg bg-white border border-slate-200 flex items-center justify-between">
              <div>
                <span class="font-bold text-slate-800 capitalize">${a.label || 'Home'}:</span>
                <span class="text-slate-600">${escapeHtml(a.full_address)}</span>
              </div>
              ${a.is_default ? '<span class="px-1.5 py-0.5 rounded text-[10px] bg-emerald-50 text-emerald-700 font-semibold border border-emerald-200">Default</span>' : ''}
            </div>
          `).join('');
        }

        // Orders
        const ordsList = c.orders || [];
        if (ordsList.length === 0) {
          document.getElementById('detail-cust-orders').innerHTML = '<tr><td colspan="5" class="py-3 text-center text-slate-400">No orders placed yet</td></tr>';
        } else {
          document.getElementById('detail-cust-orders').innerHTML = ordsList.map(o => `
            <tr class="hover:bg-slate-50">
              <td class="py-1.5 px-2 font-bold text-slate-900">#${o.id}</td>
              <td class="py-1.5 px-2 text-slate-700">${escapeHtml(o.items_summary)}</td>
              <td class="py-1.5 px-2 font-bold text-slate-900">₹${o.total_amount.toFixed(2)}</td>
              <td class="py-1.5 px-2">
                <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold ${o.status === 'delivered' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}">${o.status_display || o.status}</span>
              </td>
              <td class="py-1.5 px-2 text-slate-500">${o.created_at}</td>
            </tr>
          `).join('');
        }

        // Subscriptions
        const subsList = c.subscriptions || [];
        if (subsList.length === 0) {
          document.getElementById('detail-cust-subs').innerHTML = '<tr><td colspan="5" class="py-3 text-center text-slate-400">No active subscriptions</td></tr>';
        } else {
          document.getElementById('detail-cust-subs').innerHTML = subsList.map(s => `
            <tr class="hover:bg-slate-50">
              <td class="py-1.5 px-2 font-bold text-slate-900">#${s.id}</td>
              <td class="py-1.5 px-2 text-slate-800 font-semibold">${escapeHtml(s.product_name)} • ${s.quantity}L (₹${s.rate}/L)</td>
              <td class="py-1.5 px-2 text-slate-600">${escapeHtml(s.delivery_slot)}</td>
              <td class="py-1.5 px-2 text-slate-700">${escapeHtml(s.delivery_boy)}</td>
              <td class="py-1.5 px-2">
                <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold ${s.status === 'active' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'}">${s.status}</span>
              </td>
            </tr>
          `).join('');
        }

        // Collections
        const colsList = c.collections || [];
        if (colsList.length === 0) {
          document.getElementById('detail-cust-collections').innerHTML = '<tr><td colspan="5" class="py-3 text-center text-slate-400">No cash collections recorded</td></tr>';
        } else {
          document.getElementById('detail-cust-collections').innerHTML = colsList.map(col => `
            <tr class="hover:bg-slate-50">
              <td class="py-1.5 px-2 font-bold text-slate-900">#${col.id}</td>
              <td class="py-1.5 px-2 text-slate-700 font-semibold">Order #${col.order_id}</td>
              <td class="py-1.5 px-2 font-bold text-emerald-700">₹${col.amount.toFixed(2)} (Cash)</td>
              <td class="py-1.5 px-2 text-slate-700">${escapeHtml(col.delivery_partner)}</td>
              <td class="py-1.5 px-2">
                <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold ${col.status === 'verified' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}">${col.status}</span>
              </td>
            </tr>
          `).join('');
        }

        // Referrals
        const refsList = c.referrals || [];
        if (refsList.length === 0) {
          document.getElementById('detail-cust-referrals').innerHTML = '<p class="text-slate-400">No friends referred yet.</p>';
        } else {
          document.getElementById('detail-cust-referrals').innerHTML = refsList.map(r => `
            <div class="flex items-center justify-between p-2 rounded-lg bg-slate-50 border border-slate-100">
              <span class="font-medium text-slate-800">${escapeHtml(r.name)} (${r.mobile})</span>
              <span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-800 uppercase">${r.status}</span>
            </div>
          `).join('');
        }

        lucide.createIcons();
      } catch (err) {
        showToast('Error loading customer 360 details.', true);
      }
    }

    function closeCustomerDetailsModal() {
      document.getElementById('customer-details-modal').classList.add('hidden');
    }

    // Toggle Customer Active Status
    async function toggleCustomerActive(userId) {
      try {
        const res = await fetch('/api/admin/customers/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: userId, action: 'toggle_active' })
        });
        const data = await res.json();
        showToast(data.msg || 'Status updated');
        loadCustomers();
      } catch (err) {
        showToast('Failed to update customer status', true);
      }
    }

