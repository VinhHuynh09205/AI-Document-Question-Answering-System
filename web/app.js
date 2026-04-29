/* ================================================================
   ChatBoxAI – Workspace Frontend
   ================================================================ */

const state = {
  token: null,
  username: null,
  guestSessionId: "",
  currentChatId: null,
  chats: [],
  docs: [],
  selectedDocIdsByChat: {},
  uploadJobsByChat: {},
  activeUploadPolls: {},
  uploadMessageIdsByJob: {},
  uploadProgressStateByJob: {},
  uploadProgressTimersByJob: {},
  pendingDocsRenderByChat: {},
  hasChatActivity: false,
};

let markedConfigured = false;
let mermaidThemeMode = "";
let mermaidSequence = 0;
const UPLOAD_JOB_POLL_INTERVAL_MS = 800;
const UPLOAD_JOB_POLL_TIMEOUT_MS = 180000;
const UPLOAD_JOB_STORAGE_KEY = "nectar_upload_jobs_v1";
const LAST_CHAT_STORAGE_KEY = "nectar_last_chat_v1";
const UPLOAD_JOB_TRACK_LIMIT_PER_CHAT = 30;
const GUEST_SESSION_HEADER = "X-Guest-Session";

const UNSAVED_ANONYMOUS_WARNING =
  "Bạn chưa đăng nhập. Nếu thoát trang, cuộc hội thoại và tài liệu tạm sẽ bị mất.";

/* ---- DOM refs ---- */
const fileInput = document.getElementById("fileInput");
const chatTimeline = document.getElementById("chatTimeline");
const askForm = document.getElementById("askForm");
const questionInput = document.getElementById("questionInput");
const workspaceList = document.getElementById("workspaceList");
const btnCreateWs = document.getElementById("btnCreateWs");
const wsTitle = document.getElementById("wsTitle");
const statusPill = document.getElementById("statusPill");
const docsList = document.getElementById("docsList");
const docsSection = document.getElementById("docsSection");
const docsLabel = document.getElementById("docsLabel");
const docsSelectionGuide = document.getElementById("docsSelectionGuide");
const docsSelectAll = document.getElementById("docsSelectAll");
const docsDeleteAllBtn = document.getElementById("docsDeleteAllBtn");
const btnUploadLabel = document.getElementById("btnUploadLabel");
const btnLogin = document.getElementById("btnLogin");
const sidebarClose = document.getElementById("sidebarClose");
const sidebarToggle = document.getElementById("sidebarToggle");
const leftPanel = document.getElementById("leftPanel");
const appShell = document.querySelector(".app-shell");
const ctxMenu = document.getElementById("ctxMenu");
const composerAttach = document.getElementById("composerAttach");
const composerFileInput = document.getElementById("composerFileInput");
const uploadCard = document.getElementById("uploadCard");
const btnSearch = document.getElementById("btnSearch");
const btnTheme = document.getElementById("btnTheme");
const btnExportChat = document.getElementById("btnExportChat");
const exportMenu = document.getElementById("exportMenu");
const searchOverlay = document.getElementById("searchOverlay");
const searchInput = document.getElementById("searchInput");
const searchCount = document.getElementById("searchCount");
const searchClose = document.getElementById("searchClose");
const quickActionsPanel = document.getElementById("quickActionsPanel");
const quickActionsToggle = document.getElementById("quickActionsToggle");
const guestWarning = document.getElementById("guestWarning");

/* ================================================================
   INIT
   ================================================================ */
(function init() {
  configureMarkdownRenderer();
  restoreTrackedUploadJobsFromStorage();
  restoreSession();
  bindEvents();
  applyStoredQuickActionsState();
})();

function restoreTrackedUploadJobsFromStorage() {
  try {
    const raw = localStorage.getItem(UPLOAD_JOB_STORAGE_KEY);
    if (!raw) {
      state.uploadJobsByChat = {};
      return;
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      state.uploadJobsByChat = {};
      return;
    }
    state.uploadJobsByChat = parsed;
  } catch {
    state.uploadJobsByChat = {};
  }
}

function restoreSession() {
  ensureGuestSessionId();

  const token = getStoredAuthToken();
  if (token) {
    state.token = token;
    state.username = localStorage.getItem("username") || "user";
    showLoggedIn();
  } else {
    showLoggedOut();
  }

  loadWorkspaces();
}

function createGuestSessionId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID().replace(/-/g, "");
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
}

function ensureGuestSessionId() {
  if (!state.guestSessionId) {
    state.guestSessionId = createGuestSessionId();
  }
  return state.guestSessionId;
}

function updateGuestWarningVisibility() {
  if (!guestWarning) return;
  guestWarning.hidden = isAuthenticated();
}

/* ================================================================
   EVENT BINDINGS
   ================================================================ */
function bindEvents() {
  /* Upload (sidebar) */
  fileInput.addEventListener("change", handleUpload);

  chatTimeline.addEventListener("click", handleUploadRetryLinkClick);

  /* Upload (composer attach button) */
  composerAttach.addEventListener("click", () => composerFileInput.click());
  composerFileInput.addEventListener("change", handleUpload);

  /* Drag & drop on upload card */
  uploadCard.addEventListener("dragover", (e) => {
    e.preventDefault();
    uploadCard.classList.add("drag-over");
  });
  uploadCard.addEventListener("dragleave", () => {
    uploadCard.classList.remove("drag-over");
  });
  uploadCard.addEventListener("drop", (e) => {
    e.preventDefault();
    uploadCard.classList.remove("drag-over");
    if (e.dataTransfer.files.length) {
      handleUploadFiles(Array.from(e.dataTransfer.files));
    }
  });

  /* Ask */
  askForm.addEventListener("submit", handleAsk);
  questionInput.addEventListener("input", autoGrowTextarea);
  questionInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); askForm.requestSubmit(); }
  });

  /* Quick action chips */
  for (const chip of document.querySelectorAll(".chip")) {
    chip.addEventListener("click", () => {
      questionInput.value = chip.dataset.question || "";
      questionInput.focus();
      autoGrowTextarea();
      collapseQuickActions();
    });
  }

  if (quickActionsToggle) {
    quickActionsToggle.addEventListener("click", toggleQuickActions);
  }

  /* Workspace */
  btnCreateWs.addEventListener("click", handleCreateWorkspace);
  if (docsDeleteAllBtn) {
    docsDeleteAllBtn.addEventListener("click", handleDeleteAllDocuments);
  }

  /* Export chat */
  if (btnExportChat) {
    btnExportChat.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleExportMenu();
    });
  }
  if (exportMenu) {
    exportMenu.addEventListener("click", (e) => {
      const actionButton = e.target.closest("[data-format]");
      if (!actionButton) return;
      const format = String(actionButton.dataset.format || "").toLowerCase();
      closeExportMenu();
      void handleExportChat(format);
    });
  }

  /* Search */
  btnSearch.addEventListener("click", openSearch);
  searchClose.addEventListener("click", closeSearch);
  searchInput.addEventListener("input", performSearch);
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "f") {
      e.preventDefault();
      openSearch();
    }
    if (e.key === "Escape" && searchOverlay.classList.contains("open")) closeSearch();
    if (e.key === "Escape") closeExportMenu();
  });

  /* Theme toggle */
  btnTheme.addEventListener("click", toggleTheme);
  applyStoredTheme();

  /* Auth */
  btnLogin.addEventListener("click", async () => {
    if (state.token) {
      await handleLogoutRequested();
      return;
    }
    window.location.href = "/login";
  });

  /* Sidebar toggle */
  sidebarToggle.addEventListener("click", () => {
    if (window.innerWidth <= 860) {
      leftPanel.classList.add("open");
    } else {
      appShell.classList.remove("sidebar-collapsed");
    }
  });
  sidebarClose.addEventListener("click", () => {
    if (window.innerWidth <= 860) {
      leftPanel.classList.remove("open");
    } else {
      appShell.classList.add("sidebar-collapsed");
    }
  });

  /* Close context menu on click outside */
  document.addEventListener("click", (e) => {
    if (!ctxMenu.contains(e.target)) closeCtxMenu();

    if (
      exportMenu
      && btnExportChat
      && !exportMenu.contains(e.target)
      && !btnExportChat.contains(e.target)
    ) {
      closeExportMenu();
    }

    if (
      quickActionsPanel &&
      !quickActionsPanel.classList.contains("collapsed") &&
      !quickActionsPanel.contains(e.target)
    ) {
      quickActionsPanel.classList.add("collapsed");
      quickActionsToggle?.setAttribute("aria-expanded", "false");
      localStorage.setItem("nectar_quick_actions_collapsed", "1");
    }
  });

  /* Context menu actions */
  ctxMenu.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const action = btn.dataset.action;
    const { type, id, chatId } = ctxMenu.dataset;
    closeCtxMenu();
    if (type === "workspace") {
      if (action === "rename") handleRenameWorkspace(id);
      else if (action === "clear-messages") handleClearWorkspaceMessages(id);
      else if (action === "delete") handleDeleteWorkspace(id);
    } else if (type === "document") {
      if (action === "rename") handleRenameDocument(chatId, id);
      else if (action === "delete") handleDeleteDocument(chatId, id);
    }
  });

  /* Warn anonymous */
  window.addEventListener("beforeunload", (e) => {
    if (!shouldWarnAnonymousDataLoss()) return;
    e.preventDefault();
    e.returnValue = UNSAVED_ANONYMOUS_WARNING;
    return UNSAVED_ANONYMOUS_WARNING;
  });
}

/* ================================================================
   AUTH
   ================================================================ */
function handleLogout() {
  state.token = null;
  state.username = null;
  state.guestSessionId = createGuestSessionId();
  state.currentChatId = null;
  state.chats = [];
  state.docs = [];
  state.selectedDocIdsByChat = {};
  state.uploadJobsByChat = {};
  state.activeUploadPolls = {};
  state.uploadMessageIdsByJob = {};
  for (const timerId of Object.values(state.uploadProgressTimersByJob)) {
    window.clearInterval(timerId);
  }
  for (const timerId of Object.values(state.pendingDocsRenderByChat)) {
    window.clearTimeout(timerId);
  }
  state.uploadProgressStateByJob = {};
  state.uploadProgressTimersByJob = {};
  state.pendingDocsRenderByChat = {};
  localStorage.removeItem("auth_token");
  localStorage.removeItem("admin_token");
  localStorage.removeItem("username");
  localStorage.removeItem("user_role");
  localStorage.removeItem(UPLOAD_JOB_STORAGE_KEY);
  localStorage.removeItem(LAST_CHAT_STORAGE_KEY);
  showLoggedOut();
  workspaceList.innerHTML = "";
  docsList.innerHTML = "";
  docsSection.classList.remove("visible");
  if (docsSelectAll) {
    docsSelectAll.checked = false;
    docsSelectAll.indeterminate = false;
    docsSelectAll.disabled = true;
  }
  if (docsDeleteAllBtn) {
    docsDeleteAllBtn.disabled = true;
  }
  clearChat();
  wsTitle.textContent = "Chọn hoặc tạo workspace để bắt đầu";
  statusPill.textContent = "";
}

async function handleLogoutRequested() {
  const confirmed = await showConfirmModal({
    title: "Đăng xuất",
    message: "Bạn có muốn đăng xuất khỏi tài khoản hiện tại không?",
    confirmText: "Đăng xuất",
    cancelText: "Ở lại",
    confirmVariant: "danger",
  });
  if (!confirmed) return;
  handleLogout();
}

function showLoggedIn() {
  btnLogin.classList.add("logged-in");
  const loginText = btnLogin.querySelector(".login-text");
  loginText.textContent = state.username;
  loginText.title = state.username;
  btnLogin.querySelector(".login-sub").textContent = "Nhấn để đăng xuất";
  btnLogin.querySelector(".login-arrow").textContent = "⏻";
  updateGuestWarningVisibility();
}

function showLoggedOut() {
  btnLogin.classList.remove("logged-in");
  const loginText = btnLogin.querySelector(".login-text");
  loginText.textContent = "Login";
  loginText.title = "";
  btnLogin.querySelector(".login-sub").textContent = "Đồng bộ phiên làm việc";
  btnLogin.querySelector(".login-arrow").textContent = "→";
  updateGuestWarningVisibility();
}

/* ================================================================
   WORKSPACE CRUD
   ================================================================ */
async function loadWorkspaces() {
  try {
    const res = await apiFetch("/api/v1/workspace/chats");
    const data = await res.json();
    state.chats = data.chats || [];
    renderWorkspaceList();
    // Load doc counts for all workspaces
    await loadAllDocCounts();
    await refreshWorkspaceUploadActivity();

    const lastChatId = localStorage.getItem(LAST_CHAT_STORAGE_KEY);
    if (lastChatId && state.chats.some((chat) => chat.chat_id === lastChatId)) {
      await selectWorkspace(lastChatId);
    } else if (!state.currentChatId && state.chats.length > 0) {
      await selectWorkspace(state.chats[0].chat_id);
    }
  } catch { /* silent */ }
}

function countActiveUploadEntriesFromJobs(jobs) {
  let total = 0;
  for (const rawJob of Array.isArray(jobs) ? jobs : []) {
    const job = normalizeTrackedUploadJob(rawJob);
    if (!job) continue;
    if (isUploadTerminalStatus(job.status)) continue;

    const fileCount = Array.isArray(job.original_names) && job.original_names.length
      ? job.original_names.length
      : 1;
    total += Math.max(1, fileCount);
  }
  return total;
}

async function refreshWorkspaceUploadActivity() {
  if (!state.chats.length) return;

  const snapshots = await Promise.all(
    state.chats.map(async (chat) => {
      const activeJobs = await fetchUploadJobsForChat(chat.chat_id, {
        includeTerminal: false,
        limit: UPLOAD_JOB_TRACK_LIMIT_PER_CHAT,
      });
      return {
        chatId: chat.chat_id,
        activeCount: countActiveUploadEntriesFromJobs(activeJobs),
      };
    })
  );

  for (const snapshot of snapshots) {
    const chat = state.chats.find((item) => item.chat_id === snapshot.chatId);
    if (!chat) continue;
    chat._activeUploadCount = snapshot.activeCount;
  }

  renderWorkspaceList();
}

async function loadAllDocCounts() {
  const promises = state.chats.map(async (chat) => {
    try {
      const res = await apiFetch(`/api/v1/workspace/chats/${chat.chat_id}/documents`);
      const data = await res.json();
      chat._docCount = (data.documents || []).length;
    } catch { chat._docCount = 0; }
  });
  await Promise.all(promises);
  renderWorkspaceList();
}

function renderWorkspaceList() {
  workspaceList.innerHTML = "";
  const icons = ["📊", "📁", "📝", "📋", "📑", "📂", "🗂", "📄"];
  state.chats.forEach((chat, idx) => {
    const el = document.createElement("div");
    el.className = "ws-item" + (chat.chat_id === state.currentChatId ? " active" : "");
    const icon = icons[idx % icons.length];
    const docCount = chat._docCount || 0;
    const activeUploadCount = Number(chat._activeUploadCount || 0);
    const activityLabel = chat.chat_id === state.currentChatId ? "Đang hoạt động" : "Sẵn sàng";
    const uploadHint = activeUploadCount > 0 ? ` · ${activeUploadCount} đang xử lý nền` : "";
    el.innerHTML = `
      <div class="ws-item-icon">${icon}</div>
      <div class="ws-item-meta">
        <div class="ws-item-title">${escapeHtml(chat.title)}</div>
        <div class="ws-item-sub">${docCount} tài liệu${uploadHint} · ${activityLabel}</div>
      </div>
      <button class="ws-item-actions" data-chat-id="${chat.chat_id}" title="Tùy chọn">⋯</button>
    `;
    el.querySelector(".ws-item-meta").addEventListener("click", () => selectWorkspace(chat.chat_id));
    el.querySelector(".ws-item-icon").addEventListener("click", () => selectWorkspace(chat.chat_id));
    el.querySelector(".ws-item-actions").addEventListener("click", (e) => {
      e.stopPropagation();
      openCtxMenu(e, "workspace", chat.chat_id);
    });
    workspaceList.appendChild(el);
  });
}

