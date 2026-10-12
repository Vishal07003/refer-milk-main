    // 1. Stats and Trends
    function setElementText(id, text) {
      const el = document.getElementById(id);
      if (el) el.innerText = text;
    }

    async function loadStatsAndTrends() {
      try {
        const res = await fetch('/api/admin/stats/');
        const data = await res.json();
        const p = data.cash_collections || {};
        const sys = data.system_overview || {};

        setElementText('dash-customers-count', sys.total_customers || 0);
        setElementText('dash-boys-count', sys.total_delivery_boys || 0);
        setElementText('dash-active-boys-count', sys.active_delivery_boys || 0);
        setElementText('dash-today-orders', sys.today_orders || 0);
        setElementText('dash-subs-count', sys.active_subscriptions || 0);
        setElementText('dash-today-cash', `₹${(p.today_cash || 0).toFixed(2)}`);

        // Row 2 KPIs
        setElementText('dash-total-collected', `₹${(p.total_collected || 0).toFixed(2)}`);
        setElementText('dash-confirmed-handover', `₹${(p.confirmed_handover_amount || 0).toFixed(2)}`);
        setElementText('dash-pending-handover', `₹${(p.pending_handover_amount || 0).toFixed(2)}`);
        setElementText('dash-pending-count', `${p.pending_handovers_count || 0} pending handovers`);
        setElementText('dash-discrepancy-amount', `₹${Math.abs(p.total_discrepancy_amount || 0).toFixed(2)}`);
        setElementText('dash-discrepancy-count', `${p.discrepancy_count || 0} flagged`);

        // Render Trends Chart and Order Status Breakdown Chart
        renderCharts(data.trends || [], sys.order_statuses || {});
      } catch (err) {
        console.error('Stats error:', err);
      }
    }

    function renderCharts(trends, orderStatuses) {
      const ctxLine = document.getElementById('collectionsChart');
      if (ctxLine) {
        if (collectionsChartInstance) collectionsChartInstance.destroy();
        collectionsChartInstance = new Chart(ctxLine, {
          type: 'line',
          data: {
            labels: trends.map(t => t.date),
            datasets: [
              {
                label: 'Cash Collections (₹)',
                data: trends.map(t => t.cash),
                borderColor: '#059669',
                backgroundColor: 'rgba(5, 150, 105, 0.12)',
                tension: 0.35,
                fill: true,
                pointBackgroundColor: '#059669',
                pointRadius: 4,
              }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'top' } },
            scales: { y: { beginAtZero: true } }
          }
        });
      }

      const ctxOrder = document.getElementById('orderStatusChart');
      if (ctxOrder) {
        if (donutChartInstance) donutChartInstance.destroy();
        const delivered = orderStatuses.delivered || 0;
        const outForDelivery = orderStatuses.out_for_delivery || 0;
        const confirmed = orderStatuses.confirmed || 0;
        const cancelled = orderStatuses.cancelled || 0;

        donutChartInstance = new Chart(ctxOrder, {
          type: 'doughnut',
          data: {
            labels: ['Delivered', 'Out for Delivery', 'Confirmed', 'Cancelled'],
            datasets: [{
              data: [delivered, outForDelivery, confirmed, cancelled],
              backgroundColor: ['#059669', '#2563EB', '#F59E0B', '#F43F5E'],
              borderWidth: 2,
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            cutout: '68%',
          }
        });
      }
    }

