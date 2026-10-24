// Connect the static dashboard to the local FastAPI backend.
const API_BASE = 'http://127.0.0.1:8002/api';

async function apiGet(path) {
  const token = sessionStorage.getItem('saferoadToken') || localStorage.getItem('saferoadToken');
  const response = await fetch(`${API_BASE}${path}`, {headers: token ? {Authorization: `Bearer ${token}`} : {}});
  if (response.status === 401) {
    sessionStorage.removeItem('saferoadUser'); sessionStorage.removeItem('saferoadToken');
    localStorage.removeItem('saferoadUser'); localStorage.removeItem('saferoadToken');
    location.replace('login.html');
    throw new Error('Officer session expired. Please sign in again.');
  }
  if (!response.ok) throw new Error(`API request failed (${response.status})`);
  return response.json();
}

function objectLabel(type, id) {
  const labels = {car: 'Car', motorcycle: 'Bike', bus: 'Bus', truck: 'Truck', person: 'Pedestrian'};
  const label = labels[String(type || '').toLowerCase()] || String(type || 'Object');
  const number = String(id || '').match(/(\d+)$/)?.[1] || id;
  return `${label} #${number}`;
}

function updateDashboard(data) {
  const values = document.querySelectorAll('.stats-grid .stat-value');
  if (values[0]) values[0].textContent = Number(data.vehicles_tracked || 0).toLocaleString('en-IN');
  if (values[1]) values[1].textContent = Number(data.near_miss_events || 0).toLocaleString('en-IN');
  if (values[2]) values[2].textContent = String(data.collision_events || 0).padStart(2, '0');
  const totalEvents = Number(data.near_miss_events || 0) + Number(data.collision_events || 0);
  const riskRate = totalEvents ? Number(data.high_risk_events || 0) * 100 / totalEvents : 0;
  if (values[3]) values[3].textContent = `${riskRate.toFixed(1)}%`;
  const highRiskCount = document.querySelector('#highRiskCount');
  if (highRiskCount) highRiskCount.textContent = `${data.high_risk_events || 0} high-risk incidents`;
  document.querySelector('#processingMode').textContent = data.monitoring_status || 'READY';
  const status = document.querySelector('#apiStatus');
  status.textContent = 'API ONLINE';
  status.classList.add('api-online');
}

function updateEventRows(rows) {
  events = rows.map(row => {
    const parsedDate = new Date(row.timestamp);
    return {
      id: `${row.event_type === 'COLLISION' ? 'AC' : 'NM'}-${String(row.event_id).split('-')[0].slice(0, 6).toUpperCase()}`,
      type: row.event_type === 'COLLISION' ? 'Collision' : 'Near miss',
      time: Number.isNaN(parsedDate.valueOf()) ? '—' : new Intl.DateTimeFormat('en-IN', {hour: '2-digit', minute: '2-digit'}).format(parsedDate),
      a: objectLabel(row.object_1_type, row.object_1_id),
      b: objectLabel(row.object_2_type, row.object_2_id),
      ttc: row.ttc == null ? '—' : `${Number(row.ttc).toFixed(1)}s`,
      risk: String(row.risk_level || 'LOW').toUpperCase(),
      location: row.location || 'Unknown',
      status: row.event_type === 'COLLISION' ? 'Accident' : 'Near miss'
    };
  });
  renderEvents();
  const count = document.querySelector('.events-panel .count-pill');
  if (count) count.textContent = rows.length;
  updateConflictPanel(rows[0]);
}