async function handleCreateWorkspace() {
  const title = await showPromptModal({
    title: "Tạo Workspace",
    message: "Nhập tên cho workspace mới.",
    label: "Tên workspace",
    placeholder: "Ví dụ: Kế hoạch học tập",
    defaultValue: "Workspace mới",
    confirmText: "Tạo mới",
  });
  if (!title) return;
  try {
    const res = await apiFetch("/api/v1/workspace/chats", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    const data = await res.json();
    state.chats.unshift({ chat_id: data.chat_id, title: data.title, created_at: data.created_at, _docCount: 0 });
    selectWorkspace(data.chat_id);
    renderWorkspaceList();
  } catch (err) {
    await showAlertModal({
      title: "Tạo Workspace Thất Bại",
      message: "Không thể tạo workspace: " + err.message,
      confirmText: "Đã hiểu",
    });
  }
}

async function selectWorkspace(chatId) {
  state.currentChatId = chatId;
  localStorage.setItem(LAST_CHAT_STORAGE_KEY, chatId);
  const chat = state.chats.find((c) => c.chat_id === chatId);

  wsTitle.textContent = "Không gian làm việc: " + (chat ? chat.title : chatId);
  renderWorkspaceList();
  clearChat();

  // Load documents
  await loadDocsForChat(chatId);
  renderWorkspaceList(); // re-render with updated doc count
  // Load messages
  await loadMessagesForChat(chatId);
  await restoreTrackedUploadJobsForChat(chatId);

  // Update upload button label
  const idx = state.chats.findIndex((c) => c.chat_id === chatId);
  btnUploadLabel.childNodes[0].textContent = `Tải vào workspace ${String(idx + 1).padStart(2, "0")} `;

  leftPanel.classList.remove("open");
}

async function loadDocsForChat(chatId) {
  try {
    const res = await apiFetch(`/api/v1/workspace/chats/${chatId}/documents`);
    const data = await res.json();
    state.docs = data.documents || [];
    syncAskFromSelectionForCurrentChat();
    renderDocsList();
  } catch {
    state.docs = [];
    syncAskFromSelectionForCurrentChat();
    renderDocsList();
  }
}

async function loadMessagesForChat(chatId) {
  try {
    const res = await apiFetch(`/api/v1/workspace/chats/${chatId}/messages`);
    const data = await res.json();
    const msgs = data.messages || [];
    if (msgs.length === 0) {
      appendAssistantMessage("Xin chào! Hãy tải tài liệu lên workspace này và đặt câu hỏi để bắt đầu.");
    }
    msgs.forEach((msg) => {
      if (msg.role === "user") {
        appendUserMessage(msg.content);
      } else {
        appendAssistantMessage(msg.content);
      }
    });
    updateStatusPill();
  } catch { /* silent */ }
}

function renderDocsList() {
  docsList.innerHTML = "";
  const pendingUploads = getPendingUploadEntriesForChat(state.currentChatId);
  if (!state.docs.length && !pendingUploads.length) {
    docsSection.classList.remove("visible");
    if (docsSelectAll) {
      docsSelectAll.checked = false;
      docsSelectAll.indeterminate = false;
      docsSelectAll.disabled = true;
      docsSelectAll.onchange = null;
    }
    if (docsDeleteAllBtn) {
      docsDeleteAllBtn.disabled = true;
    }
    return;
  }

  docsSection.classList.add("visible");
  const idx = state.chats.findIndex((c) => c.chat_id === state.currentChatId);
  const pendingCount = pendingUploads.length;
  docsLabel.textContent = pendingCount
    ? `Tài liệu trong workspace ${String(idx + 1).padStart(2, "0")} (${state.docs.length} đã phân tích, ${pendingCount} đang xử lý)`
    : `Tài liệu trong workspace ${String(idx + 1).padStart(2, "0")} (${state.docs.length})`;
  if (docsSelectionGuide) {
    docsSelectionGuide.textContent = pendingCount
      ? "Hướng dẫn: tick vào ô vuông ở từng tài liệu để AI chỉ trả lời trong tài liệu đã chọn. Tài liệu đang xử lý sẽ tự cập nhật khi hoàn tất."
      : "Hướng dẫn: tick vào ô vuông ở từng tài liệu để AI chỉ trả lời trong tài liệu đã chọn.";
  }

  const selectedSet = new Set(getSelectedDocIdsForCurrentChat());
  if (docsSelectAll) {
    docsSelectAll.disabled = state.docs.length === 0;
    docsSelectAll.checked = state.docs.length > 0 && selectedSet.size === state.docs.length;
    docsSelectAll.indeterminate = selectedSet.size > 0 && selectedSet.size < state.docs.length;
    docsSelectAll.onchange = () => {
      if (docsSelectAll.checked) {
        setSelectedDocIdsForCurrentChat(state.docs.map((doc) => doc.document_id));
      } else {
        setSelectedDocIdsForCurrentChat([]);
      }
      renderDocsList();
      updateStatusPill();
    };
  }
  if (docsDeleteAllBtn) {
    docsDeleteAllBtn.disabled = state.docs.length === 0;
  }

  state.docs.forEach((doc, index) => {
    const uploadIndex = Number(doc.upload_index) || index + 1;
    const el = document.createElement("div");
    el.className = "doc-item";
    el.innerHTML = `
      <div class="doc-scope-wrap">
        <input type="checkbox" class="doc-scope-checkbox" aria-label="Chọn tài liệu ${escapeHtml(doc.original_name)}" />
      </div>
      <div class="doc-icon-wrap">
        <svg viewBox="0 0 24 24" fill="none"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="#0D9488" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><polyline points="14 2 14 8 20 8" stroke="#0D9488" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </div>
      <div class="doc-meta">
        <div class="doc-name">${escapeHtml(doc.original_name)}</div>
        <div class="doc-status">Tài liệu ${String(uploadIndex).padStart(2, "0")} · Đã phân tích</div>
      </div>
      <button class="doc-item-actions" title="Tùy chọn">⋯</button>
    `;

    const scopeCheckbox = el.querySelector(".doc-scope-checkbox");
    scopeCheckbox.checked = selectedSet.has(doc.document_id);
    scopeCheckbox.addEventListener("change", () => {
      const nextSelection = new Set(getSelectedDocIdsForCurrentChat());
      if (scopeCheckbox.checked) {
        nextSelection.add(doc.document_id);
      } else {
        nextSelection.delete(doc.document_id);
      }
      setSelectedDocIdsForCurrentChat(Array.from(nextSelection));
      renderDocsList();
      updateStatusPill();
    });

    const toggleScope = () => {
      scopeCheckbox.checked = !scopeCheckbox.checked;
      scopeCheckbox.dispatchEvent(new Event("change"));
    };
    el.querySelector(".doc-icon-wrap").addEventListener("click", toggleScope);
    el.querySelector(".doc-meta").addEventListener("click", toggleScope);

    el.querySelector(".doc-item-actions").addEventListener("click", (e) => {
      e.stopPropagation();
      openCtxMenu(e, "document", doc.document_id, state.currentChatId);
    });

    docsList.appendChild(el);
  });

  const indexedNames = new Set(
    state.docs
      .map((doc) => String(doc.original_name || "").trim().toLowerCase())
      .filter(Boolean)
  );

  for (const pending of pendingUploads) {
    const pendingName = String(pending?.name || "").trim();
    if (!pendingName) continue;
    const pendingProgress = Math.min(99, clampUploadProgress(pending?.progress));
    const pendingStage = mapUploadStage(pending?.stage || "processing");

    const normalizedName = pendingName.toLowerCase();
    if (indexedNames.has(normalizedName)) continue;
    indexedNames.add(normalizedName);

    const el = document.createElement("div");
    el.className = "doc-item doc-item-pending";
    el.innerHTML = `
      <div class="doc-scope-wrap doc-scope-placeholder"></div>
      <div class="doc-icon-wrap">
        <svg viewBox="0 0 24 24" fill="none"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="#0D9488" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><polyline points="14 2 14 8 20 8" stroke="#0D9488" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </div>
      <div class="doc-meta">
        <div class="doc-name">${escapeHtml(pendingName)}</div>
        <div class="doc-status">${escapeHtml(pendingStage)} (${pendingProgress}%)</div>
        <div class="doc-progress" aria-hidden="true"><span style="width:${pendingProgress}%"></span></div>
      </div>
      <div class="doc-badge loading" aria-hidden="true">⟳</div>
    `;
    docsList.appendChild(el);
  }

  // Update chat doc count
  const chat = state.chats.find((c) => c.chat_id === state.currentChatId);
  if (chat) chat._docCount = state.docs.length;
  updateStatusPill();
}

function updateStatusPill() {
  const docCount = state.docs.length;
  const pendingCount = getPendingUploadEntriesForChat(state.currentChatId).length;

  if (docCount > 0) {
    const selectedCount = getSelectedDocIdsForCurrentChat().length;
    statusPill.textContent = pendingCount > 0
      ? `Sẵn sàng trả lời từ ${selectedCount}/${docCount} tài liệu · ${pendingCount} tài liệu đang xử lý nền`
      : `Sẵn sàng trả lời từ ${selectedCount}/${docCount} tài liệu`;
  } else if (pendingCount > 0) {
    statusPill.textContent = `${pendingCount} tài liệu đang xử lý nền`;
  } else {
    statusPill.textContent = "";
  }
}

function getSelectedDocIdsForCurrentChat() {
  if (!state.currentChatId) return [];
  const selected = state.selectedDocIdsByChat[state.currentChatId];
  if (!Array.isArray(selected)) return [];
  return selected;
}

function setSelectedDocIdsForCurrentChat(documentIds) {
  if (!state.currentChatId) return;
  const validIds = new Set(state.docs.map((doc) => String(doc.document_id || "").trim()).filter(Boolean));
  const normalized = [];
  const seen = new Set();

  for (const rawId of documentIds || []) {
    const id = String(rawId || "").trim();
    if (!id || !validIds.has(id) || seen.has(id)) continue;
    seen.add(id);
    normalized.push(id);
  }

  state.selectedDocIdsByChat[state.currentChatId] = normalized;
}

function syncAskFromSelectionForCurrentChat() {
  if (!state.currentChatId) return;

  const currentSelected = getSelectedDocIdsForCurrentChat();
  setSelectedDocIdsForCurrentChat(currentSelected);

  if (!getSelectedDocIdsForCurrentChat().length && state.docs.length) {
    setSelectedDocIdsForCurrentChat(state.docs.map((doc) => doc.document_id));
  }
}

function normalizeTrackedUploadJob(job) {
  const jobId = String(job?.job_id || "").trim();
  if (!jobId) return null;

  const retryCount = Number(job?.retry_count);
  const maxRetries = Number(job?.max_retries);
  const progress = Number(job?.progress);
  const normalizedStatus = String(job?.status || "queued").toLowerCase();

  return {
    job_id: jobId,
    status: normalizedStatus,
    stage: String(job?.stage || ""),
    progress: Number.isFinite(progress) ? Math.max(0, Math.min(100, progress)) : 0,
    original_names: Array.isArray(job?.original_names)
      ? job.original_names.map((name) => String(name || "").trim()).filter(Boolean)
      : [],
    retry_count: Number.isFinite(retryCount) ? retryCount : 0,
    max_retries: Number.isFinite(maxRetries) ? maxRetries : 0,
    can_retry: typeof job?.can_retry === "boolean"
      ? job.can_retry
      : (normalizedStatus === "failed" && (Number.isFinite(retryCount) ? retryCount : 0) < (Number.isFinite(maxRetries) ? maxRetries : 0)),
    error: String(job?.error || "").trim(),
    message: String(job?.message || "").trim(),
    updated_at: String(job?.updated_at || new Date().toISOString()),
  };
}

function isUploadTerminalStatus(status) {
  const value = String(status || "").toLowerCase();
  return value === "completed" || value === "failed";
}

function persistTrackedUploadJobsToStorage() {
  try {
    localStorage.setItem(UPLOAD_JOB_STORAGE_KEY, JSON.stringify(state.uploadJobsByChat || {}));
  } catch {
    /* Ignore storage quota and private mode errors. */
  }
}

function getTrackedUploadJobsForChat(chatId) {
  if (!chatId) return [];
  const list = state.uploadJobsByChat?.[chatId];
  return Array.isArray(list) ? list : [];
}

function setTrackedUploadJobsForChat(chatId, jobs) {
  if (!chatId) return;
  const chat = state.chats.find((item) => item.chat_id === chatId);
  const previousActiveCount = Number(chat?._activeUploadCount || 0);

  const normalized = (Array.isArray(jobs) ? jobs : [])
    .map(normalizeTrackedUploadJob)
    .filter(Boolean)
    .slice(0, UPLOAD_JOB_TRACK_LIMIT_PER_CHAT);

  if (!normalized.length) {
    delete state.uploadJobsByChat[chatId];
  } else {
    state.uploadJobsByChat[chatId] = normalized;
  }

  if (chat) {
    chat._activeUploadCount = countActiveUploadEntriesFromJobs(normalized);
  }

  persistTrackedUploadJobsToStorage();

  if (chat && previousActiveCount !== chat._activeUploadCount) {
    renderWorkspaceList();
  }
}

function upsertTrackedUploadJob(chatId, job) {
  const normalized = normalizeTrackedUploadJob(job);
  if (!chatId || !normalized) return;

  const jobId = normalized.job_id;

  const current = getTrackedUploadJobsForChat(chatId);
  const next = current.filter((item) => String(item?.job_id || "").trim() !== jobId);
  next.unshift(normalized);

  setTrackedUploadJobsForChat(chatId, next);
}

function removeTrackedUploadJob(chatId, jobId) {
  const normalizedJobId = String(jobId || "").trim();
  if (!chatId || !normalizedJobId) return;

  const current = getTrackedUploadJobsForChat(chatId);
  const next = current.filter((item) => String(item?.job_id || "").trim() !== normalizedJobId);
  setTrackedUploadJobsForChat(chatId, next);
  delete state.uploadMessageIdsByJob[buildUploadPollKey(chatId, normalizedJobId)];
  clearUploadProgressRuntime(chatId, normalizedJobId);
}

function buildUploadPollKey(chatId, jobId) {
  return `${String(chatId || "").trim()}::${String(jobId || "").trim()}`;
}

function isUploadPollActive(chatId, jobId) {
  const key = buildUploadPollKey(chatId, jobId);
  return Boolean(state.activeUploadPolls[key]);
}

function setUploadPollActive(chatId, jobId, active) {
  const key = buildUploadPollKey(chatId, jobId);
  if (!key || key === "::") return;
  if (active) {
    state.activeUploadPolls[key] = true;
    return;
  }
  delete state.activeUploadPolls[key];
}

function clampUploadProgress(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  return Math.max(0, Math.min(100, numeric));
}

function schedulePendingDocsRefresh(chatId) {
  const normalizedChatId = String(chatId || "").trim();
  if (!normalizedChatId || state.currentChatId !== normalizedChatId) return;
  if (state.pendingDocsRenderByChat[normalizedChatId]) return;

  state.pendingDocsRenderByChat[normalizedChatId] = window.setTimeout(() => {
    delete state.pendingDocsRenderByChat[normalizedChatId];
    if (state.currentChatId !== normalizedChatId) return;
    renderDocsList();
  }, 90);
}

function setUploadProgressRuntime(chatId, jobId, payload = {}) {
  const key = buildUploadPollKey(chatId, jobId);
  if (!key || key === "::") return;

  const existing = state.uploadProgressStateByJob[key] || {
    displayProgress: 0,
    targetProgress: 0,
    stage: "queued",
    lastRenderedText: "",
    messageId: "",
  };

  const nextTarget = clampUploadProgress(payload.progress);
  const currentDisplay = clampUploadProgress(existing.displayProgress);
  existing.displayProgress = currentDisplay;
  existing.targetProgress = Math.max(existing.targetProgress || 0, nextTarget);
  if (payload.stage) {
    existing.stage = String(payload.stage || "processing");
  }
  if (payload.messageId) {
    existing.messageId = String(payload.messageId || "").trim();
  }

  state.uploadProgressStateByJob[key] = existing;
  runUploadProgressTween(chatId, jobId);
}

function clearUploadProgressRuntime(chatId, jobId) {
  const key = buildUploadPollKey(chatId, jobId);
  if (!key || key === "::") return;

  const timerId = state.uploadProgressTimersByJob[key];
  if (timerId) {
    window.clearInterval(timerId);
    delete state.uploadProgressTimersByJob[key];
  }
  delete state.uploadProgressStateByJob[key];
}

function runUploadProgressTween(chatId, jobId) {
  const key = buildUploadPollKey(chatId, jobId);
  if (!key || key === "::") return;
  if (state.uploadProgressTimersByJob[key]) return;

  const tick = () => {
    const runtime = state.uploadProgressStateByJob[key];
    if (!runtime) {
      const timerId = state.uploadProgressTimersByJob[key];
      if (timerId) {
        window.clearInterval(timerId);
        delete state.uploadProgressTimersByJob[key];
      }
      return;
    }

    const current = clampUploadProgress(runtime.displayProgress);
    const target = clampUploadProgress(runtime.targetProgress);

    let next = current;
    if (target > current) {
      const gap = target - current;
      const step = Math.max(1, Math.ceil(gap * 0.24));
      next = Math.min(target, current + step);
    }

    runtime.displayProgress = next;

    const messageId = getUploadJobMessageId(chatId, jobId) || String(runtime.messageId || "");
    if (messageId) {
      const progressText = `${mapUploadStage(runtime.stage || "processing")} (${Math.round(next)}%)`;
      if (progressText !== runtime.lastRenderedText) {
        replaceAssistantMessagePlainText(messageId, progressText);
        runtime.lastRenderedText = progressText;
      }
    }

    schedulePendingDocsRefresh(chatId);

    if (next >= target) {
      const timerId = state.uploadProgressTimersByJob[key];
      if (timerId) {
        window.clearInterval(timerId);
        delete state.uploadProgressTimersByJob[key];
      }
    }
  };

  state.uploadProgressTimersByJob[key] = window.setInterval(tick, 80);
  tick();
}

function getUploadDisplayProgress(chatId, job) {
  const jobId = String(job?.job_id || "").trim();
  if (!chatId || !jobId) return clampUploadProgress(job?.progress);

  const runtime = state.uploadProgressStateByJob[buildUploadPollKey(chatId, jobId)];
  if (runtime) {
    return clampUploadProgress(runtime.displayProgress);
  }
  return clampUploadProgress(job?.progress);
}

function getUploadDisplayStage(chatId, job) {
  const jobId = String(job?.job_id || "").trim();
  if (!chatId || !jobId) return String(job?.stage || job?.status || "processing");

  const runtime = state.uploadProgressStateByJob[buildUploadPollKey(chatId, jobId)];
  if (runtime?.stage) {
    return String(runtime.stage);
  }
  return String(job?.stage || job?.status || "processing");
}

function getUploadJobMessageId(chatId, jobId) {
  const key = buildUploadPollKey(chatId, jobId);
  const messageId = state.uploadMessageIdsByJob[key];
  if (!messageId) return "";
  if (!chatTimeline.querySelector(`[data-msg-id="${messageId}"]`)) {
    delete state.uploadMessageIdsByJob[key];
    return "";
  }
  return messageId;
}

function bindMessageToUploadJob(messageId, chatId, jobId) {
  const normalizedMessageId = String(messageId || "").trim();
  const key = buildUploadPollKey(chatId, jobId);
  if (!normalizedMessageId || !key || key === "::") return;

  state.uploadMessageIdsByJob[key] = normalizedMessageId;
  const message = chatTimeline.querySelector(`[data-msg-id="${normalizedMessageId}"]`);
  if (message) {
    message.dataset.uploadJobKey = key;
  }
}

async function fetchUploadJobsForChat(chatId, { includeTerminal = true, limit = UPLOAD_JOB_TRACK_LIMIT_PER_CHAT } = {}) {
  if (!chatId) return [];

  try {
    const query = new URLSearchParams({
      limit: String(limit),
      include_terminal: includeTerminal ? "true" : "false",
    });
    const res = await apiFetch(`/api/v1/workspace/chats/${chatId}/upload-jobs?${query.toString()}`);
    const { payload } = await parseApiPayload(res);
    if (!res.ok) return [];

    const jobs = Array.isArray(payload?.jobs) ? payload.jobs : [];
    return jobs.map(normalizeTrackedUploadJob).filter(Boolean);
  } catch {
    return [];
  }
}

function mergeTrackedAndServerUploadJobs(trackedJobs, serverJobs) {
  const merged = new Map();

  for (const rawJob of Array.isArray(trackedJobs) ? trackedJobs : []) {
    const job = normalizeTrackedUploadJob(rawJob);
    if (!job) continue;
    merged.set(job.job_id, job);
  }

  for (const rawJob of Array.isArray(serverJobs) ? serverJobs : []) {
    const job = normalizeTrackedUploadJob(rawJob);
    if (!job) continue;
    merged.set(job.job_id, job);
  }

  return Array.from(merged.values()).sort((left, right) => {
    const rightTime = Date.parse(String(right?.updated_at || "")) || 0;
    const leftTime = Date.parse(String(left?.updated_at || "")) || 0;
    return rightTime - leftTime;
  });
}

function getPendingUploadEntriesForChat(chatId) {
  const entries = [];
  for (const job of getTrackedUploadJobsForChat(chatId)) {
    const status = String(job?.status || "queued").toLowerCase();
    if (isUploadTerminalStatus(status)) continue;

    const displayProgress = Math.min(99, clampUploadProgress(getUploadDisplayProgress(chatId, job)));
    const displayStage = getUploadDisplayStage(chatId, job);

    const names = Array.isArray(job?.original_names) && job.original_names.length
      ? job.original_names
      : ["Tài liệu đang xử lý"];

    for (const name of names) {
      entries.push({
        job_id: String(job?.job_id || "").trim(),
        name: String(name || "").trim() || "Tài liệu đang xử lý",
        stage: displayStage,
        progress: displayProgress,
      });
    }
  }
  return entries;
}

function ensureUploadJobMessage({
  chatId,
  jobId,
  status,
  originalNames,
  error,
  canRetry,
  retryCount,
  maxRetries,
}) {
  const existingMessageId = getUploadJobMessageId(chatId, jobId);
  if (existingMessageId) return existingMessageId;

  const normalizedStatus = String(status || "queued").toLowerCase();
  let messageText = buildUploadQueuedMessage(originalNames);
  if (normalizedStatus === "failed") {
    messageText = buildUploadFailedMessage({
      chatId,
      jobId,
      detail: error || "Upload thất bại",
      canRetry,
      retryCount,
      maxRetries,
    });
  }

  const messageId = appendAssistantMessage(messageText);
  bindMessageToUploadJob(messageId, chatId, jobId);
  return messageId;
}

async function restoreTrackedUploadJobsForChat(chatId) {
  if (!chatId) return;

  const trackedJobs = getTrackedUploadJobsForChat(chatId);
  const serverJobs = await fetchUploadJobsForChat(chatId, {
    includeTerminal: true,
    limit: UPLOAD_JOB_TRACK_LIMIT_PER_CHAT,
  });
  const mergedJobs = mergeTrackedAndServerUploadJobs(trackedJobs, serverJobs);
  setTrackedUploadJobsForChat(chatId, mergedJobs);

  if (state.currentChatId === chatId) {
    renderDocsList();
  }

  for (const job of mergedJobs) {
    const jobId = String(job?.job_id || "").trim();
    if (!jobId) continue;

    const status = String(job?.status || "queued").toLowerCase();
    const originalNames = Array.isArray(job?.original_names) ? job.original_names : [];

    if (status === "completed") {
      clearUploadProgressRuntime(chatId, jobId);
      removeTrackedUploadJob(chatId, jobId);
      continue;
    }

    const messageId = ensureUploadJobMessage({
      chatId,
      jobId,
      status,
      originalNames,
      error: String(job?.error || job?.message || "").trim(),
      canRetry: Boolean(job?.can_retry),
      retryCount: Number(job?.retry_count || 0),
      maxRetries: Number(job?.max_retries || 0),
    });

    if (status === "failed") {
      clearUploadProgressRuntime(chatId, jobId);
      continue;
    }

    setUploadProgressRuntime(chatId, jobId, {
      progress: Number(job?.progress || 0),
      stage: String(job?.stage || status || "queued"),
      messageId,
    });

    void trackUploadJob({
      chatId,
      jobId,
      originalNames,
      messageId,
    });
  }
}

/* ================================================================
   UPLOAD
   ================================================================ */
async function handleUpload(event) {
  const files = Array.from(event.target.files ?? []);
  if (!files.length) return;
  handleUploadFiles(files);
  // Reset both file inputs so the same file can be re-selected
  fileInput.value = "";
  composerFileInput.value = "";
}

function buildDuplicateUploadSummary(duplicates) {
  const safeDuplicates = Array.isArray(duplicates) ? duplicates : [];
  if (!safeDuplicates.length) return "";

  const preview = safeDuplicates.slice(0, 3)
    .map((item) => {
      const uploadedName = String(item?.uploaded_name || "File mới");
      const existingName = String(item?.existing_original_name || "Tài liệu hiện có");
      return `- ${uploadedName} -> ${existingName}`;
    })
    .join("\n");

  if (safeDuplicates.length <= 3) return preview;
  return `${preview}\n- ... và ${safeDuplicates.length - 3} file trùng khác`;
}

async function resolveDuplicateUploadAction(payload) {
  const duplicates = Array.isArray(payload?.duplicates) ? payload.duplicates : [];
  const allowKeepBoth = payload?.allow_keep_both !== false;
  const summary = buildDuplicateUploadSummary(duplicates);

  const replaceConfirmed = await showConfirmModal({
    title: "Phát Hiện File Trùng Nội Dung",
    message: summary
      ? `Các file sau đã tồn tại theo nội dung SHA256:\n${summary}\n\nBạn muốn Replace tài liệu cũ bằng bản mới không?`
      : "File tải lên đã tồn tại theo nội dung SHA256. Bạn muốn Replace tài liệu cũ bằng bản mới không?",
    confirmText: "Replace",
    cancelText: allowKeepBoth ? "Tùy chọn khác" : "Hủy upload",
    confirmVariant: "danger",
  });
  if (replaceConfirmed) return "replace";

  if (!allowKeepBoth) {
    return "cancel";
  }

  const keepBothConfirmed = await showConfirmModal({
    title: "Giữ Cả Hai Bản",
    message: "Bạn muốn giữ cả tài liệu cũ và bản mới (Keep both)? Hệ thống sẽ vẫn indexing bản mới.",
    confirmText: "Keep both",
    cancelText: "Cancel upload",
  });

  return keepBothConfirmed ? "keep_both" : "cancel";
}

async function handleUploadFiles(files, options = {}) {
  if (!files.length) return;

  const duplicateAction = String(options.duplicateAction || "cancel");
  const showTempItems = options.showTempItems !== false;

  if (!state.currentChatId) {
    await showAlertModal({
      title: "Thiếu Workspace",
      message: "Hãy chọn hoặc tạo workspace trước khi tải tài liệu.",
      confirmText: "Đã rõ",
    });
    return;
  }

  const uploadChatId = state.currentChatId;

  // Add temp doc items
  if (showTempItems) {
    files.forEach((f) => addTempDoc(f.name));
  }

  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));
  formData.append("duplicate_action", duplicateAction);

  try {
    const res = await apiFetch(`/api/v1/workspace/chats/${uploadChatId}/upload`, {
      method: "POST",
      body: formData,
    });
    const { payload, text } = await parseApiPayload(res);
    if (!res.ok) {
      throw new Error(
        payload?.detail || payload?.message || text || `Upload thất bại (HTTP ${res.status})`
      );
    }

    if (payload?.status === "duplicate") {
      if (state.currentChatId === uploadChatId) {
        await loadDocsForChat(uploadChatId);
      }

      if (duplicateAction !== "cancel") {
        appendAssistantMessage("Không thể xử lý file trùng lặp với lựa chọn hiện tại. Vui lòng thử lại.");
        return;
      }

      const nextAction = await resolveDuplicateUploadAction(payload);
      if (nextAction === "cancel") {
        appendAssistantMessage("Đã hủy upload vì file trùng nội dung.");
        return;
      }

      await handleUploadFiles(files, {
        duplicateAction: nextAction,
        showTempItems: false,
      });
      return;
    }

    const originalNames = (payload?.original_names && payload.original_names.length)
      ? payload.original_names
      : files.map((file) => file.name);

    if (payload?.job_id) {
      upsertTrackedUploadJob(uploadChatId, {
        job_id: payload.job_id,
        status: payload.status || "queued",
        stage: payload.stage || payload.status || "queued",
        progress: Number(payload.progress || 0),
        original_names: originalNames,
        retry_count: payload.retry_count,
        max_retries: payload.max_retries,
      });

      const progressMessageId = appendAssistantMessage(buildUploadQueuedMessage(originalNames));
      bindMessageToUploadJob(progressMessageId, uploadChatId, payload.job_id);
      setUploadProgressRuntime(uploadChatId, payload.job_id, {
        progress: Number(payload.progress || 0),
        stage: payload.stage || payload.status || "queued",
        messageId: progressMessageId,
      });
      void trackUploadJob({
        chatId: uploadChatId,
        jobId: payload.job_id,
        originalNames,
        messageId: progressMessageId,
      });
      return;
    }

    appendAssistantMessage(
      buildUploadSuccessMessage(originalNames)
    );
    state.hasChatActivity = true;
    if (state.currentChatId === uploadChatId) {
      await loadDocsForChat(uploadChatId);
    }
    removeTrackedUploadJob(uploadChatId, payload?.job_id);
    await loadAllDocCounts();
  } catch (err) {
    appendAssistantMessage(`Không thể tải tài liệu: ${err.message}`);
    if (state.currentChatId === uploadChatId) {
      await loadDocsForChat(uploadChatId);
    }
  }
}

