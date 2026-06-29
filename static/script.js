/**
 * script.js - Multiple User Face Attendance System Frontend
 */

'use strict';

// ═══════════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════════

const State = {
  activeTab: 'liveTab',
  cameraRunning: false,
  activeClassSession: null,
  selectedHistorySessionId: null,
  lastNotificationTime: 0,
  
  // Registration image states
  selectedFile: null,
  useSnapshot: false,
  snapshotDataUrl: null,
  
  // Polling Intervals
  notificationsInterval: null,
  statsInterval: null,
  clockInterval: null,
};

// ═══════════════════════════════════════════════════════════
// DOM ELEMENTS
// ═══════════════════════════════════════════════════════════

const $ = (id) => document.getElementById(id);

const DOM = {
  // Navigation
  tabButtons:        document.querySelectorAll('.tab-btn'),
  tabContents:       document.querySelectorAll('.tab-content'),
  
  // Header
  liveDot:           $('liveDot'),
  liveText:          $('liveText'),
  liveIndicator:     $('liveIndicator'),
  navbarTime:        $('navbarTime'),

  // Tab 1: Live Session - Controller
  startSessionForm:  $('startSessionForm'),
  classNameInput:    $('classNameInput'),
  subjectInput:      $('subjectInput'),
  activeClassInfo:   $('activeClassInfo'),
  activeClassName:   $('activeClassName'),
  activeClassSubject: $('activeClassSubject'),
  activeClassDate:   $('activeClassDate'),
  endSessionBtn:     $('endSessionBtn'),

  // Tab 1: Live Session - Camera
  cameraFeed:        $('cameraFeed'),
  cameraWrapper:     $('cameraWrapper'),
  startCameraBtn:    $('startCameraBtn'),
  stopCameraBtn:     $('stopCameraBtn'),

  // Tab 1: Live Session - Stats & Table
  statRegistered:    $('statRegistered'),
  statPresent:       $('statPresent'),
  statRate:          $('statRate'),
  progressBar:       $('progressBar'),
  statLastName:      $('statLastName'),
  statLastTime:      $('statLastTime'),
  liveAttendanceBody: $('liveAttendanceBody'),
  refreshLiveBtn:    $('refreshLiveBtn'),

  // Tab 2: Student Registry
  registerStudentForm: $('registerStudentForm'),
  studentIdInput:    $('studentIdInput'),
  studentNameInput:  $('studentNameInput'),
  fileUploadArea:    $('fileUploadArea'),
  studentPhotoInput: $('studentPhotoInput'),
  captureSnapshotBtn: $('captureSnapshotBtn'),
  photoPreview:      $('photoPreview'),
  previewImg:        $('previewImg'),
  clearPreviewBtn:   $('clearPreviewBtn'),
  registerFeedback:  $('registerFeedback'),
  searchStudentInput: $('searchStudentInput'),
  studentListBody:   $('studentListBody'),

  // Tab 3: Session History
  sessionsList:      $('sessionsList'),
  historyDetailsCard: $('historyDetailsCard'),
  historyDetailsContent: $('historyDetailsContent'),
  historyDetailsTitle: $('historyDetailsTitle'),
  historyDetailsMeta: $('historyDetailsMeta'),
  exportHistoryCsvBtn: $('exportHistoryCsvBtn'),
  historyAttendanceBody: $('historyAttendanceBody'),

  // Toasts
  toastContainer:    $('toastContainer'),
};

// ═══════════════════════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════════════════════

async function init() {
  setupTabs();
  setupClock();
  setupEventListeners();
  setupRegistrationForm();
  
  // Load initial states
  await checkActiveSession();
  await loadStudents();
  await loadClassHistory();
  
  // Set offline feed src
  DOM.cameraFeed.src = `/video_feed?t=${Date.now()}`;
  
  // Start polling
  startPolling();
}

// ═══════════════════════════════════════════════════════════
// CLOCK
// ═══════════════════════════════════════════════════════════

function setupClock() {
  function update() {
    const now = new Date();
    DOM.navbarTime.textContent = now.toLocaleTimeString('en-US', { hour12: false });
  }
  update();
  State.clockInterval = setInterval(update, 1000);
}