function updateConflictPanel(event) {
  const panel = document.querySelector('.conflict-panel');
  if (!panel) return;
  const title = panel.querySelector('.panel-header h2');
  const badge = panel.querySelector('.risk-badge');
  const summary = panel.querySelectorAll('.conflict-summary strong');
  const alertTitle = panel.querySelector('.conflict-alert strong');
  const alertText = panel.querySelector('.conflict-alert span:last-child');
  const objectTags = panel.querySelectorAll('.object-tag');
  const trajectory = panel.querySelector('.trajectory');
  const trajectoryPaths = panel.querySelectorAll('.trajectory-svg path');
  const conflictPoint = panel.querySelectorAll('.trajectory-svg circle');
  if (!event) {
    if (title) title.textContent = 'No stored trajectory events';
    if (badge) { badge.textContent = 'NO EVENTS'; badge.className = 'risk-badge low'; }
    if (trajectory) trajectory.dataset.eventState = 'empty';
    objectTags.forEach(tag => { tag.hidden = true; });
    trajectoryPaths.forEach(path => { path.style.opacity = '.12'; });
    conflictPoint.forEach(point => { point.style.opacity = '.12'; });
    if (summary[0]) summary[0].textContent = 'Waiting for video';
    if (summary[1]) summary[1].textContent = '—';
    if (summary[2]) summary[2].textContent = '—';
    if (alertTitle) alertTitle.textContent = 'Waiting for analyzed video';
    if (alertText) alertText.textContent = 'Completed near misses and collisions will appear here.';
    return;
  }
  const collision = event.event_type === 'COLLISION';
  const risk = String(event.risk_level || 'LOW').toUpperCase();
  if (title) title.textContent = collision ? 'Recorded collision' : 'Recorded near miss';
  if (badge) { badge.textContent = `${risk} RISK`; badge.className = `risk-badge ${risk.toLowerCase()}`; }
  if (trajectory) trajectory.dataset.eventState = event.event_type.toLowerCase();
  trajectoryPaths.forEach((path, index) => {
    path.style.opacity = '1';
    path.style.strokeWidth = collision ? '3' : '2';
    if (index === 0) path.style.stroke = collision || risk === 'HIGH' ? '#ff625f' : '#56a8ff';
  });
  conflictPoint.forEach(point => {
    point.style.opacity = '1';
    if (point.hasAttribute('stroke')) point.setAttribute('stroke', collision || risk === 'HIGH' ? '#ff625f' : '#f3b84b');
    else point.setAttribute('fill', collision || risk === 'HIGH' ? '#ff625f' : '#f3b84b');
  });
  if (summary[0]) summary[0].textContent = event.location || 'Unknown';
  if (summary[1]) summary[1].textContent = event.ttc == null ? '—' : `${Number(event.ttc).toFixed(2)} sec`;
  if (summary[2]) summary[2].textContent = event.relative_distance == null ? '—' : `${Number(event.relative_distance).toFixed(1)} px`;
  if (alertTitle) alertTitle.textContent = collision ? 'Collision record saved' : 'Near-miss record saved';
  if (alertText) alertText.textContent = event.description || `${event.object_1_type} and ${event.object_2_type} interaction.`;
  if (objectTags[0]) { objectTags[0].hidden = false; objectTags[0].textContent = `${String(event.object_1_type).toUpperCase()} · ${event.object_1_id}`; }
  if (objectTags[1]) { objectTags[1].hidden = false; objectTags[1].textContent = `${String(event.object_2_type).toUpperCase()} · ${event.object_2_id}`; }
  if (objectTags[2]) objectTags[2].hidden = true;
  const conflictTag = panel.querySelector('.conflict-tag');
  if (conflictTag) conflictTag.innerHTML = `<i class="fa-solid fa-burst"></i> ${collision ? 'COLLISION POINT' : 'NEAR-MISS POINT'}`;
}

function updateHotspots(rows) {
  hotspots = rows.map(row => ({
    name: row.location,
    count: row.total_events || 0,
    ttc: row.average_ttc == null ? '—' : `${Number(row.average_ttc).toFixed(1)}s`,
    risk: String(row.risk_level || 'LOW').toLowerCase(),
    coords: row.latitude != null && row.longitude != null ? [row.latitude, row.longitude] : null
  }));
  renderHotspots();
  if (!map) return;
  markers.forEach(marker => map.removeLayer(marker));
  markers = [];
  hotspots.forEach((hotspot, index) => {
    if (!hotspot.coords) return;
    const icon = L.divIcon({className: 'custom-marker', html: `<div class="marker-core ${hotspot.risk}"></div>`, iconSize: [22, 22], iconAnchor: [11, 11]});
    const popup = `<div class="popup-title">${hotspot.name}</div><div>Near-miss count: <strong>${hotspot.count}</strong></div><div>Average TTC: <strong>${hotspot.ttc}</strong></div><div>Risk level: <strong class="popup-risk ${hotspot.risk}">${hotspot.risk.toUpperCase()}</strong></div>`;
    const marker = L.marker(hotspot.coords, {icon}).addTo(map).bindPopup(popup);
    markers.push(marker);
    marker.on('click', () => document.querySelectorAll('.hotspot-entry').forEach((entry, i) => entry.classList.toggle('selected', i === index)));
  });
}