async function trackUploadJob({ chatId, jobId, originalNames, messageId }) {
  if (!chatId || !jobId) return;

  if (messageId) {
    bindMessageToUploadJob(messageId, chatId, jobId);
    setUploadProgressRuntime(chatId, jobId, {
      progress: 0,
      stage: "queued",
      messageId,
    });
  }

  if (isUploadPollActive(chatId, jobId)) return;

  setUploadPollActive(chatId, jobId, true);
  try {
    const result = await pollUploadJob({
      chatId,
      jobId,
      originalNames,
    });

    if (result.status === "completed") {
      clearUploadProgressRuntime(chatId, jobId);
      state.hasChatActivity = true;
      removeTrackedUploadJob(chatId, jobId);
      if (state.currentChatId === chatId) {
        await loadDocsForChat(chatId);
      }
      await loadAllDocCounts();
      return;
    }

    if (result.status === "failed") {
      clearUploadProgressRuntime(chatId, jobId);
      const payload = result.payload || {};
      upsertTrackedUploadJob(chatId, {
        job_id: jobId,
        status: "failed",
        stage: payload?.stage || "failed",
        progress: Number(payload?.progress || 0),
        original_names: payload?.original_names || originalNames,
        retry_count: payload?.retry_count,
        max_retries: payload?.max_retries,
        updated_at: payload?.updated_at,
      });
      if (state.currentChatId === chatId) {
        renderDocsList();
      }
      return;
    }

    if (result.status === "not_found") {
      clearUploadProgressRuntime(chatId, jobId);
      removeTrackedUploadJob(chatId, jobId);
      if (state.currentChatId === chatId) {
        renderDocsList();
      }
      return;
    }

    if (result.status === "timeout") {
      if (state.currentChatId === chatId) {
        renderDocsList();
      }
      return;
    }

    const payload = result.payload || {};
    upsertTrackedUploadJob(chatId, {
      job_id: jobId,
      status: payload?.status || "processing",
      stage: payload?.stage || payload?.status || "processing",
      progress: Number(payload?.progress || 0),
      original_names: payload?.original_names || originalNames,
      retry_count: payload?.retry_count,
      max_retries: payload?.max_retries,
      updated_at: payload?.updated_at,
    });
  } catch (err) {
    clearUploadProgressRuntime(chatId, jobId);
    const boundMessageId = getUploadJobMessageId(chatId, jobId) || String(messageId || "");
    if (boundMessageId) {
      replaceAssistantMessage(boundMessageId, `Không thể đọc tiến độ upload: ${err.message}`);
    }
    upsertTrackedUploadJob(chatId, {
      job_id: jobId,
      status: "processing",
      stage: "processing",
      original_names: originalNames,
    });
    if (state.currentChatId === chatId) {
      renderDocsList();
    }
  } finally {
    setUploadPollActive(chatId, jobId, false);
  }
}

