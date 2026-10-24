// SafeGuard AI - Accident Detection Studio Frontend Engine

const API_BASE = "http://127.0.0.1:8001";
const apiUrl = path => `${API_BASE}${path}`;
let appState = {
  modelId: "local-yolov8n",
  videoSource: null, // "sample" or upload filename
  videoDisplayName: null,
  jobId: null,
  jobData: null,
  pollTimer: null,
  currentVideoView: "analyzed", // "analyzed" or "raw"
  sampleAvailable: false
};

document.addEventListener("DOMContentLoaded", () => {
  initUI();
  checkSampleVideo();
  checkLocalModel();
});

function initUI() {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("fileInput");
  const btnStartAnalysis = document.getElementById("btnStartAnalysis");
  const btnLoadSample = document.getElementById("btnLoadSample");
  const btnSettings = document.getElementById("btnSettings");
  const btnCloseSettings = document.getElementById("btnCloseSettings");
  const modalSettings = document.getElementById("modalSettings");
  const btnTestLocalModel = document.getElementById("btnTestLocalModel");
  const btnSaveSettings = document.getElementById("btnSaveSettings");
  
  // Drag & drop handlers
  dropzone.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
      handleFileUpload(e.target.files[0]);
    }
  });

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  });

  // Load sample video button
  btnLoadSample.addEventListener("click", (e) => {
    e.stopPropagation();
    selectSampleVideo();
  });

  // Start analysis button
  btnStartAnalysis.addEventListener("click", startAnalysis);

  // Settings modal
  btnSettings.addEventListener("click", () => {
    document.getElementById("inputModelId").value = appState.modelId;
    modalSettings.style.display = "flex";
  });
  btnCloseSettings.addEventListener("click", () => modalSettings.style.display = "none");
  modalSettings.addEventListener("click", (e) => {
    if (e.target === modalSettings) modalSettings.style.display = "none";
  });

  // Check local pretrained model
  btnTestLocalModel.addEventListener("click", async () => {
    const statusText = document.getElementById("roboflowTestResult");
    statusText.innerText = "Checking local pretrained weights...";
    statusText.style.color = "var(--accent-cyan)";
    
    try {
      const res = await fetch(apiUrl("/api/check-model"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: "local-yolov8n" })
      });
      const data = await res.json();
      if (data.success) {
        statusText.innerText = `Ready in ${data.latency_ms}ms (${data.message})`;
        statusText.style.color = "var(--accent-emerald)";
      } else {
        statusText.innerText = `Model unavailable: ${data.error || "Unknown error"}`;
        statusText.style.color = "var(--accent-crimson)";
      }
    } catch (err) {
      statusText.innerText = `Network error: ${err.message}`;
      statusText.style.color = "var(--accent-crimson)";
    }
  });

  // Save settings
  btnSaveSettings.addEventListener("click", () => {
    appState.modelId = "local-yolov8n";
    document.getElementById("statModel").innerText = appState.modelId;
    modalSettings.style.display = "none";
    showNotification("Settings updated successfully!");
  });

  document.getElementById("signOut").addEventListener("click", () => {
    [sessionStorage, localStorage].forEach(store => { store.removeItem("saferoadUser"); store.removeItem("saferoadToken"); });
    location.href = "login.html";
  });

  // View toggle buttons
  const btnViewAnalyzed = document.getElementById("btnViewAnalyzed");
  const btnViewRaw = document.getElementById("btnViewRaw");
  
  if (btnViewAnalyzed && btnViewRaw) {
    btnViewAnalyzed.addEventListener("click", () => switchVideoView("analyzed"));
    btnViewRaw.addEventListener("click", () => switchVideoView("raw"));
  }

  // Speed buttons
  document.querySelectorAll(".speed-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const spd = parseFloat(btn.dataset.speed);
      const v = document.getElementById("mainVideo");
      if (v) v.playbackRate = spd;
      document.querySelectorAll(".speed-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
    });
  });
}

// Check if default sample video exists
async function checkSampleVideo() {
  try {
    const res = await fetch(apiUrl("/api/sample-video"));
    const data = await res.json();
    const btn = document.getElementById("btnLoadSample");
    if (data.available) {
      appState.sampleAvailable = true;
      appState.sampleFilename = data.filename;
      appState.sampleSize = data.size_mb;
      btn.style.display = "inline-flex";
      btn.innerHTML = `⚡ Load Test Video (${data.filename} - ${data.size_mb} MB)`;
    } else {
      btn.style.display = "none";
    }
  } catch (err) {
    console.warn("Could not check sample video:", err);
  }
}