function updateAnalytics(data, eventRows = []) {
  const riskCounts = [data.high_risk_events || 0, data.medium_risk_events || 0, data.low_risk_events || 0];
  const total = data.total_near_miss_events || riskCounts.reduce((sum, count) => sum + count, 0);
  const riskChart = window.Chart && Chart.getChart(document.querySelector('#riskChart'));
  if (riskChart) {
    riskChart.data.datasets[0].data = riskCounts;
    riskChart.update('none');
  }
  document.querySelector('.donut-center strong').textContent = total;
  document.querySelectorAll('.donut-legend > div strong').forEach((element, index) => {
    const percent = total ? (riskCounts[index] / total * 100).toFixed(1) : '0.0';
    element.innerHTML = `${riskCounts[index]} <small>${percent}%</small>`;
  });
  const average = document.querySelector('.ttc-summary > div:first-child strong');
  if (average) average.innerHTML = data.average_ttc == null ? '— <small>sec</small>' : `${Number(data.average_ttc).toFixed(2)} <small>sec</small>`;
  const highRisk = document.querySelector('.ttc-summary > div:last-child strong');
  if (highRisk) highRisk.innerHTML = `${data.high_risk_events || 0} <small>events</small>`;

  const dailyChart = window.Chart && Chart.getChart(document.querySelector('#eventsChart'));
  if (dailyChart) {
    const days = Array.from({length: 7}, (_, index) => {
      const day = new Date(); day.setHours(0, 0, 0, 0); day.setDate(day.getDate() - (6 - index));
      return day;
    });
    dailyChart.data.labels = days.map(day => new Intl.DateTimeFormat('en-IN', {weekday: 'short'}).format(day));
    dailyChart.data.datasets[0].data = days.map(day => eventRows.filter(event => {
      const time = new Date(event.timestamp); return time >= day && time < new Date(day.getTime() + 86400000);
    }).length);
    dailyChart.update('none');
  }
  const locationChart = window.Chart && Chart.getChart(document.querySelector('#locationChart'));
  if (locationChart) {
    const top = data.top_risky_locations || [];
    locationChart.data.labels = top.map(item => item.location);
    locationChart.data.datasets[0].data = top.map(item => item.total_events);
    locationChart.update('none');
  }
  const interactionChart = window.Chart && Chart.getChart(document.querySelector('#conflictChart'));
  if (interactionChart) {
    const pairs = new Map();
    eventRows.forEach(event => {
      const key = `${event.object_1_type} × ${event.object_2_type}`;
      pairs.set(key, (pairs.get(key) || 0) + 1);
    });
    interactionChart.data.labels = [...pairs.keys()];
    interactionChart.data.datasets[0].data = [...pairs.values()];
    interactionChart.update('none');
  }
}

async function refreshBackend() {
  const results = await Promise.allSettled([
    apiGet('/dashboard'), apiGet('/events?limit=500'), apiGet('/hotspots'), apiGet('/analytics')
  ]);
  if (results[0].status === 'fulfilled') updateDashboard(results[0].value);
  if (results[1].status === 'fulfilled') updateEventRows(results[1].value);
  if (results[2].status === 'fulfilled') updateHotspots(results[2].value);
  if (results[3].status === 'fulfilled') updateAnalytics(results[3].value, events);
  if (results[0].status === 'rejected') {
    const status = document.querySelector('#apiStatus');
    status.textContent = 'API OFFLINE';
    status.classList.remove('api-online');
    toast('Backend not reached. Showing built-in demo data.', 'fa-triangle-exclamation', true);
  }
}

async function uploadTrafficVideo(file) {
  if (!file) return;
  if (!/\.(mp4|avi)$/i.test(file.name)) {
    toast('Choose an MP4 or AVI video file.', 'fa-circle-exclamation', true);
    return;
  }
  const status = document.querySelector('#uploadStatus');
  const button = document.querySelector('#chooseVideo');
  button.disabled = true;
  status.textContent = 'Uploading…';
  try {
    const form = new FormData();
    form.append('file', file);
    form.append('location', document.querySelector('#uploadLocation').value);
    const token = sessionStorage.getItem('saferoadToken') || localStorage.getItem('saferoadToken');
    const response = await fetch(`${API_BASE}/video/upload`, {method: 'POST', body: form,
      headers: token ? {Authorization: `Bearer ${token}`} : {}});
    const upload = await response.json();
    if (!response.ok) throw new Error(upload.detail || `Upload failed (${response.status})`);
    status.textContent = 'Queued…';
    let result;
    for (let attempt = 0; attempt < 90; attempt++) {
      await new Promise(resolve => setTimeout(resolve, 1500));
      result = await apiGet(`/video/${upload.video_id}`);
      status.textContent = result.processing_status === 'processing' ? 'Processing…' : `Status: ${result.processing_status}`;
      if (['completed', 'failed'].includes(result.processing_status)) break;
    }
    if (!result || result.processing_status !== 'completed') throw new Error(result?.error_message || 'Video processing did not finish.');
    status.textContent = result.frame_count ? `Complete · ${result.frame_count} frames` : 'Complete · demo simulation';
    toast(result.frame_count ? `Video analyzed: ${result.frame_count} frames.` : 'Upload complete; demo detections were simulated.', 'fa-circle-check');
    await refreshBackend();
  } catch (error) {
    status.textContent = 'Upload failed';
    toast(error.message || 'Could not connect to backend.', 'fa-triangle-exclamation', true);
  } finally {
    button.disabled = false;
  }
}