// ═══════════════════════════════════════════════════════════
// TAB NAVIGATION
// ═══════════════════════════════════════════════════════════

function setupTabs() {
  DOM.tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetTab = btn.getAttribute('data-tab');
      
      // Update buttons
      DOM.tabButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      
      // Update contents
      DOM.tabContents.forEach(c => {
        if (c.id === targetTab) {
          c.classList.add('active');
        } else {
          c.classList.remove('active');
        }
      });
      
      State.activeTab = targetTab;
      
      // Refresh views if needed when entering tab
      if (targetTab === 'studentsTab') {
        loadStudents();
      } else if (targetTab === 'historyTab') {
        loadClassHistory();
      }
    });
  });
}

// ═══════════════════════════════════════════════════════════
// CLASS SESSION ACTIONS
// ═══════════════════════════════════════════════════════════

async function checkActiveSession() {
  try {
    const res = await fetch('/active_session');
    const data = await res.json();
    
    if (data.active) {
      State.activeClassSession = data.session;
      showActiveSessionUI(data.session);
    } else {
      State.activeClassSession = null;
      showNoSessionUI();
    }
    await checkCameraStatus();
    await loadLiveStats();
    await loadLiveAttendance();
  } catch (e) {
    console.error("Error checking active session:", e);
  }
}

function showActiveSessionUI(session) {
  DOM.startSessionForm.classList.add('hidden');
  DOM.activeClassInfo.classList.remove('hidden');
  
  DOM.activeClassName.textContent = session.class_name;
  DOM.activeClassSubject.textContent = session.subject;
  DOM.activeClassDate.textContent = formatDate(session.date);
}

function showNoSessionUI() {
  DOM.startSessionForm.classList.remove('hidden');
  DOM.activeClassInfo.classList.add('hidden');
  DOM.startSessionForm.reset();
}

async function handleStartSession(e) {
  e.preventDefault();
  const class_name = DOM.classNameInput.value.trim();
  const subject = DOM.subjectInput.value.trim();
  
  try {
    const res = await fetch('/start_session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ class_name, subject })
    });
    const data = await res.json();
    
    if (data.success) {
      showToast("Session Started", `Class ${class_name} is now active.`, 'success');
      await checkActiveSession();
    } else {
      showToast("Error", data.message, 'error');
    }
  } catch (err) {
    showToast("Connection Error", "Could not start session.", 'error');
  }
}

async function handleEndSession() {
  if (!State.activeClassSession) return;
  if (!confirm("Are you sure you want to end this class session and close attendance?")) return;
  
  try {
    const res = await fetch('/end_session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ class_id: State.activeClassSession.id })
    });
    const data = await res.json();
    
    if (data.success) {
      showToast("Session Ended", "Attendance session closed.", 'info');
      await checkActiveSession();
    } else {
      showToast("Error", data.message, 'error');
    }
  } catch (err) {
    showToast("Connection Error", "Could not end session.", 'error');
  }
}

// ═══════════════════════════════════════════════════════════
// CAMERA CONTROLS
// ═══════════════════════════════════════════════════════════

async function startCamera() {
  DOM.startCameraBtn.disabled = true;
  DOM.startCameraBtn.innerHTML = `<span class="spinner"></span> Starting...`;
  
  try {
    const res = await fetch('/start_camera', { method: 'POST' });
    const data = await res.json();
    
    if (data.success) {
      State.cameraRunning = true;
      updateCameraUI(true);
      DOM.cameraFeed.src = `/video_feed?t=${Date.now()}`;
      showToast('Camera Started', 'Live video feed active.', 'success');
    } else {
      showToast('Camera Error', data.message, 'error');
      DOM.startCameraBtn.disabled = false;
      DOM.startCameraBtn.innerHTML = `▶ Start Feed`;
    }
  } catch (e) {
    showToast('Connection Error', 'Could not start camera.', 'error');
    DOM.startCameraBtn.disabled = false;
    DOM.startCameraBtn.innerHTML = `▶ Start Feed`;
  }
}