// Check local pretrained model availability
async function checkLocalModel() {
  try {
    const res = await fetch(apiUrl("/api/check-model"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: appState.modelId })
    });
    const data = await res.json();
    const indicator = document.getElementById("navStatusIndicator");
    const navText = document.getElementById("navStatusText");
    if (data.success) {
      indicator.style.background = "var(--accent-emerald)";
      navText.innerText = `Local model ready (${data.latency_ms}ms)`;
    } else {
      indicator.style.background = "var(--accent-amber)";
      navText.innerText = "Local model unavailable";
    }
  } catch (err) {
    console.warn("Local model check error:", err);
  }
}

// Select default sample video
function selectSampleVideo() {
  appState.videoSource = "sample";
  appState.videoDisplayName = appState.sampleFilename || "Sample video";
  showSelectedFileCard(appState.videoDisplayName, `${appState.sampleSize || 0} MB`, "Preloaded Test Video");
  document.getElementById("btnStartAnalysis").removeAttribute("disabled");
}

// Upload file
async function handleFileUpload(file) {
  const card = document.getElementById("selectedFileCard");
  const fileName = document.getElementById("selectedFileName");
  const fileSub = document.getElementById("selectedFileSub");
  
  card.style.display = "flex";
  fileName.innerText = file.name;
  fileSub.innerText = "Uploading to server...";
  document.getElementById("btnStartAnalysis").setAttribute("disabled", "true");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch(apiUrl("/api/upload"), {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (data.success) {
      appState.videoSource = data.filename;
      appState.videoDisplayName = data.original_name;
      fileSub.innerText = `${data.size_mb} MB • Ready for inference`;
      document.getElementById("btnStartAnalysis").removeAttribute("disabled");
      showNotification(`Uploaded ${data.original_name}`);
    } else {
      fileSub.innerText = `Upload failed: ${data.detail || data.error || "Error"}`;
    }
  } catch (err) {
    fileSub.innerText = `Network error: ${err.message}`;
  }
}

function showSelectedFileCard(name, size, sub) {
  const card = document.getElementById("selectedFileCard");
  const fileName = document.getElementById("selectedFileName");
  const fileSub = document.getElementById("selectedFileSub");
  card.style.display = "flex";
  fileName.innerText = name;
  fileSub.innerText = `${size} • ${sub}`;
}

// Launch Video Analysis Job
async function startAnalysis() {
  if (!appState.videoSource) {
    alert("Please upload or select a test video first!");
    return;
  }

  const stride = parseInt(document.getElementById("selectStride").value, 10) || 2;
  const confThresh = parseFloat(document.getElementById("inputConf").value) || 0.35;
  const iouThresh = parseFloat(document.getElementById("inputIou").value) || 0.14;

  const btnStart = document.getElementById("btnStartAnalysis");
  btnStart.setAttribute("disabled", "true");
  btnStart.innerHTML = `<span class="spinner"></span> Processing...`;

  const progressCard = document.getElementById("progressCard");
  progressCard.style.display = "block";
  document.getElementById("progressFill").style.width = "0%";
  document.getElementById("progressPercent").innerText = "0%";
  document.getElementById("progressStatus").innerText = "Initializing local pretrained YOLO model...";

  try {
    const res = await fetch(apiUrl("/api/start-analysis"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        video_source: appState.videoSource,
        location: document.getElementById("analysisLocation").value,
        model_id: appState.modelId,
        conf_thresh: confThresh,
        collision_iou_thresh: iouThresh,
        frame_stride: stride
      })
    });
    
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not start analysis.");
    if (data.success) {
      appState.jobId = data.job_id;
      startPollingJob(data.job_id);
    } else {
      alert("Failed to start analysis: " + (data.detail || "Unknown error"));
      btnStart.removeAttribute("disabled");
      btnStart.innerHTML = `🚀 Start AI Accident Detection`;
    }
  } catch (err) {
    alert("Request error: " + err.message);
    btnStart.removeAttribute("disabled");
    btnStart.innerHTML = `🚀 Start AI Accident Detection`;
  }
}

// Poll Job Status
function startPollingJob(jobId) {
  if (appState.pollTimer) clearInterval(appState.pollTimer);

  appState.pollTimer = setInterval(async () => {
    try {
      const res = await fetch(apiUrl(`/api/job-status/${jobId}`));
      if (!res.ok) return;
      const job = await res.json();
      updateProgressUI(job);

      if (job.status === "COMPLETED") {
        clearInterval(appState.pollTimer);
        appState.jobData = job;
        await onJobCompleted(job);
      } else if (job.status === "FAILED") {
        clearInterval(appState.pollTimer);
        onJobFailed(job);
      }
    } catch (err) {
      console.warn("Poll status error:", err);
    }
  }, 600);
}

