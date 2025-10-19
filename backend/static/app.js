const state = { token: null, perfData: null, perfChart: null };

function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }
function show(sel) { 
  const els = typeof sel === 'string' ? $$(sel) : [sel];
  els.forEach(el => el && el.classList.remove('hidden')); 
}
function hide(sel) { 
  const els = typeof sel === 'string' ? $$(sel) : [sel];
  els.forEach(el => el && el.classList.add('hidden')); 
}

async function api(path, options={}) {
  options.headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
  if (state.token) options.headers['Authorization'] = 'Bearer ' + state.token;
  const res = await fetch('/api' + path, options);
  if (res.status === 401) throw new Error('Unauthorized');
  if ((options.method||'GET') === 'GET' && !res.headers.get('content-type')?.includes('application/json')) {
    return res; // for file downloads
  }
  const data = await res.json();
  if (!res.ok) throw new Error(data.error||'Request failed');
  return data;
}

async function login() {
  const username = $('#username').value.trim();
  const password = $('#password').value.trim();
  try {
    const res = await api('/login', { method: 'POST', body: JSON.stringify({ username, password }) });
    state.token = res.token;
    localStorage.setItem('token', state.token);
    await loadDashboard();
  } catch (e) { $('#login-error').textContent = e.message; }
}

function logout() {
  if (!state.token) return;
  api('/logout', { method: 'POST' }).catch(()=>{});
  state.token = null;
  localStorage.removeItem('token');
  hide('#dashboard');
  show('#login-view');
}

async function loadDashboard() {
  hide('#login-view');
  show('#dashboard');
  await Promise.all([refreshLive(), refreshPerf(), refreshAI(), refreshAccount(), fetchAllLicenses()]);
}

async function refreshLive() {
  try {
    const data = await api('/trade_data/live');
    const tbody = $('#live-trades tbody');
    tbody.innerHTML = '';
    data.trades.forEach(t => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${t.pair}</td><td>${t.lots}</td><td>${t.direction}</td><td>${Math.round(t.ai_confidence*100)}%</td>`;
      tbody.appendChild(tr);
    });
  } catch (e) { /* ignore */ }
}

async function refreshPerf() {
  try {
    const data = await api('/performance');
    state.perfData = data.performance; // Store for chart updates
    
    // Populate pair selector
    const selector = $('#perf-pair-select');
    selector.innerHTML = '<option value="">-- All Pairs --</option>';
    data.performance.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.pair;
      opt.textContent = p.pair;
      selector.appendChild(opt);
    });
    
    // Populate table
    const tbody = $('#perf tbody');
    tbody.innerHTML = '';
    data.performance.forEach(p => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${p.pair}</td><td>${Math.round(p.win_rate*100)}%</td><td>${Math.round(p.drawdown*100)}%</td><td>${p.trades}</td>`;
      tbody.appendChild(tr);
    });
    
    // Render chart with all data initially
    renderPerfChart(data.performance);
  } catch (e) { console.error('Failed to load performance:', e); }
}

function renderPerfChart(perfData) {
  const canvas = $('#perf-chart');
  if (!canvas) return;
  
  const ctx = canvas.getContext('2d');
  
  // Destroy existing chart if any
  if (state.perfChart) {
    state.perfChart.destroy();
  }
  
  // Prepare data
  const labels = perfData.map(p => p.pair);
  const winRates = perfData.map(p => p.win_rate * 100);
  const drawdowns = perfData.map(p => p.drawdown * 100);
  const trades = perfData.map(p => p.trades);
  
  // Create chart
  state.perfChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Win Rate (%)',
          data: winRates,
          backgroundColor: 'rgba(76, 175, 80, 0.7)',
          borderColor: 'rgba(76, 175, 80, 1)',
          borderWidth: 1
        },
        {
          label: 'Drawdown (%)',
          data: drawdowns,
          backgroundColor: 'rgba(255, 152, 0, 0.7)',
          borderColor: 'rgba(255, 152, 0, 1)',
          borderWidth: 1
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
          ticks: { color: '#bdbdbd' },
          grid: { color: 'rgba(255,255,255,0.1)' }
        },
        x: {
          ticks: { color: '#bdbdbd' },
          grid: { color: 'rgba(255,255,255,0.1)' }
        }
      },
      plugins: {
        legend: {
          labels: { color: '#f2f2f2' }
        },
        tooltip: {
          callbacks: {
            afterLabel: function(context) {
              const index = context.dataIndex;
              return `Trades: ${trades[index]}`;
            }
          }
        }
      }
    }
  });
}

function onPerfPairChange() {
  const selectedPair = $('#perf-pair-select').value;
  if (!state.perfData) return;
  
  if (selectedPair) {
    // Filter to selected pair
    const filtered = state.perfData.filter(p => p.pair === selectedPair);
    renderPerfChart(filtered);
  } else {
    // Show all pairs
    renderPerfChart(state.perfData);
  }
}

async function refreshAI() {
  const insights = [
    'EURUSD momentum strengthening near support.',
    'GBPUSD shows divergence; consider reduced risk.',
    'USDJPY range-bound; wait for breakout confirmation.'
  ];
  const ul = $('#ai-insights');
  ul.innerHTML = '';
  insights.forEach(i => { const li = document.createElement('li'); li.textContent = i; ul.appendChild(li); });
}

async function refreshAccount() {
  // No direct endpoint; approximate by reading performance and live to display dummy values
  $('#balance').textContent = '$10,000';
  $('#equity').textContent = '$10,250';
  $('#win-rate').textContent = '60%';
}