async function pollUploadJob({ chatId, jobId, originalNames }) {
  const startedAt = Date.now();
  const updateBoundMessage = (text) => {
    const boundMessageId = getUploadJobMessageId(chatId, jobId);
    if (!boundMessageId) return;
    replaceAssistantMessage(boundMessageId, text);
  };

  while (Date.now() - startedAt < UPLOAD_JOB_POLL_TIMEOUT_MS) {
    const res = await apiFetch(`/api/v1/workspace/chats/${chatId}/upload-jobs/${jobId}`);
    const { payload, text } = await parseApiPayload(res);
    if (!res.ok) {
      if (res.status === 404) {
        clearUploadProgressRuntime(chatId, jobId);
        updateBoundMessage("Không còn tìm thấy upload job. Có thể job đã bị dọn dẹp.");
        return { status: "not_found", payload: null };
      }
      throw new Error(
        payload?.detail || payload?.message || text || `Không đọc được tiến độ upload (HTTP ${res.status})`
      );
    }

    const status = String(payload?.status || "processing");
    const progress = Number.isFinite(payload?.progress) ? payload.progress : 0;

    if (status === "completed") {
      clearUploadProgressRuntime(chatId, jobId);
      updateBoundMessage(buildUploadSuccessMessage(payload?.original_names || originalNames));
      return { status: "completed", payload };
    }

    if (status === "failed") {
      clearUploadProgressRuntime(chatId, jobId);
      const detail = payload?.error || payload?.message || "Upload thất bại";
      updateBoundMessage(
        buildUploadFailedMessage({
          chatId,
          jobId,
          detail,
          canRetry: Boolean(payload?.can_retry),
          retryCount: Number(payload?.retry_count || 0),
          maxRetries: Number(payload?.max_retries || 0),
        })
      );
      return { status: "failed", payload };
    }

    setUploadProgressRuntime(chatId, jobId, {
      progress,
      stage: String(payload?.stage || status),
    });

    await wait(UPLOAD_JOB_POLL_INTERVAL_MS);
  }

  updateBoundMessage("Tài liệu vẫn đang xử lý trên nền. Danh sách tài liệu sẽ cập nhật khi hoàn tất.");
  return { status: "timeout", payload: null };
}

function buildUploadRetryHref(chatId, jobId) {
  return `#retry-upload:${encodeURIComponent(String(chatId || ""))}:${encodeURIComponent(String(jobId || ""))}`;
}

function buildUploadFailedMessage({ chatId, jobId, detail, canRetry, retryCount, maxRetries }) {
  const lines = [`Không thể tải tài liệu: ${detail}`];
  if (canRetry) {
    lines.push(
      "",
      `Lần thử lại: ${retryCount}/${maxRetries}`,
      `[Thử lại upload](${buildUploadRetryHref(chatId, jobId)})`
    );
  } else {
    lines.push("", `Đã đạt giới hạn thử lại (${retryCount}/${maxRetries}).`);
  }
  return lines.join("\n");
}

function parseUploadRetryHash(href) {
  const prefix = "#retry-upload:";
  const value = String(href || "").trim();
  if (!value.startsWith(prefix)) return null;

  const payload = value.slice(prefix.length);
  const [rawChatId, rawJobId] = payload.split(":");
  const chatId = decodeURIComponent(rawChatId || "").trim();
  const jobId = decodeURIComponent(rawJobId || "").trim();
  if (!chatId || !jobId) return null;
  return { chatId, jobId };
}

async function handleUploadRetryLinkClick(event) {
  const link = event.target.closest("a[href^='#retry-upload:']");
  if (!link) return;

  event.preventDefault();
  const parsed = parseUploadRetryHash(link.getAttribute("href"));
  if (!parsed) return;

  const messageEl = link.closest("[data-msg-id]");
  const messageId = messageEl?.dataset?.msgId;
  if (!messageId) return;

  await retryUploadJob({
    chatId: parsed.chatId,
    jobId: parsed.jobId,
    messageId,
  });
}

async function retryUploadJob({ chatId, jobId, messageId }) {
  replaceAssistantMessage(messageId, "Đang gửi yêu cầu thử lại upload...");

  try {
    const res = await apiFetch(`/api/v1/workspace/chats/${chatId}/upload-jobs/${jobId}/retry`, {
      method: "POST",
    });
    const { payload, text } = await parseApiPayload(res);
    if (!res.ok) {
      throw new Error(
        payload?.detail || payload?.message || text || `Không thể retry upload (HTTP ${res.status})`
      );
    }

    const originalNames = Array.isArray(payload?.original_names) ? payload.original_names : [];
    upsertTrackedUploadJob(chatId, {
      job_id: jobId,
      status: payload?.status || "queued",
      stage: payload?.stage || payload?.status || "queued",
      progress: Number(payload?.progress || 0),
      original_names: originalNames,
      retry_count: payload?.retry_count,
      max_retries: payload?.max_retries,
      updated_at: payload?.updated_at,
    });

    replaceAssistantMessage(messageId, buildUploadQueuedMessage(originalNames));
    bindMessageToUploadJob(messageId, chatId, jobId);
    setUploadProgressRuntime(chatId, jobId, {
      progress: Number(payload?.progress || 0),
      stage: payload?.stage || payload?.status || "queued",
      messageId,
    });
    if (state.currentChatId === chatId) {
      renderDocsList();
    }
    void trackUploadJob({
      chatId,
      jobId,
      originalNames,
      messageId,
    });
  } catch (err) {
    replaceAssistantMessage(messageId, `Không thể retry upload: ${err.message}`);
  }
}

function mapUploadStage(stage) {
  const value = String(stage || "").toLowerCase();
  if (value === "queued") return "Đang chờ xử lý";
  if (value === "processing") return "Đang xử lý tài liệu";
  if (value === "loading") return "Đang đọc file";
  if (value === "chunking") return "Đang chia nội dung";
  if (value === "indexing") return "Đang lập chỉ mục";
  if (value === "saving") return "Đang lưu chỉ mục";
  if (value === "completed") return "Đã hoàn tất";
  if (value === "failed") return "Xử lý thất bại";
  return "Đang xử lý tài liệu";
}