function updateProgressUI(job) {
  const pct = Math.round(job.progress || 0);
  document.getElementById("progressFill").style.width = `${pct}%`;
  document.getElementById("progressPercent").innerText = `${pct}%`;
  
  if (job.total_frames) {
    document.getElementById("progressStatus").innerText = 
      `Analyzing frame ${job.current_frame} / ${job.total_frames} • Speed: ${job.fps || 0} FPS`;
    document.getElementById("metricFrames").innerText = `${job.current_frame} / ${job.total_frames}`;
    document.getElementById("metricEta").innerText = `ETA: ${job.eta_seconds || 0}s`;
    
    if (document.getElementById("statVehicles")) document.getElementById("statVehicles").innerText = job.vehicles_detected || 0;
    const liveCol = job.collisions_count || 0;
    const liveNm = job.near_miss_count || 0;
    if (document.getElementById("statCollisions")) document.getElementById("statCollisions").innerText = liveCol;
    if (document.getElementById("statNearMisses")) document.getElementById("statNearMisses").innerText = liveNm;
    if (document.getElementById("statRisk")) document.getElementById("statRisk").innerText = `${Math.round(job.current_risk || 0)}%`;

    if (liveCol > 0 && document.getElementById("cardCollisions")) {
      document.getElementById("cardCollisions").classList.add("alert-mode");
    }
    if (liveNm > 0 && document.getElementById("cardNearMisses")) {
      document.getElementById("cardNearMisses").classList.add("near-miss-mode");
    }
  }
}

// Job Completed Handler
async function onJobCompleted(job) {
  const btnStart = document.getElementById("btnStartAnalysis");
  btnStart.removeAttribute("disabled");
  btnStart.innerHTML = `🔄 Re-Analyze Video`;
  
  document.getElementById("progressStatus").innerText = "Analysis Complete!";
  document.getElementById("progressFill").style.width = "100%";
  document.getElementById("progressPercent").innerText = "100%";

  const summary = job.summary || {};
  const collisionsCount = summary.collisions_detected != null ? summary.collisions_detected : (job.collisions_count || 0);
  const nearMissCount = summary.near_misses_detected != null ? summary.near_misses_detected : (job.near_miss_count || 0);
  
  if (document.getElementById("statCollisions")) document.getElementById("statCollisions").innerText = collisionsCount;
  if (document.getElementById("statNearMisses")) document.getElementById("statNearMisses").innerText = nearMissCount;
  if (document.getElementById("statRisk")) document.getElementById("statRisk").innerText = `${Math.round(summary.peak_risk || job.current_risk || 0)}%`;
  
  if (collisionsCount > 0 && document.getElementById("cardCollisions")) {
    document.getElementById("cardCollisions").classList.add("alert-mode");
  }
  if (nearMissCount > 0 && document.getElementById("cardNearMisses")) {
    document.getElementById("cardNearMisses").classList.add("near-miss-mode");
  }

  // Load video into player
  loadVideoIntoPlayer(apiUrl(`/api/video/${job.job_id}`));

  // Populate incident feed
  renderIncidentFeed(job.incidents || []);

  // Render risk chart
  renderRiskChart(job.timeline || []);

  // Show download bar
  showDownloadBar(job);

  try {
    const token = sessionStorage.getItem("saferoadToken") || localStorage.getItem("saferoadToken");
    const response = await fetch("http://127.0.0.1:8002/api/pretrained/import", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({
        job_id: job.job_id,
        video_name: job.video_name || appState.videoDisplayName || "traffic-video",
        location: job.location || document.getElementById("analysisLocation").value,
        total_frames: summary.total_frames || 0,
        fps: summary.fps || 0,
        duration_seconds: summary.duration_seconds || 0,
        incidents: (job.incidents || []).map(incident => ({
          incident_id: incident.incident_id,
          type: incident.type,
          start_time: incident.start_time || 0,
          end_time: incident.end_time || incident.start_time || 0,
          peak_severity: incident.peak_severity || 0,
          track_a: incident.track_a > 0 ? incident.track_a : null,
          track_b: incident.track_b > 0 ? incident.track_b : null,
          class_a: incident.class_a || String(incident.vehicles || "vehicle").split(" #")[0].split(" & ")[0],
          class_b: incident.class_b || null,
          ttc_seconds: incident.ttc_seconds,
          relative_distance: incident.relative_distance,
          subtype: incident.subtype || ""
        }))
      })
    });
    const saved = await response.json();
    if (!response.ok) throw new Error(saved.detail || "Database save failed.");
    if (window.renderSafetySolution && saved.solution) window.renderSafetySolution(saved.solution);
    showNotification(`Analysis complete: ${saved.collisions} collision(s), ${saved.near_misses} near miss(es) saved to dashboard database.`);
  } catch (error) {
    showNotification(`Video analysis completed, but database sync failed: ${error.message}`);
  }
}

