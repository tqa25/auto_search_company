/* ═══════════════════════════════════════
   app.js — Core Dashboard Logic
   ═══════════════════════════════════════ */

// Store company names to resolve IDs in logs
window._companyNames = {};

// On load, fetch company names mapping
document.addEventListener("DOMContentLoaded", async () => {
    try {
        const resp = await fetch("/api/companies/names");
        if(resp.ok) window._companyNames = await resp.json();
    } catch(e) { console.error("Failed to fetch company names"); }
});

// --- Toast System ---
function showToast(message, type = 'info', duration = 5000) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
  toast.innerHTML = `
    <span>${icons[type] || 'ℹ️'}</span>
    <span>${message}</span>
    <button class="toast-close" onclick="this.parentElement.remove()">✕</button>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}


// --- Quota Widget ---
async function refreshQuota() {
  try {
    const resp = await fetch('/api/quota');
    if (!resp.ok) return;
    const data = await resp.json();

    const geminiUsed = data.gemini_grounding_used || 0;
    const geminiLimit = data.gemini_limit || 1450;
    const serperUsed = data.serper_used || 0;
    const serperLimit = 2500;

    const geminiPct = Math.min(100, (geminiUsed / geminiLimit) * 100);
    const serperPct = Math.min(100, (serperUsed / serperLimit) * 100);

    // Update text
    const gtEl = document.getElementById('geminiQuotaText');
    const stEl = document.getElementById('serperQuotaText');
    if (gtEl) gtEl.textContent = `${geminiUsed.toLocaleString()}/${geminiLimit.toLocaleString()}`;
    if (stEl) stEl.textContent = `${serperUsed.toLocaleString()}/${serperLimit.toLocaleString()}`;

    // Update fills
    const gfEl = document.getElementById('geminiQuotaFill');
    const sfEl = document.getElementById('serperQuotaFill');
    if (gfEl) {
      gfEl.style.width = geminiPct + '%';
      gfEl.className = 'quota-fill ' + (geminiPct > 90 ? 'danger' : geminiPct > 70 ? 'warn' : 'ok');
    }
    if (sfEl) {
      sfEl.style.width = serperPct + '%';
      sfEl.className = 'quota-fill ' + (serperPct > 90 ? 'danger' : serperPct > 70 ? 'warn' : 'ok');
    }

    // Alert if near limit
    if (geminiPct > 90) {
      showToast(`⚠️ Gemini quota sắp hết: ${geminiUsed}/${geminiLimit}`, 'warning');
    }
  } catch (e) {
    // Silent fail for quota refresh
  }
}


// --- WebSocket Log Stream ---
let logSocket = null;

function connectLogStream(containerId, companyFilter = null) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${location.host}/ws/logs`;

  logSocket = new WebSocket(url);

  logSocket.onopen = () => {
    container.innerHTML = '';
    appendLog(container, '● Connected to live log stream', 'log-info');
  };

  logSocket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);

      // Filter by company if needed
      if (companyFilter && data.company_id && data.company_id !== companyFilter) return;

      // Format log entry
      const time = new Date(data.timestamp).toLocaleTimeString('vi-VN');
      const step = (data.step || data.event_type || '').toUpperCase();
      const status = data.status || '';
      const companyName = window._companyNames[data.company_id] ? ` [${window._companyNames[data.company_id]}]` : '';

      let cssClass = 'log-muted';
      if (status === 'success' || status === 'SUCCESS') cssClass = 'log-success';
      else if (status === 'failed' || status === 'error') cssClass = 'log-failed';
      else if (data.event_type === 'step_start') cssClass = 'log-warning';

      let msg = `[${time}] [CMP-${String(data.company_id || 0).padStart(4, '0')}] [${step}]`;
      if (status) msg += ` [${status.toUpperCase()}]`;
      if (data.duration_ms) msg += ` ${(data.duration_ms / 1000).toFixed(1)}s`;
      if (data.credits_used) msg += ` ${data.credits_used} credits`;
      if (data.error_message) msg += ` → ${data.error_message}`;

      appendLog(container, msg, cssClass);
    } catch (e) {
      // Raw text
      appendLog(container, event.data, 'log-muted');
    }
  };

  logSocket.onclose = () => {
    appendLog(container, '● Disconnected. Reconnecting in 3s...', 'log-warning');
    setTimeout(() => connectLogStream(containerId, companyFilter), 3000);
  };

  logSocket.onerror = () => {
    appendLog(container, '● Connection error', 'log-failed');
  };
}

function appendLog(container, text, cssClass = '') {
  const entry = document.createElement('div');
  entry.className = `log-entry ${cssClass}`;
  entry.textContent = text;
  container.appendChild(entry);

  // Auto-scroll
  container.scrollTop = container.scrollHeight;

  // Keep max 500 entries
  while (container.children.length > 500) {
    container.removeChild(container.firstChild);
  }
}


// --- Modal ---
function openModal(id) {
  document.getElementById(id).classList.add('show');
}

function closeModal(id) {
  document.getElementById(id).classList.remove('show');
}


// --- Utility ---
function formatNumber(n) {
  return (n || 0).toLocaleString();
}