function wait(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function addTempDoc(name) {
  docsSection.classList.add("visible");
  const el = document.createElement("div");
  el.className = "doc-item";
  el.innerHTML = `
    <div class="doc-scope-wrap doc-scope-placeholder"></div>
    <div class="doc-icon-wrap">
      <svg viewBox="0 0 24 24" fill="none"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="#0D9488" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><polyline points="14 2 14 8 20 8" stroke="#0D9488" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </div>
    <div class="doc-meta">
      <div class="doc-name">${escapeHtml(name)}</div>
      <div class="doc-status">Đang lập chỉ mục…</div>
    </div>
    <div class="doc-badge loading">⟳</div>
  `;
  docsList.prepend(el);
}

/* ================================================================
   ASK
   ================================================================ */
async function handleAsk(event) {
  event.preventDefault();
  const question = questionInput.value.trim();
  if (!question) return;

  const selectedDocumentIds =
    state.currentChatId ? getSelectedDocIdsForCurrentChat() : [];

  if (state.currentChatId && state.docs.length && !selectedDocumentIds.length) {
    await showAlertModal({
      title: "Chưa chọn tài liệu",
      message: "Hãy chọn ít nhất 1 tài liệu trong mục Ask from trước khi đặt câu hỏi.",
      confirmText: "Đã rõ",
    });
    return;
  }

  appendUserMessage(question);
  state.hasChatActivity = true;
  questionInput.value = "";
  autoGrowTextarea();

  const loadingId = showThinkingIndicator();

  try {
    /* ---- Try streaming first (workspace chat only) ---- */
    if (state.currentChatId) {
      const ok = await handleAskStream(question, loadingId, selectedDocumentIds);
      if (ok) return;
    }

    /* ---- Fallback: non-streaming ---- */
    let res;
    if (state.currentChatId) {
      res = await apiFetch(`/api/v1/workspace/chats/${state.currentChatId}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, selected_document_ids: selectedDocumentIds }),
      });
    } else {
      res = await fetch("/api/v1/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
    }

    const { payload, text } = await parseApiPayload(res);
    if (!res.ok) {
      throw new Error(
        payload?.detail || payload?.message || text || `Không thể trả lời (HTTP ${res.status})`
      );
    }

    replaceAssistantMessage(loadingId, payload?.answer || "", payload?.sources || []);
  } catch (err) {
    replaceAssistantMessage(loadingId, `Lỗi khi hỏi đáp: ${err.message}`);
  }
}

/**
 * Stream answer via SSE. Returns true if streaming succeeded, false to fallback.
 */
async function handleAskStream(question, loadingId, selectedDocumentIds = []) {
  try {
    const headers = buildRequestHeaders({ "Content-Type": "application/json" });

    const res = await fetch(
      `/api/v1/workspace/chats/${state.currentChatId}/ask/stream`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({ question, selected_document_ids: selectedDocumentIds }),
      }
    );

    if (!res.ok || !res.body) return false;

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let fullText = "";
    let streamSources = [];
    let firstChunk = true;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      const text = decoder.decode(value, { stream: true });
      const lines = text.split("\n");

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const jsonStr = line.slice(6).trim();
        if (!jsonStr) continue;

        let payload;
        try { payload = JSON.parse(jsonStr); } catch { continue; }

        if (payload.done) {
          if (Array.isArray(payload.sources)) {
            streamSources = payload.sources;
          }
          break;
        }
        if (payload.token !== undefined) {
          fullText += payload.token;
          if (firstChunk) {
            /* Replace thinking indicator with first text */
            streamUpdateMessage(loadingId, fullText);
            firstChunk = false;
          } else {
            streamUpdateMessage(loadingId, fullText);
          }
        }
      }
    }

    if (!fullText.trim()) return false;

    replaceAssistantMessage(loadingId, fullText, streamSources);
    return true;
  } catch {
    return false;
  }
}

/**
 * Update a streaming message bubble with partial text (no source chips yet).
 */
function streamUpdateMessage(messageId, text) {
  const message = chatTimeline.querySelector(`[data-msg-id="${messageId}"]`);
  if (!message) return;
  const bubble = message.querySelector(".bubble");
  void setAssistantBubbleContent(bubble, text, { streaming: true });
  scrollTimeline();
}

/* ================================================================
   CHAT RENDERING
   ================================================================ */
function clearChat() {
  chatTimeline.innerHTML = "";
}

function appendUserMessage(text) {
  const article = document.createElement("article");
  article.className = "message user";
  const formatted = formatMessageHtml(text);
  article.innerHTML = `
    <div class="bubble"><p>${formatted}</p></div>
    <div class="avatar">👤</div>
  `;
  chatTimeline.append(article);
  scrollTimeline();
}

function normalizeSourceList(values) {
  return Array.from(
    new Set(
      (Array.isArray(values) ? values : [])
        .map((value) => String(value || "").trim())
        .filter(Boolean)
    )
  );
}

function decodeBase64Utf8(value) {
  const binary = atob(value);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder("utf-8").decode(bytes);
}

function extractPersistedSourcesFromText(text) {
  const raw = String(text ?? "");
  const sources = [];
  const cleaned = raw.replace(/<!--aichatbox:sources:([A-Za-z0-9+/=]+)-->/g, (_, payload) => {
    try {
      const decoded = decodeBase64Utf8(payload);
      const parsed = JSON.parse(decoded);
      if (Array.isArray(parsed)) {
        sources.push(...parsed);
      }
    } catch {
      // Keep rendering even if metadata is malformed.
    }
    return "";
  });

  return {
    text: cleaned.replace(/\n{3,}/g, "\n\n").trim(),
    sources: normalizeSourceList(sources),
  };
}

function buildSourceListHtml(sources) {
  const uniqueSources = normalizeSourceList(sources);
  if (!uniqueSources.length) return "";

  const chips = uniqueSources
    .map(
      (source) =>
        `<span class="source-chip"><span class="source-chip-icon" aria-hidden="true">📄</span>${escapeHtml(source)}</span>`
    )
    .join(" ");

  return `
    <div class="source-list">
      <span class="source-label">Trích dẫn từ:</span>
      ${chips}
    </div>
  `;
}

function appendAssistantMessage(text) {
  const persisted = extractPersistedSourcesFromText(text);
  const id = `msg_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
  const article = document.createElement("article");
  article.className = "message assistant";
  article.dataset.msgId = id;
  article.innerHTML = `
    <div class="avatar assistant-avatar">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" stroke="#0D9488" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </div>
    <div class="bubble"><div class="bubble-content"></div>${buildSourceListHtml(persisted.sources)}</div>
  `;
  chatTimeline.append(article);
  const bubble = article.querySelector(".bubble");
  void setAssistantBubbleContent(bubble, persisted.text, { streaming: false });
  scrollTimeline();
  return id;
}

function showThinkingIndicator() {
  const id = `msg_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
  const article = document.createElement("article");
  article.className = "message assistant";
  article.dataset.msgId = id;
  article.innerHTML = `
    <div class="avatar assistant-avatar">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" stroke="#0D9488" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </div>
    <div class="bubble">
      <div class="thinking-indicator">
        <div class="thinking-dots">
          <span></span><span></span><span></span>
        </div>
        <span class="thinking-text">Đang suy nghĩ...</span>
      </div>
    </div>
  `;
  chatTimeline.append(article);
  scrollTimeline();
  return id;
}

function replaceAssistantMessage(messageId, text, sources = []) {
  const message = chatTimeline.querySelector(`[data-msg-id="${messageId}"]`);
  if (!message) return;
  const bubble = message.querySelector(".bubble");
  const persisted = extractPersistedSourcesFromText(text);
  const mergedSources = normalizeSourceList([...(Array.isArray(sources) ? sources : []), ...persisted.sources]);

  bubble.innerHTML = `
    <div class="bubble-content"></div>
    ${buildSourceListHtml(mergedSources)}
  `;
  void setAssistantBubbleContent(bubble, persisted.text, { streaming: false });
  scrollTimeline();
}

function replaceAssistantMessagePlainText(messageId, text) {
  const message = chatTimeline.querySelector(`[data-msg-id="${messageId}"]`);
  if (!message) return;
  const bubble = message.querySelector(".bubble");
  if (!bubble) return;

  let contentEl = bubble.querySelector(".bubble-content");
  if (!contentEl) {
    contentEl = document.createElement("div");
    contentEl.className = "bubble-content";
    bubble.prepend(contentEl);
  }

  bubble.classList.remove("is-streaming");
  contentEl.dataset.rawText = String(text ?? "");
  contentEl.textContent = String(text ?? "");

  const sourceList = bubble.querySelector(".source-list");
  if (sourceList) {
    sourceList.remove();
  }

  scrollTimeline();
}

/* ================================================================
   HELPERS
   ================================================================ */
function buildRequestHeaders(baseHeaders = {}) {
  const headers = { ...baseHeaders };

  if (state.token) {
    headers["Authorization"] = `Bearer ${state.token}`;
    return headers;
  }

  const guestSessionId = ensureGuestSessionId();
  if (guestSessionId) {
    headers[GUEST_SESSION_HEADER] = guestSessionId;
  }
  return headers;
}

async function apiFetch(url, opts = {}) {
  const attemptFetch = () => {
    const headers = buildRequestHeaders(opts.headers || {});
    return fetch(url, { ...opts, headers });
  };

  // Don't set Content-Type for FormData — browser handles it
  let res = await attemptFetch();
  if (res.status === 401 && state.token) {
    handleLogout();
    res = await attemptFetch();
  }

  return res;
}

async function parseApiPayload(response) {
  const contentType = (response.headers.get("content-type") || "").toLowerCase();

  if (contentType.includes("application/json")) {
    try {
      return { payload: await response.json(), text: "" };
    } catch {
      return { payload: null, text: "" };
    }
  }

  const text = await response.text();
  if (!text) return { payload: null, text: "" };

  try {
    return { payload: JSON.parse(text), text };
  } catch {
    return { payload: null, text };
  }
}

function shouldWarnAnonymousDataLoss() {
  if (isAuthenticated()) return false;
  const hasConversation = state.hasChatActivity || chatTimeline.querySelectorAll(".message").length > 1;
  const hasWorkspaceData =
    Boolean(state.currentChatId)
    || state.chats.length > 0
    || state.docs.length > 0
    || Object.keys(state.uploadJobsByChat || {}).length > 0;
  return hasConversation || hasWorkspaceData;
}

function isAuthenticated() { return Boolean(state.token); }

function getStoredAuthToken() {
  try {
    return localStorage.getItem("auth_token") || localStorage.getItem("access_token") || "";
  } catch { return ""; }
}

function autoGrowTextarea() {
  questionInput.style.height = "auto";
  questionInput.style.height = `${questionInput.scrollHeight}px`;
}

function formatMessageHtml(text) {
  return escapeHtml(String(text ?? ""))
    .replace(/\r\n/g, "\n")
    .replace(/\n/g, "<br />");
}

function configureMarkdownRenderer() {
  if (markedConfigured) return;
  if (!window.marked || typeof window.marked.setOptions !== "function") return;

  window.marked.setOptions({
    gfm: true,
    breaks: true,
    mangle: false,
    headerIds: false,
  });
  markedConfigured = true;
}

function renderAssistantMarkdown(text) {
  const markdown = String(text ?? "").replace(/\r\n/g, "\n");
  if (!markdown.trim()) return "<p></p>";

  configureMarkdownRenderer();

  if (!window.marked || typeof window.marked.parse !== "function") {
    return `<p>${formatMessageHtml(markdown)}</p>`;
  }

  const rawHtml = window.marked.parse(markdown);
  return sanitizeRichHtml(rawHtml);
}

function sanitizeRichHtml(html) {
  const template = document.createElement("template");
  template.innerHTML = html;

  const allowedTags = new Set([
    "p", "br", "strong", "em", "ul", "ol", "li", "code", "pre", "blockquote", "hr",
    "table", "thead", "tbody", "tr", "th", "td", "a", "h1", "h2", "h3", "h4", "h5", "h6",
  ]);

  const allowedAttrs = {
    a: new Set(["href", "title"]),
    th: new Set(["align", "colspan", "rowspan"]),
    td: new Set(["align", "colspan", "rowspan"]),
    code: new Set(["class"]),
  };

  const nodes = Array.from(template.content.querySelectorAll("*"));
  for (const el of nodes) {
    const tag = el.tagName.toLowerCase();
    if (!allowedTags.has(tag)) {
      const textNode = document.createTextNode(el.textContent || "");
      el.replaceWith(textNode);
      continue;
    }

    for (const attr of Array.from(el.attributes)) {
      const name = attr.name.toLowerCase();
      const allowed = allowedAttrs[tag];
      if (!allowed || !allowed.has(name)) {
        el.removeAttribute(attr.name);
      }
    }

    if (tag === "a") {
      const href = el.getAttribute("href") || "";
      if (!isSafeLinkHref(href)) {
        el.removeAttribute("href");
      } else {
        el.setAttribute("target", "_blank");
        el.setAttribute("rel", "noopener noreferrer nofollow");
      }
    }

    if (tag === "code") {
      const classes = (el.getAttribute("class") || "").split(/\s+/).filter(Boolean);
      const safeClasses = classes.filter((cls) => /^(language|lang)-[a-z0-9_-]+$/i.test(cls));
      if (safeClasses.length) {
        el.setAttribute("class", safeClasses.join(" "));
      } else {
        el.removeAttribute("class");
      }
    }
  }

  return template.innerHTML;
}

function isSafeLinkHref(href) {
  const value = String(href || "").trim();
  if (!value) return false;
  if (value.startsWith("#")) return true;
  try {
    const parsed = new URL(value, window.location.origin);
    return ["http:", "https:", "mailto:"].includes(parsed.protocol);
  } catch {
    return false;
  }
}

async function setAssistantBubbleContent(bubble, text, options = {}) {
  if (!bubble) return;

  const { streaming = false } = options;
  let contentEl = bubble.querySelector(".bubble-content");
  if (!contentEl) {
    contentEl = document.createElement("div");
    contentEl.className = "bubble-content";
    bubble.prepend(contentEl);
  }

  const rawText = String(text ?? "");
  contentEl.dataset.rawText = rawText;

  if (streaming) {
    bubble.classList.add("is-streaming");
    contentEl.innerHTML = `<p>${formatMessageHtml(rawText)}</p>`;
    return;
  }

  bubble.classList.remove("is-streaming");
  const renderToken = `${Date.now()}_${Math.random()}`;
  contentEl.dataset.renderToken = renderToken;

  contentEl.innerHTML = renderAssistantMarkdown(rawText);
  wrapMarkdownTables(contentEl);
  await renderMermaidDiagrams(contentEl);

  if (contentEl.dataset.renderToken !== renderToken) return;
  scrollTimeline();
}

function wrapMarkdownTables(container) {
  const tables = Array.from(container.querySelectorAll("table"));
  for (const table of tables) {
    if (table.parentElement && table.parentElement.classList.contains("table-scroll")) continue;
    const wrap = document.createElement("div");
    wrap.className = "table-scroll";
    table.parentNode?.insertBefore(wrap, table);
    wrap.appendChild(table);
  }
}

function ensureMermaidRenderer() {
  if (!window.mermaid || typeof window.mermaid.initialize !== "function") return false;

  const isDark = document.documentElement.getAttribute("data-theme") === "dark";
  const targetTheme = isDark ? "dark" : "default";
  if (mermaidThemeMode === targetTheme) return true;

  window.mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    suppressErrorRendering: true,
    theme: targetTheme,
    fontFamily: "Plus Jakarta Sans, sans-serif",
    flowchart: { useMaxWidth: true, htmlLabels: false },
  });

  mermaidThemeMode = targetTheme;
  return true;
}

async function renderMermaidDiagrams(container) {
  const codeBlocks = Array.from(container.querySelectorAll("pre code.language-mermaid, pre code.lang-mermaid"));
  if (!codeBlocks.length) return;
  if (!ensureMermaidRenderer() || typeof window.mermaid.render !== "function") return;

  for (const block of codeBlocks) {
    const pre = block.closest("pre");
    if (!pre) continue;

    const source = (block.textContent || "").trim();
    if (!source) continue;

    const diagramContainer = document.createElement("div");
    diagramContainer.className = "diagram-card";
    pre.replaceWith(diagramContainer);

    const candidates = buildMermaidCandidates(source);
    let rendered = false;
    let lastError = null;

    try {
      for (const candidate of candidates) {
        try {
          const renderResult = await window.mermaid.render(
            `mermaid_${Date.now()}_${++mermaidSequence}`,
            candidate,
          );
          diagramContainer.innerHTML = renderResult.svg;
          rendered = true;
          break;
        } catch (error) {
          lastError = error;
          /* Try next repaired candidate */
        }
      }

      if (rendered) continue;

      const errorDetails = formatMermaidError(lastError);
      diagramContainer.classList.add("diagram-error");
      diagramContainer.innerHTML = `
        <div class="diagram-error-title">Không thể vẽ sơ đồ Mermaid từ nội dung hiện tại (cú pháp Mermaid chưa hợp lệ).</div>
        <div class="diagram-error-detail">${escapeHtml(errorDetails)}</div>
        <pre><code>${escapeHtml(source)}</code></pre>
      `;
    } catch (error) {
      const errorDetails = formatMermaidError(error);
      diagramContainer.classList.add("diagram-error");
      diagramContainer.innerHTML = `
        <div class="diagram-error-title">Không thể vẽ sơ đồ Mermaid từ nội dung hiện tại (cú pháp Mermaid chưa hợp lệ).</div>
        <div class="diagram-error-detail">${escapeHtml(errorDetails)}</div>
        <pre><code>${escapeHtml(source)}</code></pre>
      `;
    }
  }
}

function formatMermaidError(error) {
  if (!error) return "Không có chi tiết parser.";
  if (typeof error === "string") return error;

  const details = [error.str, error.message, error.name]
    .map((value) => String(value || "").trim())
    .find(Boolean);
  if (details) return details;

  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

function buildMermaidCandidates(source) {
  const original = String(source || "").trim();
  if (!original) return [];

  const normalized = normalizeMermaidSource(original);
  const aliasRepaired = repairMermaidGraphAliases(normalized);
  const edgeRepaired = repairMermaidLabeledEdges(aliasRepaired);
  const mindmapRepaired = repairMermaidMindmapLayout(edgeRepaired);
  const quotedLabels = quoteMermaidBracketLabels(mindmapRepaired);
  const repaired = repairDanglingMermaidEdges(quotedLabels);
  const fallbackAsciiLabels = deaccentMermaidBracketLabels(repaired);

  const candidates = [
    original,
    normalized,
    aliasRepaired,
    edgeRepaired,
    mindmapRepaired,
    quotedLabels,
    repaired,
    fallbackAsciiLabels,
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean);

  return Array.from(new Set(candidates));
}

function normalizeMermaidSource(source) {
  let text = String(source || "").replace(/\r\n/g, "\n");

  // Remove invisible chars that often appear in copied/generated content.
  text = text.replace(/[\u200B\u200C\u200D\uFEFF]/g, "");
  text = text.replace(/\u00A0/g, " ");
  text = text.replace(/[ \t]+$/gm, "");
  text = text.replace(/\n{3,}/g, "\n\n");

  return text.trim();
}

function repairMermaidGraphAliases(source) {
  const lines = String(source || "").split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;
    if (/^\s*graph\b/i.test(line)) {
      lines[i] = line.replace(/^\s*graph\b/i, (match) => match.replace(/graph/i, "flowchart"));
    }
    break;
  }
  return lines.join("\n").trim();
}

function repairMermaidLabeledEdges(source) {
  let text = String(source || "");

  // Common malformed output: "-->|Label|> B" or "--> |Label|> B".
  // Mermaid expects "-->|Label| B" (without the extra ">" after label pipe).
  text = text.replace(
    /(-->|==>|-.->|---|~~>|--o|o--|--x|x--)[ \t]*\|([^|\n]+)\|[ \t]*>[ \t]*/g,
    (_, edge, label) => `${edge}|${String(label || "").trim()}| `,
  );

  // Also repair malformed edge labels without pipes, e.g. "-->Label> B[1]".
  text = text.replace(
    /(-->|==>|-.->|---|~~>|--o|o--|--x|x--)[ \t]*([^|\n][^>\n]{1,120}?)[ \t]*>[ \t]*(?=[A-Za-z0-9_\u00C0-\u024F\u3040-\u30FF\u4E00-\u9FFF-]+[ \t]*[\[(])/g,
    (_, edge, label) => `${edge}|${String(label || "").trim()}| `,
  );

  // Normalize spacing around valid labeled edges for parser stability.
  text = text.replace(
    /(-->|==>|-.->|---|~~>|--o|o--|--x|x--)[ \t]*\|([^|\n]+)\|[ \t]*/g,
    (_, edge, label) => `${edge}|${String(label || "").trim()}| `,
  );

  // Repair merged lines like: "B[1] A -->|x| C[2]".
  text = text.replace(
    /([\]\)])[ \t]+([A-Za-z0-9_][A-Za-z0-9_]*[ \t]*(?:-->|==>|-.->|---|~~>|--o|o--|--x|x--))/g,
    "$1\n$2",
  );

  return text.trim();
}

function repairMermaidMindmapLayout(source) {
  const text = String(source || "");
  const firstNonEmpty = text.split("\n").find((line) => line.trim());
  if (!firstNonEmpty || !/^\s*mindmap\b/i.test(firstNonEmpty)) {
    return text.trim();
  }

  const output = ["mindmap"];
  let hasRoot = false;

  const lines = text.split("\n");
  for (const rawLine of lines) {
    const line = String(rawLine || "")
      .replace(/\u00A0/g, " ")
      .replace(/\t/g, "  ")
      .replace(/[ \t]+$/g, "");
    const trimmed = line.trim();
    if (!trimmed || /^mindmap\b/i.test(trimmed)) continue;

    const inlineRoot = trimmed.match(/^(root\(\(.+?\)\))\s+(.+)$/i);
    if (inlineRoot) {
      output.push(`  ${inlineRoot[1]}`);
      output.push(`    ${inlineRoot[2].trim()}`);
      hasRoot = true;
      continue;
    }

    if (/^root\(\(.+\)\)$/i.test(trimmed)) {
      output.push(`  ${trimmed}`);
      hasRoot = true;
      continue;
    }

    if (!hasRoot) {
      output.push(`  root((${trimmed}))`);
      hasRoot = true;
      continue;
    }

    const leadingSpaces = (line.match(/^\s*/) || [""])[0].length;
    const normalizedIndent = Math.max(4, Math.ceil(leadingSpaces / 2) * 2);
    output.push(`${" ".repeat(normalizedIndent)}${trimmed}`);
  }

  return output.join("\n").trim();
}

function quoteMermaidBracketLabels(source) {
  const text = String(source || "");
  const firstNonEmpty = text.split("\n").find((line) => line.trim());
  if (!firstNonEmpty || !/^\s*(flowchart|graph)\b/i.test(firstNonEmpty)) {
    return text.trim();
  }

  return text
    .replace(/\[([^\]\n]*)\]/g, (full, label) => {
      const content = String(label || "").trim();
      if (!content) return full;
      if ((content.startsWith('"') && content.endsWith('"')) || content.includes('"')) return full;
      return `[\"${content.replace(/\"/g, "\\\"")}\"]`;
    })
    .trim();
}

function deaccentMermaidBracketLabels(source) {
  return String(source || "")
    .replace(/\[([^\]\n]*)\]/g, (full, label) => {
      const content = String(label || "").trim();
      if (!content) return full;
      return `[\"${removeDiacritics(content).replace(/\"/g, "\\\"")}\"]`;
    })
    .trim();
}