document.querySelector('#chooseVideo').addEventListener('click', () => document.querySelector('#videoFileInput').click());
document.querySelector('#videoFileInput').addEventListener('change', event => {
  uploadTrafficVideo(event.target.files[0]);
  event.target.value = '';
});
refreshBackend();
setInterval(refreshBackend, 10000);

// Route dashboard uploads through the same pretrained analyzer as the main studio.
const PRETRAINED_API = 'http://127.0.0.1:8001/api';
async function uploadTrafficVideo(file) {
  if (!file) return;
  if (!/\.(mp4|avi|mov|mkv|webm)$/i.test(file.name)) {
    toast('Choose an MP4, AVI, MOV, MKV, or WEBM video.', 'fa-circle-exclamation', true);
    return;
  }
  const status = document.querySelector('#uploadStatus');
  const button = document.querySelector('#chooseVideo');
  const locationName = document.querySelector('#uploadLocation').value;
  button.disabled = true;
  status.textContent = 'Uploading video...';
  try {
    const form = new FormData(); form.append('file', file);
    const uploadResponse = await fetch(`${PRETRAINED_API}/upload`, {method: 'POST', body: form});
    const upload = await uploadResponse.json();
    if (!uploadResponse.ok) throw new Error(upload.detail || `Upload failed (${uploadResponse.status})`);

    const startResponse = await fetch(`${PRETRAINED_API}/start-analysis`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({video_source: upload.filename, location: locationName, model_id: 'local-yolov8n', frame_stride: 2})
    });
    const started = await startResponse.json();
    if (!startResponse.ok) throw new Error(started.detail || 'Could not start pretrained analysis.');

    let job;
    for (let attempt = 0; attempt < 1800; attempt++) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      const response = await fetch(`${PRETRAINED_API}/job-status/${started.job_id}`);
      job = await response.json();
      if (!response.ok) throw new Error(job.detail || 'Could not read analysis status.');
      status.textContent = job.status === 'COMPLETED' ? 'Saving incident records...' : `Analyzing video: ${Math.round(job.progress || 0)}%`;
      if (job.status === 'COMPLETED' || job.status === 'FAILED') break;
    }
    if (!job || job.status !== 'COMPLETED') throw new Error(job?.error || 'Video analysis did not finish.');

    const summary = job.summary || {};
    const token = sessionStorage.getItem('saferoadToken') || localStorage.getItem('saferoadToken');
    const saveResponse = await fetch(`${API_BASE}/pretrained/import`, {
      method: 'POST', headers: {'Content-Type': 'application/json', ...(token ? {Authorization: `Bearer ${token}`} : {})},
      body: JSON.stringify({
        job_id: job.job_id, video_name: job.video_name || file.name, location: locationName,
        total_frames: summary.total_frames || 0, fps: summary.fps || 0,
        duration_seconds: summary.duration_seconds || 0,
        incidents: (job.incidents || []).map(incident => ({
          incident_id: incident.incident_id, type: incident.type,
          start_time: incident.start_time || 0, end_time: incident.end_time || incident.start_time || 0,
          peak_severity: incident.peak_severity || 0,
          track_a: incident.track_a > 0 ? incident.track_a : null,
          track_b: incident.track_b > 0 ? incident.track_b : null,
          class_a: incident.class_a || 'vehicle', class_b: incident.class_b || null,
          ttc_seconds: incident.ttc_seconds, relative_distance: incident.relative_distance,
          subtype: incident.subtype || ''
        }))
      })
    });
    const saved = await saveResponse.json();
    if (!saveResponse.ok) throw new Error(saved.detail || 'Analysis completed but saving to the dashboard database failed.');
    status.textContent = `Saved: ${saved.near_misses} near misses, ${saved.collisions} collisions`;
    if (window.renderSafetySolution && saved.solution) window.renderSafetySolution(saved.solution);
    toast(`Video analyzed and saved: ${saved.near_misses} near misses, ${saved.collisions} collisions.`, 'fa-circle-check');
    await refreshBackend();
  } catch (error) {
    status.textContent = 'Upload or analysis failed';
    toast(error.message || 'Could not connect to the pretrained analyzer.', 'fa-triangle-exclamation', true);
  } finally {
    button.disabled = false;
  }
}
