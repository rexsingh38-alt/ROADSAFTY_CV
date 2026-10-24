(() => {
  const API = 'http://127.0.0.1:8002/api/reports/traffic-safety';
  const token = () => sessionStorage.getItem('saferoadToken') || localStorage.getItem('saferoadToken');
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));

  function queryForReport() {
    const range = document.querySelector('#reportDate')?.selectedOptions[0]?.text || 'Last 7 days';
    const days = range === 'Today' ? 1 : range.includes('30') ? 30 : 7;
    const location = document.querySelector('#reportLocation')?.value || 'All locations';
    const risk = document.querySelector('#reportRisk')?.value || 'All risk levels';
    const params = new URLSearchParams({days: String(days)});
    if (location !== 'All locations') params.set('location', location);
    if (risk !== 'All risk levels') params.set('risk_level', risk.toUpperCase().replace(' RISK', ''));
    return `${API}?${params}`;
  }

  async function fetchReport() {
    const accessToken = token();
    if (!accessToken) throw new Error('Sign in again to create a report.');
    const response = await fetch(queryForReport(), {headers: {Authorization: `Bearer ${accessToken}`}});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Could not generate the report.');
    return data;
  }

  function csvCell(value) { return `"${String(value ?? '').replaceAll('"', '""')}"`; }
  async function exportCsv() {
    try {
      const report = await fetchReport();
      const columns = ['event_id','event_type','timestamp','object_1_type','object_1_id','object_2_type','object_2_id','ttc','risk_level','location','relative_distance','description'];
      const lines = [columns.join(','), ...report.events.map(event => columns.map(key => csvCell(event[key])).join(','))];
      const url = URL.createObjectURL(new Blob([lines.join('\r\n')], {type: 'text/csv;charset=utf-8'}));
      const link = document.createElement('a'); link.href = url; link.download = 'saferoad-incident-report.csv'; link.click();
      URL.revokeObjectURL(url);
      toast(`CSV report downloaded (${report.summary.total_incidents} incidents).`, 'fa-file-csv');
    } catch (error) { toast(error.message, 'fa-triangle-exclamation', true); }
  }

  function reportHtml(report) {
    const summary = report.summary;
    const rows = report.events.map(event => `<tr><td>${escapeHtml(event.event_type)}</td><td>${escapeHtml(new Date(event.timestamp).toLocaleString())}</td><td>${escapeHtml(event.object_1_type)} ${escapeHtml(event.object_1_id)} + ${escapeHtml(event.object_2_type)} ${escapeHtml(event.object_2_id)}</td><td>${event.ttc == null ? '—' : `${Number(event.ttc).toFixed(2)} s`}</td><td>${escapeHtml(event.risk_level)}</td><td>${escapeHtml(event.location)}</td></tr>`).join('');
    return `<!doctype html><html><head><meta charset="utf-8"><title>SafeRoad traffic safety report</title><style>body{font:14px Arial,sans-serif;color:#182432;margin:36px}h1{margin-bottom:6px;color:#174b76}p{color:#526273}.cards{display:flex;gap:12px;margin:24px 0}.card{border:1px solid #cbd5df;padding:14px;min-width:120px}.card b{display:block;font-size:24px;margin-top:8px}table{border-collapse:collapse;width:100%;font-size:12px}th,td{text-align:left;border:1px solid #cbd5df;padding:8px}th{background:#eaf1f7}@media print{body{margin:14mm}.no-print{display:none}}</style></head><body><button class="no-print" onclick="window.print()">Print / Save PDF</button><h1>SafeRoad AI — Traffic safety report</h1><p>Generated ${escapeHtml(new Date(report.generated_at).toLocaleString())} · Last ${report.period_days} days · ${escapeHtml(report.location_filter)} · ${escapeHtml(report.risk_filter)}</p><div class="cards"><div class="card">All incidents<b>${summary.total_incidents}</b></div><div class="card">Near misses<b>${summary.near_misses}</b></div><div class="card">Collisions<b>${summary.collisions}</b></div><div class="card">High-risk rate<b>${summary.high_risk_rate}%</b></div><div class="card">Average TTC<b>${summary.average_ttc_seconds == null ? '—' : `${summary.average_ttc_seconds} s`}</b></div></div><h2>Incident records</h2><table><thead><tr><th>Type</th><th>Time</th><th>Objects</th><th>TTC</th><th>Risk</th><th>Location</th></tr></thead><tbody>${rows || '<tr><td colspan="6">No incidents in this report period.</td></tr>'}</tbody></table></body></html>`;
  }

  async function openReport(print = false) {
    const reportWindow = window.open('', '_blank');
    if (!reportWindow) { toast('Allow pop-ups to open the report.', 'fa-triangle-exclamation', true); return; }
    reportWindow.document.write('<p style="font:16px Arial;padding:30px">Preparing report from the incident database…</p>');
    try {
      const report = await fetchReport();
      reportWindow.document.open(); reportWindow.document.write(reportHtml(report)); reportWindow.document.close();
      if (print) reportWindow.setTimeout(() => reportWindow.print(), 500);
    } catch (error) {
      reportWindow.close(); toast(error.message, 'fa-triangle-exclamation', true);
    }
  }

  function intercept(id, handler) {
    const button = document.getElementById(id);
    if (!button) return;
    button.addEventListener('click', event => { event.preventDefault(); event.stopImmediatePropagation(); handler(); }, true);
  }
  intercept('exportCsv', exportCsv);
  intercept('downloadPdf', () => openReport(true));
  intercept('generateReport', () => openReport(false));
  intercept('generateTop', () => openReport(false));
  intercept('modalGenerate', () => openReport(false));
})();