function removeDiacritics(value) {
  try {
    return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  } catch {
    return String(value || "");
  }
}

function repairDanglingMermaidEdges(source) {
  let text = String(source || "");

  // Fix common broken pattern: line ends with arrow (with/without label) but no target node.
  const danglingEdgePattern = /(?:-->|---|==>|-.->|~~>|--o|o--|--x|x--)\s*(?:\|[^|\n]*\|\s*)?$/gm;
  text = text.replace(danglingEdgePattern, "");

  return text.trim();
}

function buildUploadSuccessMessage(names) {
  if (!names.length) return "Đã xử lý xong tài liệu. Bạn có thể bắt đầu đặt câu hỏi!";
  const nameList = names.map((n) => `"${n}"`).join(", ");
  if (names.length === 1) {
    return `Đã xử lý xong tài liệu ${nameList} ✅\nBạn có thể đặt câu hỏi về tài liệu này ngay bây giờ!`;
  }
  return `Đã xử lý xong ${names.length} tài liệu: ${nameList} ✅\nBạn có thể đặt câu hỏi về các tài liệu này ngay bây giờ!`;
}

function buildUploadQueuedMessage(names) {
  if (!names.length) return "Đã nhận tài liệu. Hệ thống đang lập chỉ mục trên nền...";
  if (names.length === 1) {
    return `Đã nhận tài liệu "${names[0]}". Hệ thống đang lập chỉ mục trên nền...`;
  }
  return `Đã nhận ${names.length} tài liệu. Hệ thống đang lập chỉ mục trên nền...`;
}

function scrollTimeline() {
  chatTimeline.scrollTop = chatTimeline.scrollHeight;
}