async function stopCamera() {
  DOM.stopCameraBtn.disabled = true;
  try {
    await fetch('/stop_camera', { method: 'POST' });
    State.cameraRunning = false;
    updateCameraUI(false);
    setTimeout(() => {
      DOM.cameraFeed.src = `/video_feed?t=${Date.now()}`;
    }, 500);
    showToast('Camera Stopped', 'Video feed paused.', 'info');
  } catch (e) {
    showToast('Error', 'Could not stop camera.', 'error');
  } finally {
    DOM.stopCameraBtn.disabled = false;
  }
}

function updateCameraUI(running) {
  DOM.liveIndicator.className = `live-indicator ${running ? 'active' : 'stopped'}`;
  DOM.liveText.textContent = running ? 'LIVE' : 'STOPPED';
  DOM.cameraWrapper.classList.toggle('live', running);
  
  DOM.startCameraBtn.disabled = running;
  DOM.stopCameraBtn.disabled = !running;
  
  if (running) {
    DOM.startCameraBtn.innerHTML = `▶ Start Feed`;
  }
}

async function checkCameraStatus() {
  try {
    const res = await fetch('/camera_status');
    const data = await res.json();
    if (data.running !== State.cameraRunning) {
      State.cameraRunning = data.running;
      updateCameraUI(data.running);
    }
  } catch (e) {
    // Ignore
  }
}

// ═══════════════════════════════════════════════════════════
// LIVE SESSION LOGS & STATS
// ═══════════════════════════════════════════════════════════

async function loadLiveStats() {
  let url = '/stats';
  if (State.activeClassSession) {
    url += `?class_id=${State.activeClassSession.id}`;
  }
  
  try {
    const res = await fetch(url);
    const data = await res.json();
    
    DOM.statRegistered.textContent = data.total_registered;
    DOM.statPresent.textContent    = data.present_count || 0;
    DOM.statRate.textContent       = `${data.attendance_rate || 0}%`;
    DOM.progressBar.style.width    = `${data.attendance_rate || 0}%`;
    
    if (data.last_marked) {
      DOM.statLastName.textContent = data.last_marked.name;
      DOM.statLastTime.textContent = data.last_marked.time;
    } else {
      DOM.statLastName.textContent = 'None yet';
      DOM.statLastTime.textContent = '—';
    }
  } catch (e) {
    console.error("Error loading live stats:", e);
  }
}

async function loadLiveAttendance() {
  if (!State.activeClassSession) {
    DOM.liveAttendanceBody.innerHTML = `
      <tr>
        <td colspan="4">
          <div class="empty-state">
            <span class="empty-state-icon">📺</span>
            <h3>No active session</h3>
            <p>Start a class session above to view live attendance.</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }
  
  try {
    const res = await fetch(`/attendance?class_id=${State.activeClassSession.id}`);
    const data = await res.json();
    renderLiveTable(data.records);
  } catch (e) {
    console.error("Error loading live attendance:", e);
  }
}

function renderLiveTable(records) {
  if (!records || records.length === 0) {
    DOM.liveAttendanceBody.innerHTML = `
      <tr>
        <td colspan="4">
          <div class="empty-state">
            <span class="empty-state-icon">⚡</span>
            <h3>Waiting for detections...</h3>
            <p>Students recognized by the camera will appear here automatically.</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }
  
  DOM.liveAttendanceBody.innerHTML = records.map(r => `
    <tr>
      <td><span class="mono">${escapeHtml(r.student_id.toUpperCase())}</span></td>
      <td>
        <div style="display:flex; align-items:center; gap:8px;">
          <span class="face-avatar">${escapeHtml(getInitials(r.student_name))}</span>
          <strong>${escapeHtml(r.student_name)}</strong>
        </div>
      </td>
      <td><span class="mono">${r.time}</span></td>
      <td><span class="badge badge-present">● Present</span></td>
    </tr>
  `).join('');
}

// ═══════════════════════════════════════════════════════════
// STUDENT REGISTRY TAB
// ═══════════════════════════════════════════════════════════

