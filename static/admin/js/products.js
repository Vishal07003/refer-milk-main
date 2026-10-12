    // 7. Products
cachedProducts = [];
currentProductStatusFilter = 'all';
productSearchTimeout = null;

    async function loadProducts() {
      const tbody = document.getElementById('products-table-body');
      const catFilter = document.getElementById('prod-category-filter')?.value || 'all';
      const searchVal = document.getElementById('prod-search-input')?.value.trim() || '';

      try {
        const queryParams = new URLSearchParams();
        if (catFilter !== 'all') queryParams.append('category_id', catFilter);
        if (currentProductStatusFilter !== 'all') queryParams.append('status', currentProductStatusFilter);
        if (searchVal) queryParams.append('search', searchVal);

        const res = await fetch(`/api/admin/products/?${queryParams.toString()}`);
        const data = await res.json();
        const list = data.products || [];
        cachedProducts = list;

        // Populate category filter dropdown once if needed
        const catSelect = document.getElementById('prod-category-filter');
        if (catSelect && data.categories && catSelect.options.length <= 1) {
          const currentVal = catSelect.value;
          catSelect.innerHTML = '<option value="all">All Categories</option>' +
            data.categories.map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('');
          catSelect.value = currentVal;
        }

        // Populate product select dropdown for subscriptions
        const prodSelect = document.getElementById('sub-product-select');
        if (prodSelect) {
          prodSelect.innerHTML = list.map(p => `<option value="${p.id}">${escapeHtml(p.name)} (₹${p.price}/${p.unit})</option>`).join('');
        }

        if (list.length === 0) {
          tbody.innerHTML = `<tr><td colspan="6" class="text-center py-8 text-slate-400">No products found matching current filters.</td></tr>`;
          return;
        }

        tbody.innerHTML = list.map(p => `
          <tr class="hover:bg-slate-50 transition">
            <td class="py-3 px-4 font-bold text-slate-900">${escapeHtml(p.name)}</td>
            <td class="py-3 px-4 text-slate-600">${escapeHtml(p.category)}</td>
            <td class="py-3 px-4 font-bold text-slate-900">₹${p.price.toFixed(2)} / ${p.unit}</td>
            <td class="py-3 px-4">${p.is_subscription_eligible ? '<span class="text-emerald-700 font-semibold">Yes</span>' : '<span class="text-slate-400">No</span>'}</td>
            <td class="py-3 px-4">
              <button onclick="toggleProductActive(${p.id})" class="px-2.5 py-1 rounded-full text-[11px] font-semibold transition ${p.is_active ? 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}">
                ${p.is_active ? 'Active' : 'Disabled'}
              </button>
            </td>
            <td class="py-3 px-4 text-right">
              <div class="flex items-center justify-end space-x-1.5">
                <button onclick="openEditProductModal(${p.id})" class="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:text-blue-600 hover:border-blue-400 transition" title="Edit Product">
                  <i data-lucide="edit" class="w-3.5 h-3.5"></i>
                </button>
                <button onclick="toggleProductActive(${p.id})" class="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:text-amber-700 transition" title="Archive / Toggle">
                  <i data-lucide="archive" class="w-3.5 h-3.5"></i>
                </button>
              </div>
            </td>
          </tr>
        `).join('');
        lucide.createIcons();
      } catch (e) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center py-6 text-red-500">Error loading products.</td></tr>`;
      }
    }

    function debounceProductSearch() {
      clearTimeout(productSearchTimeout);
      productSearchTimeout = setTimeout(() => {
        loadProducts();
      }, 300);
    }

    function filterProducts() {
      loadProducts();
    }

    function filterProductStatus(status) {
      currentProductStatusFilter = status;
      ['all', 'active', 'inactive'].forEach(st => {
        const btn = document.getElementById(`prod-filter-${st}`);
        if (btn) {
          if (st === status) {
            btn.className = 'px-2.5 py-1 rounded-md font-semibold bg-white text-slate-900 shadow-xs transition';
          } else {
            btn.className = 'px-2.5 py-1 rounded-md font-medium text-slate-600 hover:text-slate-900 transition';
          }
        }
      });
      loadProducts();
    }


    // Add Product Modal
    function openCreateProductModal() {
      document.getElementById('prod-name').value = '';
      document.getElementById('prod-price').value = '';
      document.getElementById('create-product-modal').classList.remove('hidden');
      lucide.createIcons();
    }

    function closeCreateProductModal() {
      document.getElementById('create-product-modal').classList.add('hidden');
    }

    async function submitCreateProduct() {
      const name = document.getElementById('prod-name').value.trim();
      const price = document.getElementById('prod-price').value.trim();
      const unit = document.getElementById('prod-unit').value;
      const category = document.getElementById('prod-category').value;
      const isSub = document.getElementById('prod-sub').checked;

      if (!name || !price) return showToast('Name and price are required', true);

      try {
        const res = await fetch('/api/admin/products/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, price, unit, category, is_subscription_eligible: isSub })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Product created!');
          closeCreateProductModal();
          refreshAllData();
        } else {
          showToast(data.error || 'Failed to create product', true);
        }
      } catch (e) {
        showToast('Network error', true);
      }
    }

    // Edit Product Modal
    function openEditProductModal(prodId) {
      const p = cachedProducts.find(item => item.id === prodId);
      if (!p) return showToast('Product not found', true);

      document.getElementById('edit-prod-id').value = p.id;
      document.getElementById('edit-prod-name').value = p.name;
      document.getElementById('edit-prod-price').value = p.price;
      const catSelect = document.getElementById('edit-prod-category');
      if (catSelect) catSelect.value = p.category;
      const unitSelect = document.getElementById('edit-prod-unit');
      if (unitSelect) unitSelect.value = p.unit;
      const statusSelect = document.getElementById('edit-prod-status');
      if (statusSelect) statusSelect.value = p.is_active ? 'true' : 'false';
      const subCheck = document.getElementById('edit-prod-sub');
      if (subCheck) subCheck.checked = !!p.is_subscription_eligible;

      document.getElementById('edit-product-modal').classList.remove('hidden');
      if (window.lucide && typeof lucide.createIcons === 'function') {
        lucide.createIcons();
      }
    }

    function closeEditProductModal() {
      const modal = document.getElementById('edit-product-modal');
      if (modal) modal.classList.add('hidden');
    }

    async function submitUpdateProduct() {
      const id = document.getElementById('edit-prod-id').value;
      const name = document.getElementById('edit-prod-name').value.trim();
      const price = document.getElementById('edit-prod-price').value.trim();
      const unit = document.getElementById('edit-prod-unit').value;
      const category = document.getElementById('edit-prod-category').value;
      const isActive = document.getElementById('edit-prod-status').value === 'true';
      const isSub = document.getElementById('edit-prod-sub').checked;

      if (!name || !price) return showToast('Name and price are required', true);

      try {
        const res = await fetch('/api/admin/products/', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id,
            action: 'update',
            name,
            price,
            unit,
            category,
            is_active: isActive,
            is_subscription_eligible: isSub
          })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Product updated!');
          closeEditProductModal();
          loadProducts();
        } else {
          showToast(data.error || 'Failed to update product', true);
        }
      } catch (e) {
        showToast('Network error updating product', true);
      }
    }

    async function toggleProductActive(prodId) {
      try {
        const res = await fetch('/api/admin/products/', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: prodId, action: 'toggle_active' })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.msg || 'Product status toggled');
          loadProducts();
        } else {
          showToast(data.error || 'Failed to toggle product', true);
        }
      } catch (err) {
        showToast('Failed to toggle product', true);
      }
    }

