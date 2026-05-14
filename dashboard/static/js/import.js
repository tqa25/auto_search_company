/* ═══════════════════════════════════════
   import.js — File Import & Preview
   ═══════════════════════════════════════ */

let pendingImportData = [];

document.addEventListener('DOMContentLoaded', () => {
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  if (!dropZone || !fileInput) return;

  // Click to select
  dropZone.addEventListener('click', () => fileInput.click());

  // Drag events
  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
  });

  dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('drag-over');
  });

  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) processFile(file);
  });

  // File input change
  fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) processFile(file);
  });
});


function processFile(file) {
  const ext = file.name.split('.').pop().toLowerCase();

  if (ext === 'xlsx' || ext === 'xls') {
    processExcel(file);
  } else if (ext === 'csv') {
    processCSV(file);
  } else if (ext === 'txt') {
    processTXT(file);
  } else {
    showToast('Unsupported file type. Use .xlsx, .csv, or .txt', 'error');
  }
}


function processExcel(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const workbook = XLSX.read(e.target.result, { type: 'array' });
      const sheet = workbook.Sheets[workbook.SheetNames[0]];
      const rows = XLSX.utils.sheet_to_json(sheet, { header: 1 });

      // Find the column with company names
      // Strategy: look for a column header containing "name" or "company", or use first column
      const header = rows[0] || [];
      let nameCol = 0;
      for (let i = 0; i < header.length; i++) {
        const h = String(header[i]).toLowerCase();
        if (h.includes('name') || h.includes('company') || h.includes('tên') || h.includes('công ty')) {
          nameCol = i;
          break;
        }
      }

      const names = [];
      for (let i = 1; i < rows.length; i++) {
        const val = rows[i] && rows[i][nameCol];
        if (val && String(val).trim()) {
          names.push(String(val).trim());
        }
      }

      showImportPreview(names, file.name);
    } catch (err) {
      showToast('Error parsing Excel: ' + err.message, 'error');
    }
  };
  reader.readAsArrayBuffer(file);
}


function processCSV(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    const text = e.target.result;
    const lines = text.split('\n').filter(l => l.trim());

    // Skip header if it looks like a header
    const start = (lines[0] && /name|company|tên|công ty/i.test(lines[0])) ? 1 : 0;

    const names = [];
    for (let i = start; i < lines.length; i++) {
      // Take first column if comma-separated
      const parts = lines[i].split(',');
      const name = parts[0].replace(/^["']|["']$/g, '').trim();
      if (name) names.push(name);
    }

    showImportPreview(names, file.name);
  };
  reader.readAsText(file);
}


function processTXT(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    const text = e.target.result;
    const names = text.split('\n')
      .map(l => l.trim())
      .filter(l => l && l.length > 1);

    showImportPreview(names, file.name);
  };
  reader.readAsText(file);
}


function showImportPreview(names, fileName) {
  if (!names.length) {
    showToast('No company names found in file', 'warning');
    return;
  }

  pendingImportData = names;

  // Build preview table
  const preview = names.slice(0, 20).map((n, i) =>
    `<tr><td class="text-muted">${i + 1}</td><td>${n}</td></tr>`
  ).join('');

  const moreNote = names.length > 20 ? `<tr><td colspan="2" class="text-muted">... and ${names.length - 20} more</td></tr>` : '';

  document.getElementById('importPreviewContent').innerHTML = `
    <p class="text-muted mb-1" style="font-size:13px">File: <strong>${fileName}</strong></p>
    <div style="max-height:300px;overflow-y:auto">
      <table class="data-table">
        <thead><tr><th>#</th><th>Company Name</th></tr></thead>
        <tbody>${preview}${moreNote}</tbody>
      </table>
    </div>
  `;

  document.getElementById('importCount').textContent = `${names.length} companies`;
  openModal('importModal');
}


async function confirmImport() {
  if (!pendingImportData.length) return;

  const btn = document.getElementById('importConfirmBtn');
  btn.disabled = true;
  btn.textContent = 'Importing...';

  try {
    const resp = await fetch('/api/companies/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ names: pendingImportData })
    });

    const result = await resp.json();

    if (resp.ok) {
      showToast(`✅ Imported ${result.imported} companies (${result.skipped} duplicates skipped)`, 'success');
      closeModal('importModal');
      setTimeout(() => location.reload(), 1000);
    } else {
      showToast('Import failed: ' + (result.error || 'Unknown error'), 'error');
    }
  } catch (err) {
    showToast('Import error: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Import';
  }
}