function escapeHtml(v) {
  return v
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

/* ================================================================
   CONTEXT MENU
   ================================================================ */
function openCtxMenu(event, type, id, chatId) {
  ctxMenu.dataset.type = type;
  ctxMenu.dataset.id = id;
  if (chatId) ctxMenu.dataset.chatId = chatId;

  const clearMessagesItem = ctxMenu.querySelector("[data-action='clear-messages']");
  if (clearMessagesItem) {
    clearMessagesItem.style.display = type === "workspace" ? "flex" : "none";
  }

  const rect = event.target.getBoundingClientRect();
  let top = rect.bottom + 4;
  let left = rect.left;

  // Keep menu within viewport
  ctxMenu.classList.add("open");
  const mRect = ctxMenu.getBoundingClientRect();
  if (top + mRect.height > window.innerHeight) top = rect.top - mRect.height - 4;
  if (left + mRect.width > window.innerWidth) left = window.innerWidth - mRect.width - 8;

  ctxMenu.style.top = `${top}px`;
  ctxMenu.style.left = `${left}px`;
}

function closeCtxMenu() {
  const activeElement = document.activeElement;
  if (activeElement instanceof HTMLElement && ctxMenu.contains(activeElement)) {
    activeElement.blur();
  }
  ctxMenu.classList.remove("open");
}

/* ================================================================
   WORKSPACE RENAME / DELETE
   ================================================================ */
async function handleRenameWorkspace(chatId) {
  const chat = state.chats.find((c) => c.chat_id === chatId);
  if (!chat) return;
  const newTitle = await showPromptModal({
    title: "Đổi Tên Workspace",
    message: "Nhập tên mới cho workspace.",
    label: "Tên mới",
    placeholder: "Workspace của tôi",
    defaultValue: chat.title,
    confirmText: "Lưu thay đổi",
  });
  if (!newTitle || newTitle.trim() === chat.title) return;
  try {
    const res = await apiFetch(`/api/v1/workspace/chats/${chatId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: newTitle.trim() }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Lỗi");
    chat.title = data.title;
    renderWorkspaceList();
    if (chatId === state.currentChatId) {
      wsTitle.textContent = "Không gian làm việc: " + data.title;
    }
  } catch (err) {
    await showAlertModal({
      title: "Đổi Tên Thất Bại",
      message: "Không thể đổi tên workspace: " + err.message,
      confirmText: "Đã hiểu",
    });
  }
}

async function handleDeleteWorkspace(chatId) {
  const chat = state.chats.find((c) => c.chat_id === chatId);
  if (!chat) return;
  const confirmed = await showConfirmModal({
    title: "Xóa Workspace",
    message: `Xóa workspace "${chat.title}"? Tất cả tài liệu và tin nhắn sẽ bị mất.`,
    confirmText: "Xóa ngay",
    cancelText: "Hủy",
    confirmVariant: "danger",
  });
  if (!confirmed) return;
  try {
    const res = await apiFetch(`/api/v1/workspace/chats/${chatId}`, { method: "DELETE" });
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Lỗi"); }
    state.chats = state.chats.filter((c) => c.chat_id !== chatId);
    delete state.uploadJobsByChat[chatId];
    persistTrackedUploadJobsToStorage();
    for (const key of Object.keys(state.activeUploadPolls)) {
      if (key.startsWith(`${chatId}::`)) {
        delete state.activeUploadPolls[key];
      }
    }
    for (const key of Object.keys(state.uploadMessageIdsByJob)) {
      if (key.startsWith(`${chatId}::`)) {
        delete state.uploadMessageIdsByJob[key];
      }
    }
    for (const key of Object.keys(state.uploadProgressTimersByJob)) {
      if (key.startsWith(`${chatId}::`)) {
        window.clearInterval(state.uploadProgressTimersByJob[key]);
        delete state.uploadProgressTimersByJob[key];
      }
    }
    for (const key of Object.keys(state.uploadProgressStateByJob)) {
      if (key.startsWith(`${chatId}::`)) {
        delete state.uploadProgressStateByJob[key];
      }
    }
    const pendingDocsTimer = state.pendingDocsRenderByChat[chatId];
    if (pendingDocsTimer) {
      window.clearTimeout(pendingDocsTimer);
      delete state.pendingDocsRenderByChat[chatId];
    }
    if (localStorage.getItem(LAST_CHAT_STORAGE_KEY) === chatId) {
      localStorage.removeItem(LAST_CHAT_STORAGE_KEY);
    }
    if (chatId === state.currentChatId) {
      state.currentChatId = null;
      state.docs = [];
      clearChat();
      wsTitle.textContent = "Chọn hoặc tạo workspace để bắt đầu";
      statusPill.textContent = "";
      docsSection.classList.remove("visible");
    }
    renderWorkspaceList();
    showToast({
      message: `Đã xóa workspace "${chat.title}" cùng toàn bộ tài liệu và tin nhắn.`,
      tone: "success",
    });
  } catch (err) {
    await showAlertModal({
      title: "Xóa Workspace Thất Bại",
      message: "Không thể xóa workspace: " + err.message,
      confirmText: "Đã hiểu",
    });
  }
}

async function handleClearWorkspaceMessages(chatId) {
  const chat = state.chats.find((c) => c.chat_id === chatId);
  if (!chat) return;

  const confirmed = await showConfirmModal({
    title: "Xóa Tin Nhắn Workspace",
    message: `Xóa toàn bộ tin nhắn trong workspace "${chat.title}"? Workspace và tài liệu sẽ được giữ lại.`,
    confirmText: "Xóa tin nhắn",
    cancelText: "Hủy",
    confirmVariant: "danger",
  });
  if (!confirmed) return;

  try {
    const res = await apiFetch(`/api/v1/workspace/chats/${chatId}/messages`, { method: "DELETE" });
    const { payload, text } = await parseApiPayload(res);
    if (!res.ok) {
      throw new Error(payload?.detail || payload?.message || text || "Lỗi");
    }

    const deletedMessages = Math.max(0, Number(payload?.deleted_messages || 0));

    if (chatId === state.currentChatId) {
      clearChat();
      appendAssistantMessage("Xin chào! Hãy tải tài liệu lên workspace này và đặt câu hỏi để bắt đầu.");
      state.hasChatActivity = false;
    }

    showToast({
      message: deletedMessages > 0
        ? `Đã xóa ${deletedMessages} tin nhắn trong workspace "${chat.title}".`
        : `Workspace "${chat.title}" không có tin nhắn để xóa.`,
      tone: deletedMessages > 0 ? "success" : "info",
    });
  } catch (err) {
    await showAlertModal({
      title: "Xóa Tin Nhắn Thất Bại",
      message: "Không thể xóa tin nhắn trong workspace: " + err.message,
      confirmText: "Đã hiểu",
    });
  }
}

/* ================================================================
   DOCUMENT RENAME / DELETE
   ================================================================ */
async function handleRenameDocument(chatId, documentId) {
  const doc = state.docs.find((d) => d.document_id === documentId);
  if (!doc) return;
  const newName = await showPromptModal({
    title: "Đổi Tên Tài Liệu",
    message: "Nhập tên mới cho tài liệu.",
    label: "Tên tài liệu",
    placeholder: "Tên tài liệu",
    defaultValue: doc.original_name,
    confirmText: "Lưu thay đổi",
  });
  if (!newName || newName.trim() === doc.original_name) return;
  try {
    const res = await apiFetch(`/api/v1/workspace/chats/${chatId}/documents/${documentId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newName.trim() }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Lỗi");
    doc.original_name = data.original_name;
    renderDocsList();
  } catch (err) {
    await showAlertModal({
      title: "Đổi Tên Thất Bại",
      message: "Không thể đổi tên tài liệu: " + err.message,
      confirmText: "Đã hiểu",
    });
  }
}

async function handleDeleteDocument(chatId, documentId) {
  const doc = state.docs.find((d) => d.document_id === documentId);
  if (!doc) return;
  const confirmed = await showConfirmModal({
    title: "Xóa Tài Liệu",
    message: `Xóa tài liệu "${doc.original_name}"?`,
    confirmText: "Xóa ngay",
    cancelText: "Hủy",
    confirmVariant: "danger",
  });
  if (!confirmed) return;

  const previousDocs = Array.isArray(state.docs) ? [...state.docs] : [];
  if (state.currentChatId === chatId) {
    state.docs = state.docs.filter((d) => d.document_id !== documentId);
    syncAskFromSelectionForCurrentChat();
    renderDocsList();
  }

  try {
    const res = await apiFetch(`/api/v1/workspace/chats/${chatId}/documents/${documentId}`, { method: "DELETE" });
    if (res.status === 404) {
      // The document may already be removed (e.g. replaced while UI was stale).
      if (state.currentChatId === chatId) {
        await loadDocsForChat(chatId);
      } else {
        state.docs = state.docs.filter((d) => d.document_id !== documentId);
        renderDocsList();
      }
      await loadAllDocCounts();
      showToast({
        message: `Tài liệu "${doc.original_name}" đã không còn tồn tại. Danh sách đã được làm mới.`,
        tone: "info",
      });
      return;
    }
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Lỗi"); }
    if (state.currentChatId === chatId) {
      // Reload from server so upload_index is compacted immediately after delete.
      await loadDocsForChat(chatId);
    } else {
      state.docs = state.docs.filter((d) => d.document_id !== documentId);
      renderDocsList();
    }
    await loadAllDocCounts();
    showToast({ message: `Đã xóa tài liệu "${doc.original_name}".`, tone: "success" });
  } catch (err) {
    if (state.currentChatId === chatId) {
      state.docs = previousDocs;
      syncAskFromSelectionForCurrentChat();
      renderDocsList();
    }
    await showAlertModal({
      title: "Xóa Tài Liệu Thất Bại",
      message: "Không thể xóa tài liệu: " + err.message,
      confirmText: "Đã hiểu",
    });
  }
}

async function handleDeleteAllDocuments() {
  const chatId = state.currentChatId;
  if (!chatId) {
    return;
  }

  const currentDocs = Array.isArray(state.docs) ? state.docs : [];
  if (!currentDocs.length) {
    await showAlertModal({
      title: "Không Có Tài Liệu",
      message: "Workspace hiện tại chưa có tài liệu để xóa.",
      confirmText: "Đã hiểu",
    });
    return;
  }

  const confirmed = await showConfirmModal({
    title: "Xóa Tất Cả Tài Liệu",
    message: `Xóa toàn bộ ${currentDocs.length} tài liệu trong workspace này?`,
    confirmText: "Xóa tất cả",
    cancelText: "Hủy",
    confirmVariant: "danger",
  });
  if (!confirmed) return;

  const previousDocs = [...currentDocs];
  const previousSelected = [...getSelectedDocIdsForCurrentChat()];
  state.docs = [];
  setSelectedDocIdsForCurrentChat([]);
  renderDocsList();

  try {
    const res = await apiFetch(`/api/v1/workspace/chats/${chatId}/documents`, { method: "DELETE" });
    const { payload, text } = await parseApiPayload(res);
    if (!res.ok) {
      throw new Error(payload?.detail || payload?.message || text || "Lỗi");
    }

    const deletedDocuments = Math.max(0, Number(payload?.deleted_documents || 0));

    if (state.currentChatId === chatId) {
      await loadDocsForChat(chatId);
    }
    await loadAllDocCounts();
    showToast({
      message: deletedDocuments > 0
        ? `Đã xóa ${deletedDocuments} tài liệu trong workspace hiện tại.`
        : "Workspace hiện tại không có tài liệu để xóa.",
      tone: deletedDocuments > 0 ? "success" : "info",
    });
  } catch (err) {
    if (state.currentChatId === chatId) {
      state.docs = previousDocs;
      setSelectedDocIdsForCurrentChat(previousSelected);
      syncAskFromSelectionForCurrentChat();
      renderDocsList();
    }
    await showAlertModal({
      title: "Xóa Tất Cả Tài Liệu Thất Bại",
      message: "Không thể xóa toàn bộ tài liệu: " + err.message,
      confirmText: "Đã hiểu",
    });
  }
}

function ensureToastViewport() {
  let viewport = document.getElementById("toastViewport");
  if (viewport) return viewport;

  viewport = document.createElement("div");
  viewport.id = "toastViewport";
  viewport.className = "toast-viewport";
  viewport.setAttribute("aria-live", "polite");
  viewport.setAttribute("aria-atomic", "true");
  document.body.appendChild(viewport);
  return viewport;
}

function showToast({ message, tone = "success", duration = 2800 } = {}) {
  const text = String(message || "").trim();
  if (!text) return;

  const normalizedTone = ["success", "info", "error"].includes(tone) ? tone : "success";
  const iconByTone = {
    success: "✓",
    info: "i",
    error: "!",
  };

  const viewport = ensureToastViewport();
  const toast = document.createElement("div");
  toast.className = `toast toast-${normalizedTone}`;
  toast.setAttribute("role", normalizedTone === "error" ? "alert" : "status");

  const icon = document.createElement("span");
  icon.className = "toast-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = iconByTone[normalizedTone];

  const messageEl = document.createElement("span");
  messageEl.className = "toast-message";
  messageEl.textContent = text;

  toast.appendChild(icon);
  toast.appendChild(messageEl);
  viewport.appendChild(toast);

  const safeDuration = Math.max(1200, Number(duration) || 2800);
  let removed = false;

  const removeToast = () => {
    if (removed) return;
    removed = true;
    toast.classList.add("is-leaving");
    window.setTimeout(() => {
      if (toast.isConnected) {
        toast.remove();
      }
    }, 180);
  };

  const timerId = window.setTimeout(removeToast, safeDuration);
  toast.addEventListener("click", () => {
    window.clearTimeout(timerId);
    removeToast();
  });
}

/* ================================================================
   UI MODAL
   ================================================================ */
function ensureUiModal() {
  let modal = document.getElementById("uiModal");
  if (modal) return modal;

  modal = document.createElement("div");
  modal.id = "uiModal";
  modal.className = "ui-modal";
  modal.hidden = true;
  modal.inert = true;
  modal.innerHTML = `
    <div class="ui-modal-backdrop" data-role="backdrop">
      <div class="ui-modal-dialog" role="dialog" aria-modal="true" aria-labelledby="uiModalTitle">
        <div class="ui-modal-header">
          <h3 id="uiModalTitle" class="ui-modal-title"></h3>
          <button type="button" class="ui-modal-close" data-role="close" aria-label="Đóng">✕</button>
        </div>
        <p class="ui-modal-message" id="uiModalMessage"></p>
        <div class="ui-modal-field-wrap" id="uiModalFieldWrap"></div>
        <p class="ui-modal-error" id="uiModalError"></p>
        <div class="ui-modal-actions">
          <button type="button" class="ui-modal-btn ui-modal-btn-secondary" data-role="cancel">Hủy</button>
          <button type="button" class="ui-modal-btn ui-modal-btn-primary" data-role="confirm">Đồng ý</button>
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(modal);
  return modal;
}

function moveFocusOutsideModal(modal, preferredTarget) {
  const isFocusInsideModal = () => {
    const currentActive = document.activeElement;
    return currentActive instanceof HTMLElement && modal.contains(currentActive);
  };

  if (!isFocusInsideModal()) {
    return;
  }

  const tryMoveFocus = (target) => {
    if (
      !(target instanceof HTMLElement)
      || !document.contains(target)
      || modal.contains(target)
    ) {
      return false;
    }

    target.focus({ preventScroll: true });
    return !isFocusInsideModal();
  };

  if (tryMoveFocus(preferredTarget)) {
    return;
  }

  const fallbackTarget = document.createElement("button");
  fallbackTarget.type = "button";
  fallbackTarget.tabIndex = -1;
  fallbackTarget.setAttribute("aria-hidden", "true");
  fallbackTarget.style.position = "fixed";
  fallbackTarget.style.left = "-9999px";
  fallbackTarget.style.top = "0";
  fallbackTarget.style.opacity = "0";
  fallbackTarget.style.pointerEvents = "none";
  document.body.appendChild(fallbackTarget);
  fallbackTarget.focus({ preventScroll: true });
  const removeFallbackTarget = () => {
    if (fallbackTarget.isConnected) {
      fallbackTarget.remove();
    }
  };
  requestAnimationFrame(removeFallbackTarget);

  if (!isFocusInsideModal()) {
    return;
  }

  removeFallbackTarget();

  const body = document.body;
  const hadTabIndex = body.hasAttribute("tabindex");
  const previousTabIndex = body.getAttribute("tabindex");

  if (!hadTabIndex) {
    body.setAttribute("tabindex", "-1");
  }
  body.focus({ preventScroll: true });

  if (!hadTabIndex) {
    body.removeAttribute("tabindex");
  } else if (previousTabIndex !== null) {
    body.setAttribute("tabindex", previousTabIndex);
  }

  if (!isFocusInsideModal()) {
    return;
  }

  const stillActive = document.activeElement;
  if (stillActive instanceof HTMLElement && modal.contains(stillActive)) {
    stillActive.blur();
  }
}

function openUiModal(options) {
  const {
    title,
    message,
    field,
    confirmText = "Đồng ý",
    cancelText = "Hủy",
    hideCancel = false,
    confirmVariant = "primary",
  } = options;

  return new Promise((resolve) => {
    const modal = ensureUiModal();
    const previousActiveElement = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const backdrop = modal.querySelector("[data-role='backdrop']");
    const titleEl = document.getElementById("uiModalTitle");
    const messageEl = document.getElementById("uiModalMessage");
    const fieldWrap = document.getElementById("uiModalFieldWrap");
    const errorEl = document.getElementById("uiModalError");
    const closeBtn = modal.querySelector("[data-role='close']");
    const cancelBtn = modal.querySelector("[data-role='cancel']");
    const confirmBtn = modal.querySelector("[data-role='confirm']");

    titleEl.textContent = title || "Thông báo";
    messageEl.textContent = message || "";
    errorEl.textContent = "";

    cancelBtn.textContent = cancelText;
    confirmBtn.textContent = confirmText;
    cancelBtn.style.display = hideCancel ? "none" : "inline-flex";
    confirmBtn.classList.toggle("ui-modal-btn-danger", confirmVariant === "danger");

    fieldWrap.innerHTML = "";
    let inputEl = null;

    if (field) {
      const label = document.createElement("label");
      label.className = "ui-modal-label";
      label.textContent = field.label || "";

      inputEl = document.createElement("input");
      inputEl.className = "ui-modal-input";
      inputEl.type = field.type || "text";
      inputEl.placeholder = field.placeholder || "";
      inputEl.value = field.defaultValue || "";
      inputEl.maxLength = field.maxLength || 255;

      fieldWrap.appendChild(label);
      fieldWrap.appendChild(inputEl);
    }

    function cleanup() {
      moveFocusOutsideModal(modal, previousActiveElement);

      modal.classList.remove("open");
      modal.inert = true;
      modal.hidden = true;
      closeBtn.removeEventListener("click", onCancel);
      cancelBtn.removeEventListener("click", onCancel);
      confirmBtn.removeEventListener("click", onConfirm);
      backdrop.removeEventListener("click", onBackdrop);
      document.removeEventListener("keydown", onKeydown);

      if (
        previousActiveElement instanceof HTMLElement
        && document.contains(previousActiveElement)
        && !modal.contains(previousActiveElement)
      ) {
        requestAnimationFrame(() => {
          if (document.contains(previousActiveElement)) {
            previousActiveElement.focus({ preventScroll: true });
          }
        });
      }
    }

    function done(value) {
      cleanup();
      resolve(value);
    }

    function onCancel() {
      done(null);
    }

    function onConfirm() {
      if (!inputEl) {
        done(true);
        return;
      }

      const value = inputEl.value.trim();
      if (!value) {
        errorEl.textContent = "Vui lòng nhập thông tin trước khi tiếp tục.";
        inputEl.focus();
        return;
      }

      done(value);
    }

    function onBackdrop(event) {
      if (event.target === backdrop) onCancel();
    }

    function onKeydown(event) {
      if (!modal.classList.contains("open")) return;
      if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
      }
      if (event.key === "Enter" && inputEl) {
        event.preventDefault();
        onConfirm();
      }
    }

    closeBtn.addEventListener("click", onCancel);
    cancelBtn.addEventListener("click", onCancel);
    confirmBtn.addEventListener("click", onConfirm);
    backdrop.addEventListener("click", onBackdrop);
    document.addEventListener("keydown", onKeydown);

    modal.hidden = false;
    modal.inert = false;
    modal.classList.add("open");

    requestAnimationFrame(() => {
      if (inputEl) {
        inputEl.focus();
        inputEl.select();
      } else {
        confirmBtn.focus();
      }
    });
  });
}

function showAlertModal(options) {
  return openUiModal({
    title: options.title,
    message: options.message,
    confirmText: options.confirmText || "Đã hiểu",
    hideCancel: true,
    confirmVariant: options.confirmVariant || "primary",
  });
}

function showConfirmModal(options) {
  return openUiModal({
    title: options.title,
    message: options.message,
    confirmText: options.confirmText || "Đồng ý",
    cancelText: options.cancelText || "Hủy",
    confirmVariant: options.confirmVariant || "primary",
  }).then((result) => Boolean(result));
}

function showPromptModal(options) {
  return openUiModal({
    title: options.title,
    message: options.message,
    field: {
      label: options.label || "",
      placeholder: options.placeholder || "",
      defaultValue: options.defaultValue || "",
      type: "text",
      maxLength: options.maxLength || 200,
    },
    confirmText: options.confirmText || "Lưu",
    cancelText: options.cancelText || "Hủy",
    confirmVariant: options.confirmVariant || "primary",
  }).then((value) => (typeof value === "string" ? value : null));
}

/* ================================================================
   CHAT EXPORT
   ================================================================ */
function toggleExportMenu() {
  if (!exportMenu || !btnExportChat) return;
  const willOpen = !exportMenu.classList.contains("open");
  exportMenu.classList.toggle("open", willOpen);
  btnExportChat.setAttribute("aria-expanded", willOpen ? "true" : "false");
}

function closeExportMenu() {
  if (!exportMenu || !btnExportChat) return;
  exportMenu.classList.remove("open");
  btnExportChat.setAttribute("aria-expanded", "false");
}

function getExportableChatMessages() {
  return Array.from(chatTimeline.querySelectorAll(".message"))
    .filter((message) => !message.querySelector(".thinking-indicator"));
}

function normalizeExportBubbleClone(root) {
  if (!root) return;

  root.classList.remove("is-streaming");
  for (const indicator of root.querySelectorAll(".thinking-indicator")) {
    indicator.remove();
  }

  for (const wrappedTable of Array.from(root.querySelectorAll(".table-scroll"))) {
    const table = wrappedTable.querySelector("table");
    if (table) {
      wrappedTable.replaceWith(table);
    } else {
      wrappedTable.remove();
    }
  }

  for (const retryLink of Array.from(root.querySelectorAll("a[href^='#retry-upload:']"))) {
    const replacement = document.createElement("span");
    replacement.textContent = retryLink.textContent || "Thử lại upload";
    retryLink.replaceWith(replacement);
  }

  for (const sourceList of Array.from(root.querySelectorAll(".source-list"))) {
    const sourceItems = Array.from(sourceList.querySelectorAll(".source-chip"))
      .map((chip) => String(chip.textContent || "").trim())
      .filter(Boolean);
    if (!sourceItems.length) continue;

    const normalized = document.createElement("div");
    normalized.className = "source-list";

    const label = document.createElement("span");
    label.className = "source-label";
    label.textContent = "Trích dẫn từ:";
    normalized.appendChild(label);

    const ul = document.createElement("ul");
    ul.className = "source-list-items";
    for (const item of sourceItems) {
      const li = document.createElement("li");
      li.textContent = item;
      ul.appendChild(li);
    }
    normalized.appendChild(ul);

    sourceList.replaceWith(normalized);
  }
}

function parseSvgDimension(value) {
  const raw = String(value || "").trim();
  if (!raw || raw.includes("%")) {
    return 0;
  }
  const numeric = Number.parseFloat(raw.replace(/[^\d.-]/g, ""));
  return Number.isFinite(numeric) && numeric > 0 ? numeric : 0;
}

function getSvgExportSize(svgElement) {
  const rect = svgElement.getBoundingClientRect();
  const rectWidth = Number.isFinite(rect.width) ? Math.round(rect.width) : 0;
  const rectHeight = Number.isFinite(rect.height) ? Math.round(rect.height) : 0;

  if (rectWidth > 0 && rectHeight > 0) {
    return {
      width: Math.max(120, rectWidth),
      height: Math.max(80, rectHeight),
    };
  }

  let width = parseSvgDimension(svgElement.getAttribute("width"));
  let height = parseSvgDimension(svgElement.getAttribute("height"));

  const viewBoxParts = String(svgElement.getAttribute("viewBox") || "")
    .split(/\s+/)
    .map((part) => Number(part));

  if (!width && viewBoxParts.length === 4 && Number.isFinite(viewBoxParts[2])) {
    width = Math.abs(viewBoxParts[2]);
  }
  if (!height && viewBoxParts.length === 4 && Number.isFinite(viewBoxParts[3])) {
    height = Math.abs(viewBoxParts[3]);
  }

  width = Math.max(120, Math.round(width || 900));
  height = Math.max(80, Math.round(height || 480));
  return { width, height };
}

function getSvgContentBounds(svgElement) {
  try {
    const bbox = svgElement.getBBox();
    if (
      Number.isFinite(bbox.x)
      && Number.isFinite(bbox.y)
      && Number.isFinite(bbox.width)
      && Number.isFinite(bbox.height)
      && bbox.width > 0
      && bbox.height > 0
    ) {
      return {
        x: bbox.x,
        y: bbox.y,
        width: bbox.width,
        height: bbox.height,
      };
    }
  } catch {
    // Some SVGs throw when measuring bbox. Keep fallback sizing path.
  }
  return null;
}

function createExportImageElement(src, altText) {
  const image = document.createElement("img");
  image.src = src;
  image.alt = altText || "Nội dung xuất từ hội thoại";
  image.style.maxWidth = "100%";
  image.style.height = "auto";
  image.style.display = "block";
  image.style.borderRadius = "8px";
  return image;
}

function getElementExportSize(element) {
  const rect = element.getBoundingClientRect();
  const width = Math.max(
    120,
    Math.round(rect.width || element.scrollWidth || element.clientWidth || 900),
  );
  const height = Math.max(
    80,
    Math.round(rect.height || element.scrollHeight || element.clientHeight || 480),
  );
  return { width, height };
}

async function elementToImageDataUrl(element, options = {}) {
  if (!window.html2canvas || typeof window.html2canvas !== "function") {
    return "";
  }

  const mimeType = options.mimeType === "image/jpeg" ? "image/jpeg" : "image/png";
  const quality = Number.isFinite(options.quality) ? Math.min(1, Math.max(0.4, Number(options.quality))) : 0.92;
  const scale = Number.isFinite(options.scale) ? Math.min(3, Math.max(1, Number(options.scale))) : 2;

  try {
    const { width, height } = getElementExportSize(element);
    const canvas = await window.html2canvas(element, {
      backgroundColor: "#ffffff",
      scale,
      useCORS: true,
      logging: false,
      width,
      height,
      windowWidth: Math.max(width, 1024),
    });

    if (mimeType === "image/jpeg") {
      return canvas.toDataURL(mimeType, quality);
    }
    return canvas.toDataURL(mimeType);
  } catch {
    return "";
  }
}

async function elementToPngDataUrl(element) {
  return elementToImageDataUrl(element, { mimeType: "image/png", scale: 2 });
}

function svgElementToPngDataUrl(svgElement, options = {}) {
  return new Promise((resolve) => {
    const serializer = new XMLSerializer();
    const svgClone = svgElement.cloneNode(true);
    const contentBounds = getSvgContentBounds(svgElement);
    const defaultSize = getSvgExportSize(svgElement);
    const mimeType = options.mimeType === "image/jpeg" ? "image/jpeg" : "image/png";
    const quality = Number.isFinite(options.quality) ? Math.min(1, Math.max(0.4, Number(options.quality))) : 0.92;

    let width = defaultSize.width;
    let height = defaultSize.height;
    if (contentBounds) {
      const padding = 12;
      const viewX = contentBounds.x - padding;
      const viewY = contentBounds.y - padding;
      const viewWidth = contentBounds.width + padding * 2;
      const viewHeight = contentBounds.height + padding * 2;

      width = Math.max(120, Math.round(viewWidth));
      height = Math.max(80, Math.round(viewHeight));
      svgClone.setAttribute("viewBox", `${viewX} ${viewY} ${viewWidth} ${viewHeight}`);
      svgClone.removeAttribute("preserveAspectRatio");
    }

    svgClone.setAttribute("width", String(width));
    svgClone.setAttribute("height", String(height));
    if (!svgClone.getAttribute("xmlns")) {
      svgClone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    }
    if (!svgClone.getAttribute("xmlns:xlink")) {
      svgClone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
    }

    const svgMarkup = serializer.serializeToString(svgClone);
    const svgDataUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgMarkup)}`;
    const image = new Image();

    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d");
      if (!context) {
        resolve("");
        return;
      }

      context.fillStyle = "#ffffff";
      context.fillRect(0, 0, width, height);
      context.drawImage(image, 0, 0, width, height);
      const imageDataUrl = mimeType === "image/jpeg"
        ? canvas.toDataURL(mimeType, quality)
        : canvas.toDataURL(mimeType);
      resolve(imageDataUrl);
    };

    image.onerror = () => {
      resolve("");
    };

    image.src = svgDataUrl;
  });
}