function onJobFailed(job) {
  const btnStart = document.getElementById("btnStartAnalysis");
  btnStart.removeAttribute("disabled");
  btnStart.innerHTML = `🚀 Start AI Accident Detection`;
  document.getElementById("progressStatus").innerText = `Failed: ${job.error || "Unknown error"}`;
  document.getElementById("progressStatus").style.color = "var(--accent-crimson)";
  alert("Analysis error: " + (job.error || "Failed to process video"));
}

// Video Player Management
function loadVideoIntoPlayer(src) {
  const wrapper = document.getElementById("videoContainer");
  wrapper.innerHTML = `
    <video id="mainVideo" controls autoplay playsinline style="width: 100%; height: 100%;">
      <source src="${src}" type="video/mp4">
      Your browser does not support the video tag.
    </video>
  `;
  document.getElementById("videoControlsBar").style.display = "flex";
  
  // Highlight active view button
  document.getElementById("btnViewAnalyzed").classList.add("active");
  document.getElementById("btnViewRaw").classList.remove("active");
}

function switchVideoView(view) {
  if (!appState.jobId) return;
  const v = document.getElementById("mainVideo");
  if (!v) return;
  const curTime = v.currentTime;
  const isPaused = v.paused;

  if (view === "analyzed") {
    v.src = apiUrl(`/api/video/${appState.jobId}`);
    document.getElementById("btnViewAnalyzed").classList.add("active");
    document.getElementById("btnViewRaw").classList.remove("active");
  } else {
    v.src = apiUrl(`/api/raw-video/${appState.jobId}`);
    document.getElementById("btnViewRaw").classList.add("active");
    document.getElementById("btnViewAnalyzed").classList.remove("active");
  }

  v.currentTime = curTime;
  if (!isPaused) v.play();
  appState.currentVideoView = view;
}

// Render Incident Feed Cards
function renderIncidentFeed(incidents) {
  const container = document.getElementById("incidentList");
  document.getElementById("incidentCountHeader").innerText = incidents.length;

  if (incidents.length === 0) {
    container.innerHTML = `
      <div class="incident-empty">
        <svg width="40" height="40" fill="none" stroke="var(--accent-emerald)" viewBox="0 0 24 24" style="margin: 0 auto 0.75rem auto; display: block;">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <strong>No Collisions Detected</strong><br>
        Traffic flow was smooth and safe throughout the entire sequence.
      </div>
    `;
    return;
  }

  container.innerHTML = "";
  incidents.forEach((inc) => {
    const card = document.createElement("div");
    const isCollision = inc.type === "COLLISION";
    card.className = `incident-card ${isCollision ? 'collision' : 'near-miss'}`;
    
    const minutes = Math.floor(inc.start_time / 60);
    const seconds = (inc.start_time % 60).toFixed(1);
    const timeStr = `${minutes.toString().padStart(2, '0')}:${seconds.padStart(4, '0')}s`;

    const badgeHtml = isCollision
      ? `<span class="severity-pill collision">🚨 ${Math.round(inc.peak_severity)}% Collision</span>`
      : `<span class="severity-pill near-miss">⚠️ ${Math.round(inc.peak_severity)}% Near Miss</span>`;

    card.innerHTML = `
      <div class="incident-card-header">
        <span class="incident-time">⏱ ${timeStr} (Frame ${inc.start_frame})</span>
        ${badgeHtml}
      </div>
      <div class="incident-details">
        <strong>Involved:</strong> ${inc.vehicles || "Multiple Vehicles"}<br>
        <strong>Event Type:</strong> <span style="color: ${isCollision ? 'var(--accent-crimson)' : 'var(--accent-amber)'}; font-weight: 600;">${isCollision ? 'Direct Collision / Impact' : 'Dangerous Near Miss Proximity'}</span><br>
        <strong>Duration:</strong> ${(inc.end_time - inc.start_time).toFixed(1)}s (${inc.frame_count} frames)
      </div>
      ${inc.snapshot_url ? `
        <div class="incident-thumb-wrapper">
          <img src="${inc.snapshot_url}" alt="${isCollision ? 'Collision Frame Snapshot' : 'Near Miss Snapshot'}" class="incident-thumb" />
        </div>
      ` : ''}
    `;

    // Click on card jumps video to incident moment!
    card.addEventListener("click", () => {
      const v = document.getElementById("mainVideo");
      if (v) {
        v.currentTime = Math.max(0, inc.start_time - 0.5);
        v.play();
        showNotification(`Jumped to ${isCollision ? 'collision' : 'near-miss'} at ${timeStr}`);
      }
    });

    container.appendChild(card);
  });
}

