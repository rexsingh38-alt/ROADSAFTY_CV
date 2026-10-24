(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

  function render(solution, elementId = 'aiSolutionPanel') {
    const panel = document.getElementById(elementId);
    if (!panel || !solution) return;
    panel.hidden = false;
    panel.dataset.priority = String(solution.priority || 'LOW').toLowerCase();
    const factors = solution.possible_contributing_factors || [];
    const actions = solution.recommended_actions || [];
    const events = solution.event_solutions || [];
    panel.innerHTML = `
      <div class="solution-head"><div><span class="solution-kicker">VIDEO-SPECIFIC SAFETY GUIDANCE</span><h2>AI Safety Solution</h2><p>${esc(solution.video_name || 'Analyzed video')} · ${esc(solution.location || 'Location not specified')}</p></div><span class="solution-priority">${esc(solution.priority || 'LOW')} PRIORITY</span></div>
      <div class="solution-stats"><div><strong>${Number(solution.total_events || 0)}</strong><span>Events</span></div><div><strong>${Number(solution.near_misses || 0)}</strong><span>Near misses</span></div><div><strong>${Number(solution.collisions || 0)}</strong><span>Accidents</span></div><div><strong>${esc(solution.risk_level || 'LOW')}</strong><span>Risk level</span></div></div>
      <div class="solution-columns"><section><h3>Possible contributing factors</h3><ul>${factors.map(item => `<li>${esc(item)}</li>`).join('') || '<li>No factors identified.</li>'}</ul></section><section><h3>Recommended authority actions</h3><ul>${actions.map(item => `<li>${esc(item)}</li>`).join('') || '<li>Continue monitoring and review the footage.</li>'}</ul></section></div>
      ${events.length ? `<details class="solution-event-details"><summary>Show recommendations by detected event (${events.length})</summary><div>${events.map(item => `<article><strong>${esc(item.event_type.replaceAll('_',' '))} · ${esc(item.priority)} · ${esc(item.objects.join(' + ') || 'Road user')}</strong><small>Video time ${Number(item.start_time_seconds || 0).toFixed(2)}–${Number(item.end_time_seconds || item.start_time_seconds || 0).toFixed(2)} s · ${esc(item.detector_pattern)}</small><ul>${item.recommended_actions.map(action => `<li>${esc(action)}</li>`).join('')}</ul></article>`).join('')}</div></details>` : ''}
      <div class="solution-foot"><span>${esc(solution.note || 'Recommendations are decision support and do not establish the actual cause.')}</span><button type="button" class="solution-report-button" data-solution-report>Generate Authority Report</button></div>`;
    panel.querySelector('[data-solution-report]').addEventListener('click', () => openReport(solution));
  }

  function openReport(solution) {
    const report = window.open('', '_blank');
    if (!report) { window.alert('Allow pop-ups to open the authority report.'); return; }
    const list = values => (values || []).map(value => `<li>${esc(value)}</li>`).join('') || '<li>None recorded</li>';
    report.document.open();
    report.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>SafeRoad Authority Action Plan</title><style>body{font:15px Arial;color:#172434;max-width:900px;margin:35px auto;padding:0 22px}h1,h2{color:#174b76}section{border:1px solid #d5dee7;padding:16px;margin:16px 0;border-radius:8px}.badge{color:#9b2020;font-weight:bold}li{margin:8px 0}.note{color:#586879;font-size:13px}button{padding:9px 14px}@media print{button{display:none}body{margin:12mm}}</style></head><body><button onclick="window.print()">Print / Save as PDF</button><h1>SafeRoad AI — Authority Action Plan</h1><p>${esc(solution.video_name)} · ${esc(solution.location)}</p><p class="badge">${esc(solution.priority)} PRIORITY · ${esc(solution.risk_level)} RISK</p><p>Events: ${Number(solution.total_events||0)} · Near misses: ${Number(solution.near_misses||0)} · Collisions: ${Number(solution.collisions||0)}</p><section><h2>Possible contributing factors</h2><ul>${list(solution.possible_contributing_factors)}</ul></section><section><h2>Recommended authority actions</h2><ul>${list(solution.recommended_actions)}</ul></section><p class="note">${esc(solution.note || 'These recommendations are decision support, not a confirmed cause or legal finding.')}</p></body></html>`);
    report.document.close();
  }

  window.renderSafetySolution = render;

  const accessToken = sessionStorage.getItem('saferoadToken') || localStorage.getItem('saferoadToken');
  if (accessToken) {
    fetch('http://127.0.0.1:8002/api/pretrained/solutions/latest?limit=1', {
      headers: {Authorization: `Bearer ${accessToken}`}
    }).then(response => response.ok ? response.json() : [])
      .then(records => { if (records[0]) render(records[0]); })
      .catch(() => {});
  }
})();