function setupRegistrationForm() {
  const area = DOM.fileUploadArea;
  
  area.addEventListener('dragover', (e) => {
    e.preventDefault();
    area.style.borderColor = 'var(--accent)';
  });
  
  area.addEventListener('dragleave', () => {
    area.style.borderColor = 'var(--border)';
  });
  
  area.addEventListener('drop', (e) => {
    e.preventDefault();
    area.style.borderColor = 'var(--border)';
    const file = e.dataTransfer.files[0];
    if (file) handleFileSelect(file);
  });
  
  DOM.studentPhotoInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) handleFileSelect(file);
  });
  
  DOM.captureSnapshotBtn.addEventListener('click', captureSnapshotFromServer);
  DOM.clearPreviewBtn.addEventListener('click', clearPhotoPreview);
  DOM.registerStudentForm.addEventListener('submit', handleRegisterStudent);
  
  DOM.searchStudentInput.addEventListener('input', debounce(loadStudents, 300));
}

function handleFileSelect(file) {
  State.selectedFile = file;
  State.useSnapshot = false;
  
  const reader = new FileReader();
  reader.onload = (e) => {
    DOM.previewImg.src = e.target.result;
    DOM.photoPreview.style.display = 'block';
  };
  reader.readAsDataURL(file);
}

async function captureSnapshotFromServer() {
  if (!State.cameraRunning) {
    showToast("Camera Offline", "Please start the camera feed first to capture a snapshot.", "warning");
    return;
  }
  
  DOM.captureSnapshotBtn.disabled = true;
  DOM.captureSnapshotBtn.textContent = "📸 Capturing...";
  
  try {
    const res = await fetch('/capture_snapshot');
    const data = await res.json();
    
    if (data.success) {
      State.useSnapshot = true;
      State.selectedFile = null;
      State.snapshotDataUrl = data.image;
      
      DOM.previewImg.src = data.image;
      DOM.photoPreview.style.display = 'block';
      showToast("Snapshot Captured", "Snapshot grabbed from running video feed.", "success");
    } else {
      showToast("Capture Error", data.message, "error");
    }
  } catch (err) {
    showToast("Error", "Could not capture snapshot from server.", "error");
  } finally {
    DOM.captureSnapshotBtn.disabled = false;
    DOM.captureSnapshotBtn.textContent = "📸 Capture from Live Feed";
  }
}

function clearPhotoPreview() {
  State.selectedFile = null;
  State.useSnapshot = false;
  State.snapshotDataUrl = null;
  DOM.previewImg.src = "";
  DOM.photoPreview.style.display = 'none';
  DOM.studentPhotoInput.value = "";
}