// Render Risk Chart with Canvas
function renderRiskChart(timeline) {
  const canvas = document.getElementById("riskChart");
  if (!canvas || timeline.length === 0) return;
  const ctx = canvas.getContext("2d");
  
  canvas.width = canvas.parentElement.clientWidth;
  canvas.height = 60;
  
  const w = canvas.width;
  const h = canvas.height;
  
  ctx.clearRect(0, 0, w, h);
  
  // Baseline
  ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, h - 1);
  ctx.lineTo(w, h - 1);
  ctx.stroke();

  // Yellow Near-Miss threshold (35%)
  ctx.strokeStyle = "rgba(255, 183, 3, 0.35)";
  ctx.setLineDash([3, 3]);
  ctx.beginPath();
  ctx.moveTo(0, h * (1.0 - 0.35));
  ctx.lineTo(w, h * (1.0 - 0.35));
  ctx.stroke();

  // Red Collision threshold (55%)
  ctx.strokeStyle = "rgba(255, 0, 85, 0.4)";
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(0, h * (1.0 - 0.55));
  ctx.lineTo(w, h * (1.0 - 0.55));
  ctx.stroke();
  ctx.setLineDash([]);

  // Plot risk line
  const maxRisk = 100;
  const pts = timeline.map((pt, i) => {
    const x = (i / (timeline.length - 1)) * w;
    const y = h - (pt.risk / maxRisk) * (h - 10) - 5;
    return { x, y, risk: pt.risk, time: pt.time };
  });

  // Area under curve gradient
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, "rgba(255, 0, 85, 0.4)");
  grad.addColorStop(0.5, "rgba(255, 183, 3, 0.2)");
  grad.addColorStop(1, "rgba(0, 245, 255, 0.0)");

  ctx.beginPath();
  ctx.moveTo(pts[0].x, h);
  pts.forEach(p => ctx.lineTo(p.x, p.y));
  ctx.lineTo(pts[pts.length - 1].x, h);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Stroke line
  ctx.beginPath();
  ctx.moveTo(pts[0].x, pts[0].y);
  pts.forEach(p => ctx.lineTo(p.x, p.y));
  ctx.strokeStyle = "#ff0055";
  ctx.lineWidth = 2;
  ctx.stroke();

  // Canvas click scrubber
  canvas.onclick = (e) => {
    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const ratio = clickX / w;
    const v = document.getElementById("mainVideo");
    if (v && v.duration) {
      v.currentTime = ratio * v.duration;
    }
  };
}

// Show Download Bar
function showDownloadBar(job) {
  const container = document.getElementById("exportActions");
  container.style.display = "flex";
  
  const btnDownloadVideo = document.getElementById("btnDownloadVideo");
  const btnDownloadReport = document.getElementById("btnDownloadReport");

  btnDownloadVideo.onclick = () => {
    window.open(apiUrl(`/api/video/${job.job_id}`), "_blank");
  };

  btnDownloadReport.onclick = () => {
    window.open(apiUrl(`/api/report/${job.job_id}`), "_blank");
  };
}

// Notification Toast
function showNotification(msg) {
  let toast = document.getElementById("toastNotification");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toastNotification";
    toast.style.position = "fixed";
    toast.style.bottom = "2rem";
    toast.style.right = "2rem";
    toast.style.background = "var(--bg-surface-elevated)";
    toast.style.border = "1px solid var(--accent-cyan)";
    toast.style.color = "#fff";
    toast.style.padding = "0.75rem 1.25rem";
    toast.style.borderRadius = "var(--radius-md)";
    toast.style.boxShadow = "var(--shadow-cyan)";
    toast.style.fontSize = "0.85rem";
    toast.style.fontWeight = "500";
    toast.style.zIndex = "999";
    toast.style.transition = "all 0.3s ease";
    document.body.appendChild(toast);
  }
  toast.innerText = msg;
  toast.style.opacity = "1";
  toast.style.transform = "translateY(0)";
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
  }, 3500);
}