// Dynamic license form handler
function updateLicenseForm() {
  const action = $('#license-action').value;
  const container = $('#license-form-container');
  const keyField = $('.field-license-key');
  const nameField = $('.field-license-name');
  const daysField = $('.field-license-days');
  const submitBtn = $('#btn-license-submit');
  
  if (!action) {
    hide('#license-form-container');
    hide('#license-result');
    return;
  }
  
  show('#license-form-container');
  hide('#license-result');
  
  // Hide all fields first
  hide('.field-license-key');
  hide('.field-license-name');
  hide('.field-license-days');

  // Determine which fields to show
  if (action === 'activate') {
    show('.field-license-key');
    show('.field-license-name');
    show('.field-license-days');
    if (submitBtn) submitBtn.textContent = 'Activate';
  } else if (action === 'deactivate') {
    show('.field-license-key');
    if (submitBtn) submitBtn.textContent = 'Deactivate';
  } else if (action === 'renew') {
    show('.field-license-key');
    show('.field-license-days');
    if (submitBtn) submitBtn.textContent = 'Renew';
  } else if (action === 'status') {
    show('.field-license-key');
    if (submitBtn) submitBtn.textContent = 'Check Status';
  }
}

async function submitLicenseAction() {
  const action = $('#license-action').value;
  const key = $('#license-key').value.trim();
  const name = $('#license-name').value.trim() || 'Unknown';
  const days = parseInt($('#license-days').value || '30', 10);
  
  if (!key) {
    displayLicenseResult({ error: 'License key is required' }, true);
    return;
  }
  
  try {
    let res;
    if (action === 'status') {
      res = await api(`/license/status?key=${encodeURIComponent(key)}`);
    } else if (action === 'activate') {
      res = await api('/license/activate', { method: 'POST', body: JSON.stringify({ key, name, days }) });
    } else if (action === 'deactivate') {
      res = await api('/license/deactivate', { method: 'POST', body: JSON.stringify({ key }) });
    } else if (action === 'renew') {
      res = await api('/license/renew', { method: 'POST', body: JSON.stringify({ key, days }) });
    }
    displayLicenseResult(res, false);
    await fetchAllLicenses(); // Refresh the license list
  } catch (e) {
    displayLicenseResult({ error: e.message }, true);
  }
}

function displayLicenseResult(data, isError) {
  const resultDiv = $('#license-result');
  show('#license-result');
  
  if (isError || data.error) {
    resultDiv.className = 'license-result error-result';
    resultDiv.innerHTML = `<strong>Error:</strong> ${data.error || 'Unknown error'}`;
    return;
  }
  
  resultDiv.className = 'license-result success-result';
  let html = '<div class="result-card">';
  
  if (data.key) html += `<div class="result-item"><span class="result-label">License Key:</span> <span class="result-value">${data.key}</span></div>`;
  if (data.name) html += `<div class="result-item"><span class="result-label">Name:</span> <span class="result-value">${data.name}</span></div>`;
  if (data.status) {
    const statusClass = data.status === 'active' ? 'status-active' : 'status-inactive';
    html += `<div class="result-item"><span class="result-label">Status:</span> <span class="result-value ${statusClass}">${data.status.toUpperCase()}</span></div>`;
  }
  if (data.expires_at) {
    const date = new Date(data.expires_at).toLocaleDateString();
    html += `<div class="result-item"><span class="result-label">Expires At:</span> <span class="result-value">${date}</span></div>`;
  }
  
  html += '</div>';
  resultDiv.innerHTML = html;
}

async function fetchAllLicenses() {
  try {
    const licenses = await api('/license/all');
    const tbody = $('#licenses-table tbody');
    tbody.innerHTML = '';
    
    if (licenses.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align: center;">No licenses found</td></tr>';
      return;
    }
    
    licenses.forEach(lic => {
      const tr = document.createElement('tr');
      const statusClass = lic.status === 'active' ? 'status-active' : 'status-inactive';
      const expiryDate = lic.expires_at ? new Date(lic.expires_at).toLocaleDateString() : 'N/A';
      tr.innerHTML = `
        <td>${lic.name || 'Unknown'}</td>
        <td>${lic.key}</td>
        <td>${expiryDate}</td>
        <td><span class="${statusClass}">${lic.status.toUpperCase()}</span></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error('Failed to fetch licenses:', e);
  }
}

function dl(url) {
  fetch('/api' + url, { headers: { 'Authorization': 'Bearer ' + state.token } })
    .then(r => r.blob())
    .then(b => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(b);
      a.download = url.includes('pdf') ? 'statement.pdf' : 'statement.xlsx';
      a.click();
      URL.revokeObjectURL(a.href);
    });
}

window.addEventListener('DOMContentLoaded', () => {
  $('#login-btn').addEventListener('click', login);
  $('#logout-btn').addEventListener('click', logout);
  $('#export-pdf').addEventListener('click', () => dl('/export/pdf'));
  $('#export-xls').addEventListener('click', () => dl('/export/xls'));
  
  // License control event listeners
  $('#license-action').addEventListener('change', updateLicenseForm);
  $('#btn-license-submit').addEventListener('click', submitLicenseAction);
  
  // Performance pair selector
  $('#perf-pair-select').addEventListener('change', onPerfPairChange);

  // restore token
  const t = localStorage.getItem('token');
  if (t) { state.token = t; loadDashboard().catch(()=>logout()); }
});
