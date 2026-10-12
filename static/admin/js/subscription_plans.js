    // 6A. Subscription Plans Management
cachedSubscriptionPlans = [];
currentPlanStatusFilter = 'all';
planSearchTimeout = null;

    async function loadSubscriptionPlans() {
      const tbody = document.getElementById('subscription-plans-table-body');
      if (!tbody) return;
      try {
        const queryParams = new URLSearchParams();
        if (currentPlanStatusFilter !== 'all') queryParams.append('status', currentPlanStatusFilter);
        const searchInput = document.getElementById('plan-search-input');
        if (searchInput && searchInput.value.trim()) queryParams.append('search', searchInput.value.trim());

        const res = await fetch(`/api/admin/subscription-plans/?${queryParams.toString()}`);
        const data = await res.json();
        const list = data.plans || [];
        cachedSubscriptionPlans = list;

        // Populate plan dropdown for Admin Create Customer Subscription modal
        const planSelect = document.getElementById('sub-plan-select');
        if (planSelect) {
          planSelect.innerHTML = '<option value="">-- Choose a Predefined Plan --</option>' +
            list.filter(p => p.is_active).map(p => `<option value="${p.id}" data-prodid="${p.product_id}" data-qty="${p.quantity}" data-price="${p.price_per_unit}">${escapeHtml(p.name)} (${p.quantity} ${p.unit} - ₹${p.price_per_unit}/${p.unit})</option>`).join('');
        }

        if (list.length === 0) {
          tbody.innerHTML = `<tr><td colspan="9" class="text-center py-8 text-slate-400">No subscription plans found matching current criteria.</td></tr>`;
          return;
        }

        tbody.innerHTML = list.map(p => `
          <tr class="hover:bg-slate-50 transition">
            <td class="py-3 px-4 font-bold text-slate-900">${escapeHtml(p.name)}</td>
            <td class="py-3 px-4 font-semibold text-slate-700">${escapeHtml(p.product_name)}</td>
            <td class="py-3 px-4 text-slate-800 font-medium">${p.quantity} ${escapeHtml(p.unit)}</td>
            <td class="py-3 px-4 text-slate-600"><span class="px-2 py-0.5 rounded bg-slate-100 text-[11px] font-semibold uppercase">${escapeHtml(p.frequency_display)}</span></td>
            <td class="py-3 px-4 font-bold text-emerald-800">₹${p.price_per_unit.toFixed(2)} / ${escapeHtml(p.unit)}</td>
            <td class="py-3 px-4 text-slate-500 text-[11px] max-w-xs truncate">${escapeHtml(p.schedule_description)}</td>
            <td class="py-3 px-4"><span class="font-bold text-slate-900">${p.active_subscribers}</span> <span class="text-slate-400 text-[11px]">active</span></td>
            <td class="py-3 px-4">
              <button onclick="togglePlanActive(${p.id})" class="px-2.5 py-1 rounded-full text-[11px] font-semibold transition ${p.is_active ? 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}">
                ${p.is_active ? '● Active in App' : '○ Deactivated'}
              </button>
            </td>
            <td class="py-3 px-4 text-right">
              <div class="flex items-center justify-end space-x-1.5">
                <button onclick="openEditPlanModal(${p.id})" class="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:text-brand hover:border-brand transition" title="Edit Plan">
                  <i data-lucide="edit" class="w-3.5 h-3.5"></i>
                </button>
                <button onclick="deactivatePlanPrompt(${p.id}, '${escapeHtml(p.name)}')" class="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:text-amber-700 hover:border-amber-300 transition" title="Toggle / Deactivate Safely">
                  <i data-lucide="power" class="w-3.5 h-3.5"></i>
                </button>
              </div>
            </td>
          </tr>
        `).join('');
        lucide.createIcons();
      } catch (e) {
        tbody.innerHTML = `<tr><td colspan="9" class="text-center py-6 text-red-500">Error loading subscription plans.</td></tr>`;
      }
    }

    function filterPlanStatus(status) {
      currentPlanStatusFilter = status;
      ['all', 'active', 'inactive'].forEach(s => {
        const btn = document.getElementById(`plan-filter-${s}`);
        if (btn) {
          btn.className = s === status
            ? 'px-2.5 py-1 rounded-md font-semibold bg-white text-slate-900 shadow-xs transition'
            : 'px-2.5 py-1 rounded-md font-medium text-slate-600 hover:text-slate-900 transition';
        }
      });
      loadSubscriptionPlans();
    }

    function debouncePlanSearch() {
      clearTimeout(planSearchTimeout);
      planSearchTimeout = setTimeout(loadSubscriptionPlans, 300);
    }


    // Plan Creation and Editing Modals
    async function loadProductsForPlanModal(targetSelectId = null, selectedProductId = null) {
      const errBox = document.getElementById(targetSelectId === 'edit-plan-product' ? 'edit-plan-product-error' : 'new-plan-product-error');
      const errText = document.getElementById(targetSelectId === 'edit-plan-product' ? 'edit-plan-product-error-text' : 'new-plan-product-error-text');
      
      const newSelect = document.getElementById('new-plan-product');
      const editSelect = document.getElementById('edit-plan-product');

      if (errBox) errBox.classList.add('hidden');

      // If we don't have cached products, fetch them from the official API
      if (!cachedProducts || cachedProducts.length === 0) {
        if (newSelect && !newSelect.options.length) {
          newSelect.innerHTML = '<option value="">Loading active products...</option>';
        }
        if (editSelect && !editSelect.options.length) {
          editSelect.innerHTML = '<option value="">Loading active products...</option>';
        }
        try {
          const res = await fetch('/api/admin/products/');
          if (!res.ok) {
            throw new Error(`Server returned HTTP ${res.status}`);
          }
          const data = await res.json();
          cachedProducts = data.products || [];
        } catch (err) {
          console.error('Failed to load products for plan modal:', err);
          if (errBox) {
            if (errText) errText.textContent = 'Failed to load active products. Please check connection and retry.';
            errBox.classList.remove('hidden');
          }
          if (newSelect) newSelect.innerHTML = '<option value="">Failed to load products</option>';
          if (editSelect) editSelect.innerHTML = '<option value="">Failed to load products</option>';
          showToast('Failed to load products for subscription plan', true);
          return false;
        }
      }

      // Filter for active products that can be subscribed to
      const activeProducts = cachedProducts.filter(p => p.is_active);

      if (activeProducts.length === 0) {
        if (errBox) {
          if (errText) errText.textContent = 'No active products available in the database. Please activate or add products first.';
          errBox.classList.remove('hidden');
        }
        if (newSelect) newSelect.innerHTML = '<option value="">No active products found</option>';
        if (editSelect) editSelect.innerHTML = '<option value="">No active products found</option>';
        return false;
      }

      // Populate Create Modal Select
      if (newSelect) {
        newSelect.innerHTML = activeProducts.map(p =>
          `<option value="${p.id}" data-price="${p.price}" data-unit="${escapeHtml(p.unit)}" data-name="${escapeHtml(p.name)}">${escapeHtml(p.name)} (₹${p.price}/${escapeHtml(p.unit)})</option>`
        ).join('');
      }

      // Populate Edit Modal Select
      if (editSelect) {
        // For editing, also include the product currently assigned to the plan even if inactive
        let selectableForEdit = [...activeProducts];
        if (selectedProductId && !selectableForEdit.some(p => p.id === selectedProductId)) {
          const inactiveAssigned = cachedProducts.find(p => p.id === selectedProductId);
          if (inactiveAssigned) selectableForEdit.push(inactiveAssigned);
        }
        editSelect.innerHTML = selectableForEdit.map(p =>
          `<option value="${p.id}" data-price="${p.price}" data-unit="${escapeHtml(p.unit)}" data-name="${escapeHtml(p.name)}" ${p.id === selectedProductId ? 'selected' : ''}>${escapeHtml(p.name)} (₹${p.price}/${escapeHtml(p.unit)})${p.is_active ? '' : ' [Disabled]'}</option>`
        ).join('');
      }

      return true;
    }

    async function openCreatePlanModal() {
      // Reset inputs first
      document.getElementById('new-plan-name').value = '';
      document.getElementById('new-plan-quantity').value = '1.0';
      document.getElementById('new-plan-unit').value = 'litre';
      document.getElementById('new-plan-frequency').value = 'daily';
      document.getElementById('new-plan-price').value = '';
      document.getElementById('new-plan-schedule').value = 'Morning Delivery (5:30 AM - 7:30 AM)';
      document.getElementById('new-plan-active').checked = true;

      const loaded = await loadProductsForPlanModal('new-plan-product');
      if (loaded) {
        onPlanProductChange();
      }

      document.getElementById('create-plan-modal').classList.remove('hidden');
    }

    function closeCreatePlanModal() {
      document.getElementById('create-plan-modal').classList.add('hidden');
      const errBox = document.getElementById('new-plan-product-error');
      if (errBox) errBox.classList.add('hidden');
    }

    function onPlanProductChange() {
      const prodSelect = document.getElementById('new-plan-product');
      if (!prodSelect || !prodSelect.selectedOptions || !prodSelect.selectedOptions[0]) return;
      const opt = prodSelect.selectedOptions[0];
      if (!opt.value) return;

      const price = opt.getAttribute('data-price') || '60';
      const unit = opt.getAttribute('data-unit') || 'litre';
      const prodName = opt.getAttribute('data-name') || opt.text.split(' (')[0];

      document.getElementById('new-plan-price').value = price;
      document.getElementById('new-plan-unit').value = unit;

      // Auto-fill a sensible plan name if empty or previously auto-generated
      const nameInput = document.getElementById('new-plan-name');
      if (!nameInput.value || nameInput.value.includes('Daily') || nameInput.value.includes('Plan')) {
        nameInput.value = `${prodName} Daily 1L Plan`;
      }
    }

    function onEditPlanProductChange() {
      const prodSelect = document.getElementById('edit-plan-product');
      if (!prodSelect || !prodSelect.selectedOptions || !prodSelect.selectedOptions[0]) return;
      const opt = prodSelect.selectedOptions[0];
      if (!opt.value) return;

      const price = opt.getAttribute('data-price');
      const unit = opt.getAttribute('data-unit');

      if (price) document.getElementById('edit-plan-price').value = price;
      if (unit) document.getElementById('edit-plan-unit').value = unit;
    }

    async function submitCreatePlan() {
      const name = document.getElementById('new-plan-name').value.trim();
      const productId = document.getElementById('new-plan-product').value;
      const quantity = document.getElementById('new-plan-quantity').value;
      const unit = document.getElementById('new-plan-unit').value.trim();
      const frequency = document.getElementById('new-plan-frequency').value;
      const price = document.getElementById('new-plan-price').value;
      const schedule = document.getElementById('new-plan-schedule').value.trim();
      const isActive = document.getElementById('new-plan-active').checked;

      if (!name || !productId || !price) {
        return showToast('Plan name, product, and price per unit are required.', true);
      }

      try {
        const res = await fetch('/api/admin/subscription-plans/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name,
            product_id: productId,
            quantity,
            unit,
            frequency,
            price_per_unit: price,
            schedule_description: schedule,
            is_active: isActive
          })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Subscription plan created successfully!');
          closeCreatePlanModal();
          loadSubscriptionPlans();
        } else {
          showToast(data.error || 'Failed to create plan', true);
        }
      } catch (err) {
        showToast('Network error while creating plan', true);
      }
    }

    async function openEditPlanModal(planId) {
      const plan = cachedSubscriptionPlans.find(p => p.id === planId);
      if (!plan) return showToast('Plan not found', true);

      document.getElementById('edit-plan-id').value = plan.id;
      document.getElementById('edit-plan-name').value = plan.name;
      document.getElementById('edit-plan-quantity').value = plan.quantity;
      document.getElementById('edit-plan-unit').value = plan.unit;
      document.getElementById('edit-plan-frequency').value = plan.frequency;
      document.getElementById('edit-plan-price').value = plan.price_per_unit;
      document.getElementById('edit-plan-schedule').value = plan.schedule_description || '';
      document.getElementById('edit-plan-active').checked = plan.is_active;

      await loadProductsForPlanModal('edit-plan-product', plan.product_id);

      document.getElementById('edit-plan-modal').classList.remove('hidden');
    }

    function closeEditPlanModal() {
      document.getElementById('edit-plan-modal').classList.add('hidden');
      const errBox = document.getElementById('edit-plan-product-error');
      if (errBox) errBox.classList.add('hidden');
    }

    async function submitUpdatePlan() {
      const planId = document.getElementById('edit-plan-id').value;
      const name = document.getElementById('edit-plan-name').value.trim();
      const productId = document.getElementById('edit-plan-product').value;
      const quantity = document.getElementById('edit-plan-quantity').value;
      const unit = document.getElementById('edit-plan-unit').value.trim();
      const frequency = document.getElementById('edit-plan-frequency').value;
      const price = document.getElementById('edit-plan-price').value;
      const schedule = document.getElementById('edit-plan-schedule').value.trim();
      const isActive = document.getElementById('edit-plan-active').checked;

      try {
        const res = await fetch('/api/admin/subscription-plans/', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id: planId,
            name,
            product_id: productId,
            quantity,
            unit,
            frequency,
            price_per_unit: price,
            schedule_description: schedule,
            is_active: isActive
          })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Plan updated successfully!');
          closeEditPlanModal();
          loadSubscriptionPlans();
        } else {
          showToast(data.error || 'Failed to update plan', true);
        }
      } catch (err) {
        showToast('Network error while updating plan', true);
      }
    }

    async function togglePlanActive(planId) {
      try {
        const res = await fetch('/api/admin/subscription-plans/', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: planId, action: 'toggle_active' })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg);
          loadSubscriptionPlans();
        } else {
          showToast(data.error || 'Failed to toggle plan status', true);
        }
      } catch (err) {
        showToast('Network error', true);
      }
    }

    async function deactivatePlanPrompt(planId, planName) {
      if (!confirm(`Are you sure you want to deactivate '${planName}'? It will no longer be visible to new customers in the app. Existing customer subscriptions and historical deliveries will be safely preserved.`)) return;
      try {
        const res = await fetch(`/api/admin/subscription-plans/`, {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: planId })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg);
          loadSubscriptionPlans();
        } else {
          showToast(data.error || 'Failed to deactivate plan', true);
        }
      } catch (err) {
        showToast('Network error', true);
      }
    }