async function handleRegisterStudent(e) {
  e.preventDefault();
  
  const student_id = DOM.studentIdInput.value.trim().toLowerCase();
  const name = DOM.studentNameInput.value.trim();
  
  if (!student_id || !name) {
    showFeedback("Student ID and Name are required.", "error");
    return;
  }
  
  if (!State.selectedFile && !State.useSnapshot) {
    showFeedback("Please upload a photo or capture a snapshot.", "error");
    return;
  }
  
  const submitBtn = DOM.registerStudentForm.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  submitBtn.innerHTML = `<span class="spinner"></span> Registering...`;
  
  try {
    const formData = new FormData();
    formData.append("student_id", student_id);
    formData.append("name", name);
    
    if (State.useSnapshot) {
      formData.append("use_snapshot", "true");
    } else {
      formData.append("photo", State.selectedFile);
    }
    
    const res = await fetch('/register_student', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    
    if (data.success) {
      showFeedback("Student registered successfully!", "success");
      showToast("Success", `${name} is registered.`, "success");
      
      // Reset
      DOM.registerStudentForm.reset();
      clearPhotoPreview();
      
      // Reload
      await loadStudents();
      await loadLiveStats();
    } else {
      showFeedback(data.message, "error");
    }
  } catch (err) {
    showFeedback("Connection error. Try again.", "error");
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = `+ Register Student`;
  }
}

function showFeedback(msg, type) {
  DOM.registerFeedback.className = `alert alert-${type}`;
  DOM.registerFeedback.textContent = msg;
  DOM.registerFeedback.style.display = 'block';
  if (type === 'success') {
    setTimeout(() => { DOM.registerFeedback.style.display = 'none'; }, 4000);
  }
}

async function loadStudents() {
  const query = DOM.searchStudentInput.value.trim();
  try {
    const res = await fetch(`/students?search=${encodeURIComponent(query)}`);
    const data = await res.json();
    renderStudentList(data.students);
  } catch (e) {
    console.error("Error loading students:", e);
  }
}

function renderStudentList(students) {
  if (!students || students.length === 0) {
    DOM.studentListBody.innerHTML = `
      <tr>
        <td colspan="4">
          <div class="empty-state">
            <h3>No students found</h3>
            <p>Add new student records using the left form.</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }
  
  DOM.studentListBody.innerHTML = students.map(s => `
    <tr>
      <td><span class="mono">${escapeHtml(s.student_id.toUpperCase())}</span></td>
      <td>
        <div style="display:flex; align-items:center; gap:8px;">
          <span class="face-avatar">${escapeHtml(getInitials(s.name))}</span>
          <strong>${escapeHtml(s.name)}</strong>
        </div>
      </td>
      <td><span class="mono">${formatDate(s.created_at.split('T')[0])}</span></td>
      <td>
        <button class="btn btn-ghost btn-sm" onclick="deleteStudent('${s.student_id}')" style="color:var(--danger); border-color:rgba(255,76,76,0.2);">Delete</button>
      </td>
    </tr>
  `).join('');
}

window.deleteStudent = async function(student_id) {
  if (!confirm(`Are you sure you want to delete student ${student_id.toUpperCase()}? This will clear their face encoding and all past attendance records.`)) return;
  
  try {
    const res = await fetch('/delete_student', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ student_id })
    });
    const data = await res.json();
    if (data.success) {
      showToast("Deleted", "Student profile deleted.", "info");
      await loadStudents();
      await loadLiveStats();
    } else {
      showToast("Error", data.message, "error");
    }
  } catch (e) {
    showToast("Error", "Could not delete student.", "error");
  }
};

// ═══════════════════════════════════════════════════════════
// TAB 3: SESSION HISTORY
// ═══════════════════════════════════════════════════════════

async function loadClassHistory() {
  try {
    const res = await fetch('/class_history');
    const data = await res.json();
    renderHistoryList(data.history);
  } catch (e) {
    console.error("Error loading class history:", e);
  }
}

function renderHistoryList(history) {
  if (!history || history.length === 0) {
    DOM.sessionsList.innerHTML = `
      <div class="empty-state">
        <p>No past class sessions recorded.</p>
      </div>
    `;
    return;
  }
  
  DOM.sessionsList.innerHTML = history.map(h => `
    <div class="session-item ${State.selectedHistorySessionId === h.id ? 'active' : ''}" onclick="selectHistorySession(${h.id})">
      <div class="session-item-title">${escapeHtml(h.class_name)} - ${escapeHtml(h.subject)}</div>
      <div class="session-item-sub">${formatDate(h.date)}</div>
      <div class="session-item-stats">
        <span>Status: <strong style="color:${h.status === 'active' ? 'var(--accent)' : 'var(--text-muted)'}">${h.status.toUpperCase()}</strong></span>
        <span>Present: <strong>${h.present_count}</strong></span>
      </div>
    </div>
  `).join('');
}

window.selectHistorySession = async function(id) {
  State.selectedHistorySessionId = id;
  
  // Highlight active item
  const items = DOM.sessionsList.querySelectorAll('.session-item');
  loadClassHistory(); // reload to apply active class dynamically
  
  DOM.historyDetailsCard.querySelector('.empty-state').classList.add('hidden');
  DOM.historyDetailsContent.classList.remove('hidden');
  
  try {
    // Load stats for this class
    const statsRes = await fetch(`/stats?class_id=${id}`);
    const stats = await statsRes.json();
    
    // Load attendance
    const attRes = await fetch(`/attendance?class_id=${id}`);
    const att = await attRes.json();
    
    DOM.historyDetailsTitle.textContent = `${stats.class_name} - ${stats.subject}`;
    DOM.historyDetailsMeta.textContent = `DATE: ${formatDate(stats.date)} | STATUS: ${stats.status.toUpperCase()} | TOTAL PRESENT: ${stats.present_count} | RATE: ${stats.attendance_rate}%`;
    
    renderHistoryAttendance(att.records);
  } catch (e) {
    console.error("Error loading history session details:", e);
  }
};

function renderHistoryAttendance(records) {
  if (!records || records.length === 0) {
    DOM.historyAttendanceBody.innerHTML = `
      <tr>
        <td colspan="4">
          <div class="empty-state">
            <p>No attendance records for this session.</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }
  
  DOM.historyAttendanceBody.innerHTML = records.map(r => `
    <tr>
      <td><span class="mono">${escapeHtml(r.student_id.toUpperCase())}</span></td>
      <td>
        <div style="display:flex; align-items:center; gap:8px;">
          <span class="face-avatar">${escapeHtml(getInitials(r.student_name))}</span>
          <strong>${escapeHtml(r.student_name)}</strong>
        </div>
      </td>
      <td><span class="mono">${r.time}</span></td>
      <td><span class="badge badge-present">● Present</span></td>
    </tr>
  `).join('');
}

function exportHistoryCsv() {
  if (!State.selectedHistorySessionId) return;
  window.location.href = `/export_csv?class_id=${State.selectedHistorySessionId}`;
  showToast("Exporting", "CSV download started.", "success");
}

// ═══════════════════════════════════════════════════════════
// POLLING & TOASTS
// ═══════════════════════════════════════════════════════════

function startPolling() {
  // Poll notifications
  State.notificationsInterval = setInterval(async () => {
    if (!State.cameraRunning || !State.activeClassSession) return;
    
    try {
      const res = await fetch(`/notifications?since=${State.lastNotificationTime}`);
      const data = await res.json();
      
      State.lastNotificationTime = data.server_time;
      
      data.notifications.forEach(n => {
        showToast("Attendance Marked", `${n.name} (${n.student_id.toUpperCase()}) present.`, "success");
        // Prepend to live logs
        prependLiveAttendanceRow(n);
      });
      
      if (data.notifications.length > 0) {
        loadLiveStats();
      }
    } catch (e) {}
  }, 2000);
  
  // Poll stats
  State.statsInterval = setInterval(() => {
    if (State.activeClassSession) {
      loadLiveStats();
    }
  }, 5000);
}

function prependLiveAttendanceRow(notif) {
  const body = DOM.liveAttendanceBody;
  
  // Remove empty state
  const empty = body.querySelector('.empty-state');
  if (empty) body.innerHTML = '';
  
  // Don't duplicate
  const existing = body.querySelector(`tr`);
  
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td><span class="mono">${escapeHtml(notif.student_id.toUpperCase())}</span></td>
    <td>
      <div style="display:flex; align-items:center; gap:8px;">
        <span class="face-avatar">${escapeHtml(getInitials(notif.name))}</span>
        <strong>${escapeHtml(notif.name)}</strong>
      </div>
    </td>
    <td><span class="mono">${notif.time}</span></td>
    <td><span class="badge badge-present">● Present</span></td>
  `;
  body.insertBefore(tr, body.firstChild);
}

function showToast(title, msg, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast`;
  toast.style.borderLeftColor = type === 'success' ? 'var(--accent)' : (type === 'error' ? 'var(--danger)' : 'var(--warning)');
  toast.innerHTML = `
    <div style="font-weight:700; font-size:0.85rem; color:var(--text-primary);">${escapeHtml(title)}</div>
    <div style="font-size:0.75rem; color:var(--text-muted); margin-top:2px;">${escapeHtml(msg)}</div>
  `;
  DOM.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'slideOut 0.3s ease forwards';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ═══════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════

function formatDate(dateStr) {
  if (!dateStr || dateStr === '—') return '—';
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function getInitials(name) {
  return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

// ═══════════════════════════════════════════════════════════
// EVENT LISTENERS
// ═══════════════════════════════════════════════════════════

function setupEventListeners() {
  DOM.startSessionForm.addEventListener('submit', handleStartSession);
  DOM.endSessionBtn.addEventListener('click', handleEndSession);
  
  DOM.startCameraBtn.addEventListener('click', startCamera);
  DOM.stopCameraBtn.addEventListener('click', stopCamera);
  
  DOM.refreshLiveBtn.addEventListener('click', () => {
    loadLiveStats();
    loadLiveAttendance();
    showToast("Refreshed", "Live attendance list updated.", "info");
  });
  
  DOM.exportHistoryCsvBtn.addEventListener('click', exportHistoryCsv);
}

document.addEventListener('DOMContentLoaded', init);
