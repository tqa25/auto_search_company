/* ═══════════════════════════════════════
   runner.js — Process Runner Logic
   ═══════════════════════════════════════ */

let currentMode = 'manual';
let isRunning = false;
let lastStepResult = null;

// --- Mode Toggle ---
function setMode(mode) {
  currentMode = mode;
  document.getElementById('stepsPanel').classList.toggle('hidden', mode !== 'manual');
  document.getElementById('autoPanel').classList.toggle('hidden', mode !== 'auto');
}


// --- Manual Step Execution ---
async function runStep(stepName) {
  const select = document.getElementById('companySelect');
  const companyId = select.value;

  if (!companyId) {
    showToast('Please select a company first', 'warning');
    return;
  }

  const companyName = select.options[select.selectedIndex].dataset.name;

  // UI: Mark step as running
  resetStepCards();
  const stepCard = getStepCard(stepName);
  if (stepCard) stepCard.classList.add('running');

  // Log
  const logContainer = document.getElementById('runnerLogContainer');
  const startTime = new Date();
  appendLog(logContainer, `[${startTime.toLocaleTimeString()}] ▶ Starting ${stepName} for "${companyName}" (ID: ${companyId})`, 'log-info');

  try {
    const resp = await fetch('/api/runner/step', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ company_id: parseInt(companyId), step: stepName })
    });

    const result = await resp.json();
    const endTime = new Date();
    const duration = ((endTime - startTime) / 1000).toFixed(1);

    lastStepResult = result;

    if (resp.ok && result.status !== 'error') {
      // Success
      if (stepCard) { stepCard.classList.remove('running'); stepCard.classList.add('done'); }
      appendLog(logContainer, `[${endTime.toLocaleTimeString()}] ✅ ${stepName} completed in ${duration}s`, 'log-success');

      // Show result card
      showStepResult(stepName, result, duration);

      // Specific log details
      if (result.phone) appendLog(logContainer, `   📞 Phone: ${result.phone}`, 'log-success');
      if (result.confidence) appendLog(logContainer, `   🎯 Confidence: ${result.confidence}`, 'log-info');
      if (result.urls_found !== undefined) appendLog(logContainer, `   🔗 URLs found: ${result.urls_found}`, 'log-info');
      if (result.tokens_used) appendLog(logContainer, `   🪙 Tokens: in=${result.tokens_used.input || 0} out=${result.tokens_used.output || 0}`, 'log-muted');
    } else {
      // Error
      if (stepCard) { stepCard.classList.remove('running'); }
      appendLog(logContainer, `[${endTime.toLocaleTimeString()}] ❌ ${stepName} failed: ${result.error || result.message || 'Unknown error'}`, 'log-failed');
      showToast(`Step failed: ${result.error || 'Unknown error'}`, 'error');
    }
  } catch (err) {
    if (stepCard) stepCard.classList.remove('running');
    appendLog(logContainer, `❌ Network error: ${err.message}`, 'log-failed');
    showToast('Network error: ' + err.message, 'error');
  }

  // Refresh quota
  refreshQuota();
}


function showStepResult(stepName, result, duration) {
  const card = document.getElementById('stepResultCard');
  card.style.display = '';

  document.getElementById('stepResultTitle').textContent = `${stepName} Result`;
  document.getElementById('stepDuration').textContent = `${duration}s`;

  // Metrics
  const metrics = document.getElementById('stepMetrics');
  const metricItems = [];

  if (result.confidence !== undefined) metricItems.push({ label: 'Confidence', value: result.confidence, color: 'var(--accent)' });
  if (result.phone) metricItems.push({ label: 'Phone', value: '✓', color: 'var(--success)' });
  if (result.tokens_used) {
    metricItems.push({ label: 'Tokens In', value: (result.tokens_used.input || 0).toLocaleString() });
    metricItems.push({ label: 'Tokens Out', value: (result.tokens_used.output || 0).toLocaleString() });
  }
  if (result.urls_found !== undefined) metricItems.push({ label: 'URLs', value: result.urls_found });
  if (result.credits_used !== undefined) metricItems.push({ label: 'Credits', value: result.credits_used });

  metrics.innerHTML = metricItems.map(m => `
    <div class="stat-card">
      <div class="stat-value" style="font-size:18px;${m.color ? 'color:' + m.color : ''}">${m.value}</div>
      <div class="stat-label">${m.label}</div>
    </div>
  `).join('');

  // JSON viewer
  document.getElementById('stepJsonViewer').textContent = JSON.stringify(result, null, 2);
}


function copyStepResult() {
  if (!lastStepResult) return;
  navigator.clipboard.writeText(JSON.stringify(lastStepResult, null, 2));
  showToast('JSON copied to clipboard', 'info');
}


// --- Auto Mode ---
async function startAuto() {
  const select = document.getElementById('companySelect');
  const companyId = select.value;

  if (!companyId) {
    showToast('Please select a company first', 'warning');
    return;
  }

  isRunning = true;
  document.getElementById('startBtn').disabled = true;
  document.getElementById('stopBtn').disabled = false;

  const logContainer = document.getElementById('runnerLogContainer');
  appendLog(logContainer, `\n━━━ AUTO MODE STARTED ━━━`, 'log-info');

  const steps = ['gemini_quick', 'google_maps', 'serper_search', 'scrape', 'ai_extract'];

  for (const step of steps) {
    if (!isRunning) {
      appendLog(logContainer, `⏹ Auto mode stopped by user`, 'log-warning');
      break;
    }
    await runStep(step);
  }

  isRunning = false;
  document.getElementById('startBtn').disabled = false;
  document.getElementById('stopBtn').disabled = true;
  appendLog(logContainer, `━━━ AUTO MODE FINISHED ━━━\n`, 'log-info');
}


function stopAuto() {
  isRunning = false;
  showToast('Stopping after current step completes...', 'warning');
}


// --- Log Export ---
function exportLog(format) {
  const companyId = document.getElementById('companySelect')?.value;
  let url = `/api/export/logs?format=${format}`;
  if (companyId) url += `&company_id=${companyId}`;
  window.open(url, '_blank');
}


// --- Helpers ---
function getStepCard(stepName) {
  const map = {
    'gemini_quick': 'step-gemini',
    'google_maps': 'step-maps',
    'serper_search': 'step-search',
    'scrape': 'step-scrape',
    'ai_extract': 'step-extract',
    'facebook': 'step-facebook'
  };
  return document.getElementById(map[stepName]);
}

function resetStepCards() {
  document.querySelectorAll('.step-card').forEach(c => {
    c.classList.remove('running', 'done', 'active');
  });
}

function clearRunnerLog() {
  const c = document.getElementById('runnerLogContainer');
  if (c) c.innerHTML = '<div class="text-muted" style="text-align:center;padding:40px">Log cleared.</div>';
}

// --- Init: auto-select from URL param ---
document.addEventListener('DOMContentLoaded', () => {
  const params = new URLSearchParams(window.location.search);
  const companyId = params.get('company');
  if (companyId) {
    const select = document.getElementById('companySelect');
    if (select) select.value = companyId;
  }
});