async function rasterizeDiagramCards(root) {
  const diagramCards = Array.from(root.querySelectorAll(".diagram-card"));
  for (const diagramCard of diagramCards) {
    const pngDataUrl = await elementToPngDataUrl(diagramCard);
    if (!pngDataUrl) continue;

    const replacementImage = createExportImageElement(pngDataUrl, "Sơ đồ xuất từ hội thoại");
    replacementImage.style.margin = "4px 0";
    diagramCard.replaceWith(replacementImage);
  }
}

function getRenderableSvgElements(root) {
  const diagramSvgs = Array.from(root.querySelectorAll(".diagram-card svg"));
  const seen = new Set(diagramSvgs);
  const result = [...diagramSvgs];

  for (const svgElement of Array.from(root.querySelectorAll("svg"))) {
    if (seen.has(svgElement)) {
      continue;
    }

    const rect = svgElement.getBoundingClientRect();
    const area = Math.max(0, Number(rect.width || 0)) * Math.max(0, Number(rect.height || 0));
    if (area >= 2400) {
      seen.add(svgElement);
      result.push(svgElement);
    }
  }

  return result;
}

async function rasterizeSvgElements(root, options = {}) {
  const exportFormat = String(options.exportFormat || "pdf").toLowerCase();
  const isWordExport = exportFormat === "word";
  const rasterOptions = {
    mimeType: isWordExport ? "image/jpeg" : "image/png",
    quality: isWordExport ? 0.86 : 0.95,
    scale: isWordExport ? 1.4 : 2,
  };

  const svgElements = getRenderableSvgElements(root);
  for (const svgElement of svgElements) {
    const rect = svgElement.getBoundingClientRect();
    const renderedWidth = Math.round(Number(rect.width || 0));

    let imageDataUrl = await elementToImageDataUrl(svgElement, rasterOptions);
    if (!imageDataUrl) {
      imageDataUrl = await svgElementToPngDataUrl(svgElement, rasterOptions);
    }
    if (!imageDataUrl) continue;

    const replacementImage = createExportImageElement(imageDataUrl, "Sơ đồ xuất từ hội thoại");
    if (renderedWidth > 0) {
      replacementImage.style.width = `${renderedWidth}px`;
    }
    replacementImage.style.margin = "4px 0";
    svgElement.replaceWith(replacementImage);
  }
}

async function prepareBubbleCloneForExport(bubbleClone, options = {}) {
  const stagingHost = document.createElement("div");
  stagingHost.style.position = "fixed";
  stagingHost.style.left = "-10000px";
  stagingHost.style.top = "0";
  stagingHost.style.width = "980px";
  stagingHost.style.padding = "12px";
  stagingHost.style.background = "#ffffff";
  stagingHost.style.pointerEvents = "none";
  stagingHost.style.opacity = "0";

  stagingHost.appendChild(bubbleClone);
  document.body.appendChild(stagingHost);

  await new Promise((resolve) => requestAnimationFrame(() => resolve()));
  try {
    await rasterizeSvgElements(bubbleClone, options);
  } finally {
    stagingHost.remove();
  }
}

function getChatExportStyleSheet() {
  return `
    * { box-sizing: border-box; }
    body { margin: 0; background: #ffffff; color: #0f172a; font-family: "Plus Jakarta Sans", "Segoe UI", Arial, sans-serif; }
    .chat-export-doc { width: 100%; max-width: 980px; margin: 0 auto; padding: 26px 26px 34px; }
    .chat-export-header { border-bottom: 2px solid #dbe6eb; padding-bottom: 12px; margin-bottom: 18px; }
    .chat-export-title { margin: 0; font-size: 22px; font-weight: 800; color: #0f172a; }
    .chat-export-subtitle { margin-top: 6px; font-size: 12px; color: #475569; }
    .chat-export-list { display: grid; gap: 12px; }
    .chat-export-message { border: 1px solid #dbe6eb; border-radius: 12px; padding: 12px 14px; background: #ffffff; page-break-inside: auto; break-inside: auto; }
    .chat-export-message.chat-export-assistant { border-left: 5px solid #22c1b3; }
    .chat-export-message.chat-export-user { border-left: 5px solid #f59e0b; background: #fffbeb; }
    .chat-export-role { font-size: 11px; font-weight: 800; letter-spacing: 0.03em; text-transform: uppercase; color: #334155; margin-bottom: 8px; }
    .chat-export-content { font-size: 13px; line-height: 1.6; color: #0f172a; }
    .chat-export-content p { margin: 0 0 8px; }
    .chat-export-content p:last-child { margin-bottom: 0; }
    .chat-export-content ul, .chat-export-content ol { margin: 8px 0 8px 20px; }
    .chat-export-content blockquote { margin: 8px 0; border-left: 4px solid #cbd5e1; padding: 6px 10px; color: #334155; background: #f8fafc; border-radius: 4px; }
    .chat-export-content pre { margin: 8px 0; padding: 10px; border-radius: 8px; background: #0f172a; color: #e2e8f0; overflow-x: auto; white-space: pre-wrap; }
    .chat-export-content code { font-family: "Cascadia Code", Consolas, monospace; font-size: 12px; }
    .chat-export-content table { width: 100%; border-collapse: collapse; margin: 8px 0; }
    .chat-export-content th, .chat-export-content td { border: 1px solid #cbd5e1; padding: 7px 8px; vertical-align: top; }
    .chat-export-content th { background: #f1f5f9; font-weight: 800; }
    .chat-export-content img { max-width: 100%; height: auto; }
    .chat-export-content .source-list { margin-top: 10px; padding: 8px; border-radius: 8px; border: 1px solid #dbe6eb; background: #f8fafc; }
    .chat-export-content .source-label { display: inline-block; margin-right: 4px; font-size: 11px; font-weight: 700; color: #334155; }
    .chat-export-content .source-list-items { margin: 8px 0 0 18px; padding: 0; }
    .chat-export-content .source-list-items li { margin: 4px 0; font-size: 11px; font-weight: 700; color: #0f766e; }
    .chat-export-content .source-chip { display: inline-block; margin: 4px 6px 0 0; padding: 4px 8px; border-radius: 999px; background: #ffffff; border: 1px solid #cbd5e1; font-size: 11px; font-weight: 700; color: #0f766e; }
    .chat-export-content .source-chip-icon { display: none; }
  `;
}

async function buildChatExportDocumentElement(options = {}) {
  const messages = getExportableChatMessages();
  if (!messages.length) {
    return null;
  }

  const exportDocument = document.createElement("article");
  exportDocument.className = "chat-export-doc";

  const header = document.createElement("header");
  header.className = "chat-export-header";
  const title = document.createElement("h1");
  title.className = "chat-export-title";
  title.textContent = wsTitle?.textContent?.trim() || "Nectar Chat Export";
  const subtitle = document.createElement("div");
  subtitle.className = "chat-export-subtitle";
  subtitle.textContent = `Xuất lúc: ${new Date().toLocaleString("vi-VN")}`;
  header.appendChild(title);
  header.appendChild(subtitle);
  exportDocument.appendChild(header);

  const list = document.createElement("div");
  list.className = "chat-export-list";

  for (const message of messages) {
    const role = message.classList.contains("user") ? "Người dùng" : "Nectar AI";
    const roleClass = message.classList.contains("user") ? "chat-export-user" : "chat-export-assistant";

    const bubble = message.querySelector(".bubble");
    const bubbleClone = bubble ? bubble.cloneNode(true) : document.createElement("div");
    normalizeExportBubbleClone(bubbleClone);
    await prepareBubbleCloneForExport(bubbleClone, options);

    const item = document.createElement("section");
    item.className = `chat-export-message ${roleClass}`;

    const roleLine = document.createElement("div");
    roleLine.className = "chat-export-role";
    roleLine.textContent = role;

    const content = document.createElement("div");
    content.className = "chat-export-content";
    content.innerHTML = bubbleClone.innerHTML || "<p>(Không có nội dung)</p>";

    item.appendChild(roleLine);
    item.appendChild(content);
    list.appendChild(item);
  }

  exportDocument.appendChild(list);
  return exportDocument;
}

function getExportFileBaseName() {
  const titleText = String(wsTitle?.textContent || "chat").trim().toLowerCase();
  const normalizedTitle = removeDiacritics(titleText)
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48) || "chat";
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  return `${normalizedTitle}-${stamp}`;
}

function downloadBlobFile(blob, fileName) {
  const blobUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(blobUrl), 500);
}

async function exportChatToPdf() {
  if (!window.html2pdf) {
    throw new Error("Thư viện xuất PDF chưa sẵn sàng");
  }

  const exportDoc = await buildChatExportDocumentElement({ exportFormat: "pdf" });
  if (!exportDoc) {
    await showAlertModal({
      title: "Không Có Nội Dung",
      message: "Hiện chưa có tin nhắn để xuất.",
      confirmText: "Đã hiểu",
    });
    return;
  }

  const host = document.createElement("div");
  host.style.position = "fixed";
  host.style.left = "-10000px";
  host.style.top = "0";
  host.style.width = "1024px";
  host.style.background = "#ffffff";

  const styleTag = document.createElement("style");
  styleTag.textContent = getChatExportStyleSheet();
  host.appendChild(styleTag);
  host.appendChild(exportDoc);
  document.body.appendChild(host);

  try {
    await window.html2pdf()
      .set({
        margin: [10, 10, 10, 10],
        filename: `${getExportFileBaseName()}.pdf`,
        pagebreak: { mode: ["css", "legacy"] },
        image: { type: "jpeg", quality: 0.98 },
        html2canvas: {
          scale: 2,
          useCORS: true,
          backgroundColor: "#ffffff",
          logging: false,
        },
        jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
      })
      .from(exportDoc)
      .save();

    showToast({ message: "Đã xuất toàn bộ đoạn chat ra file PDF.", tone: "success" });
  } finally {
    host.remove();
  }
}

async function handleExportChat(format) {
  const normalizedFormat = String(format || "").toLowerCase();
  if (normalizedFormat !== "pdf") return;

  try {
    await exportChatToPdf();
  } catch (err) {
    await showAlertModal({
      title: "Xuất Đoạn Chat Thất Bại",
      message: "Không thể xuất đoạn chat: " + err.message,
      confirmText: "Đã hiểu",
    });
  }
}

/* ================================================================
   SEARCH IN CHAT
   ================================================================ */
function openSearch() {
  searchOverlay.classList.add("open");
  searchInput.value = "";
  searchCount.textContent = "";
  searchInput.focus();
}

function closeSearch() {
  searchOverlay.classList.remove("open");
  clearSearchHighlights();
  searchCount.textContent = "";
}

function performSearch() {
  clearSearchHighlights();
  const query = searchInput.value.trim().toLowerCase();
  if (!query) { searchCount.textContent = ""; return; }

  const blocks = chatTimeline.querySelectorAll(".message.assistant .bubble-content, .message.user .bubble p");
  let total = 0;
  let firstMatchBubble = null;

  blocks.forEach((block) => {
    const text = block.dataset.rawText || block.textContent || "";
    const lower = text.toLowerCase();
    if (!lower.includes(query)) return;

    const bubble = block.closest(".bubble");
    if (bubble) {
      bubble.classList.add("search-hit");
      if (!firstMatchBubble) firstMatchBubble = bubble;
    }

    let idx = -1;
    let searchIdx;
    while ((searchIdx = lower.indexOf(query, idx + 1)) !== -1) {
      total++;
    }
  });

  if (total > 0) {
    firstMatchBubble?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  searchCount.textContent = total > 0 ? `${total} kết quả` : "Không tìm thấy";
}

function clearSearchHighlights() {
  chatTimeline.querySelectorAll(".bubble.search-hit").forEach((bubble) => {
    bubble.classList.remove("search-hit");
  });
}

/* ================================================================
   THEME (DARK / LIGHT)
   ================================================================ */
function applyStoredTheme() {
  const stored = localStorage.getItem("nectar_theme") || "light";
  setTheme(stored);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  setTheme(current === "dark" ? "light" : "dark");
}

function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("nectar_theme", theme);

  const sun = btnTheme.querySelector(".icon-sun");
  const moon = btnTheme.querySelector(".icon-moon");
  if (theme === "dark") {
    sun.style.display = "none";
    moon.style.display = "";
  } else {
    sun.style.display = "";
    moon.style.display = "none";
  }
}

function applyStoredQuickActionsState() {
  if (!quickActionsPanel || !quickActionsToggle) return;
  const stored = localStorage.getItem("nectar_quick_actions_collapsed");
  const collapsed = stored === null ? true : stored === "1";
  quickActionsPanel.classList.toggle("collapsed", collapsed);
  quickActionsToggle.setAttribute("aria-expanded", String(!collapsed));
}

function toggleQuickActions() {
  if (!quickActionsPanel || !quickActionsToggle) return;
  const collapsed = quickActionsPanel.classList.toggle("collapsed");
  quickActionsToggle.setAttribute("aria-expanded", String(!collapsed));
  localStorage.setItem("nectar_quick_actions_collapsed", collapsed ? "1" : "0");
}

function collapseQuickActions() {
  if (!quickActionsPanel || !quickActionsToggle) return;
  quickActionsPanel.classList.add("collapsed");
  quickActionsToggle.setAttribute("aria-expanded", "false");
  localStorage.setItem("nectar_quick_actions_collapsed", "1");
}
