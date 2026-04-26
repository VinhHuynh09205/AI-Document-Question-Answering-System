/* ================================================================
   ChatBoxAI – Workspace Frontend
   ================================================================ */

const state = {
  token: null,
  username: null,
  currentChatId: null,
  chats: [],
  docs: [],
  selectedDocIdsByChat: {},
  hasChatActivity: false,
};

let markedConfigured = false;
let mermaidThemeMode = "";
let mermaidSequence = 0;
const UPLOAD_JOB_POLL_INTERVAL_MS = 800;
const UPLOAD_JOB_POLL_TIMEOUT_MS = 180000;

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
const searchOverlay = document.getElementById("searchOverlay");
const searchInput = document.getElementById("searchInput");
const searchCount = document.getElementById("searchCount");
const searchClose = document.getElementById("searchClose");
const quickActionsPanel = document.getElementById("quickActionsPanel");
const quickActionsToggle = document.getElementById("quickActionsToggle");

/* ================================================================
   INIT
   ================================================================ */
(function init() {
  configureMarkdownRenderer();
  restoreSession();
  bindEvents();
  applyStoredQuickActionsState();
})();

function restoreSession() {
  const token = getStoredAuthToken();
  if (token) {
    state.token = token;
    state.username = localStorage.getItem("username") || "user";
    showLoggedIn();
    loadWorkspaces();
  }
}

/* ================================================================
   EVENT BINDINGS
   ================================================================ */
function bindEvents() {
  /* Upload (sidebar) */
  fileInput.addEventListener("change", handleUpload);

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
  state.currentChatId = null;
  state.chats = [];
  state.docs = [];
  state.selectedDocIdsByChat = {};
  localStorage.removeItem("auth_token");
  localStorage.removeItem("admin_token");
  localStorage.removeItem("username");
  localStorage.removeItem("user_role");
  showLoggedOut();
  workspaceList.innerHTML = "";
  docsList.innerHTML = "";
  docsSection.classList.remove("visible");
  if (docsSelectAll) {
    docsSelectAll.checked = false;
    docsSelectAll.indeterminate = false;
    docsSelectAll.disabled = true;
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
}

function showLoggedOut() {
  btnLogin.classList.remove("logged-in");
  const loginText = btnLogin.querySelector(".login-text");
  loginText.textContent = "Login";
  loginText.title = "";
  btnLogin.querySelector(".login-sub").textContent = "Đồng bộ phiên làm việc";
  btnLogin.querySelector(".login-arrow").textContent = "→";
}

/* ================================================================
   WORKSPACE CRUD
   ================================================================ */
async function loadWorkspaces() {
  if (!state.token) return;
  try {
    const res = await apiFetch("/api/v1/workspace/chats");
    const data = await res.json();
    state.chats = data.chats || [];
    renderWorkspaceList();
    // Load doc counts for all workspaces
    await loadAllDocCounts();
  } catch { /* silent */ }
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
    el.innerHTML = `
      <div class="ws-item-icon">${icon}</div>
      <div class="ws-item-meta">
        <div class="ws-item-title">${escapeHtml(chat.title)}</div>
        <div class="ws-item-sub">${docCount} tài liệu · ${chat.chat_id === state.currentChatId ? "Đang hoạt động" : "Sẵn sàng"}</div>
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
  if (!state.token) { window.location.href = "/login"; return; }
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
  const chat = state.chats.find((c) => c.chat_id === chatId);

  wsTitle.textContent = "Không gian làm việc: " + (chat ? chat.title : chatId);
  renderWorkspaceList();
  clearChat();

  // Load documents
  await loadDocsForChat(chatId);
  renderWorkspaceList(); // re-render with updated doc count
  // Load messages
  await loadMessagesForChat(chatId);

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
  if (!state.docs.length) {
    docsSection.classList.remove("visible");
    if (docsSelectAll) {
      docsSelectAll.checked = false;
      docsSelectAll.indeterminate = false;
      docsSelectAll.disabled = true;
      docsSelectAll.onchange = null;
    }
    return;
  }

  docsSection.classList.add("visible");
  const idx = state.chats.findIndex((c) => c.chat_id === state.currentChatId);
  docsLabel.textContent = `Tài liệu trong workspace ${String(idx + 1).padStart(2, "0")} (${state.docs.length})`;
  if (docsSelectionGuide) {
    docsSelectionGuide.textContent = "Hướng dẫn: tick vào ô vuông ở từng tài liệu để AI chỉ trả lời trong tài liệu đã chọn.";
  }

  const selectedSet = new Set(getSelectedDocIdsForCurrentChat());
  if (docsSelectAll) {
    docsSelectAll.disabled = false;
    docsSelectAll.checked = selectedSet.size === state.docs.length;
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

  // Update chat doc count
  const chat = state.chats.find((c) => c.chat_id === state.currentChatId);
  if (chat) chat._docCount = state.docs.length;
  updateStatusPill();
}

function updateStatusPill() {
  const docCount = state.docs.length;
  if (docCount > 0) {
    const selectedCount = getSelectedDocIdsForCurrentChat().length;
    statusPill.textContent = `Sẵn sàng trả lời từ ${selectedCount}/${docCount} tài liệu`;
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

async function handleUploadFiles(files) {
  if (!files.length) return;

  if (!state.token || !state.currentChatId) {
    if (!state.token) { window.location.href = "/login"; return; }
    await showAlertModal({
      title: "Thiếu Workspace",
      message: "Hãy chọn hoặc tạo workspace trước khi tải tài liệu.",
      confirmText: "Đã rõ",
    });
    return;
  }

  const uploadChatId = state.currentChatId;

  // Add temp doc items
  files.forEach((f) => addTempDoc(f.name));

  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));

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

    const originalNames = (payload?.original_names && payload.original_names.length)
      ? payload.original_names
      : files.map((file) => file.name);

    if (payload?.job_id) {
      const progressMessageId = appendAssistantMessage(buildUploadQueuedMessage(originalNames));
      const jobStatus = await pollUploadJob({
        chatId: uploadChatId,
        jobId: payload.job_id,
        originalNames,
        messageId: progressMessageId,
      });

      if (jobStatus === "completed") {
        state.hasChatActivity = true;
      }

      if (state.currentChatId === uploadChatId) {
        await loadDocsForChat(uploadChatId);
      }
      await loadAllDocCounts();
      return;
    }

    appendAssistantMessage(
      buildUploadSuccessMessage(originalNames)
    );
    state.hasChatActivity = true;
    if (state.currentChatId === uploadChatId) {
      await loadDocsForChat(uploadChatId);
    }
    await loadAllDocCounts();
  } catch (err) {
    appendAssistantMessage(`Không thể tải tài liệu: ${err.message}`);
    if (state.currentChatId === uploadChatId) {
      await loadDocsForChat(uploadChatId);
    }
  }
}

async function pollUploadJob({ chatId, jobId, originalNames, messageId }) {
  const startedAt = Date.now();
  let lastMessage = "";

  while (Date.now() - startedAt < UPLOAD_JOB_POLL_TIMEOUT_MS) {
    await wait(UPLOAD_JOB_POLL_INTERVAL_MS);

    const res = await apiFetch(`/api/v1/workspace/chats/${chatId}/upload-jobs/${jobId}`);
    const { payload, text } = await parseApiPayload(res);
    if (!res.ok) {
      throw new Error(
        payload?.detail || payload?.message || text || `Không đọc được tiến độ upload (HTTP ${res.status})`
      );
    }

    const status = String(payload?.status || "processing");
    const progress = Number.isFinite(payload?.progress) ? payload.progress : 0;

    if (status === "completed") {
      replaceAssistantMessage(messageId, buildUploadSuccessMessage(payload?.original_names || originalNames));
      return "completed";
    }

    if (status === "failed") {
      const detail = payload?.error || payload?.message || "Upload thất bại";
      replaceAssistantMessage(messageId, `Không thể tải tài liệu: ${detail}`);
      return "failed";
    }

    const progressText = `${mapUploadStage(payload?.stage || status)} (${Math.max(0, Math.min(100, progress))}%)`;
    if (progressText !== lastMessage) {
      replaceAssistantMessage(messageId, progressText);
      lastMessage = progressText;
    }
  }

  replaceAssistantMessage(
    messageId,
    "Tài liệu vẫn đang xử lý trên nền. Danh sách tài liệu sẽ cập nhật khi hoàn tất."
  );
  return "timeout";
}

function mapUploadStage(stage) {
  const value = String(stage || "").toLowerCase();
  if (value === "queued") return "Đang chờ xử lý";
  if (value === "loading") return "Đang đọc file";
  if (value === "chunking") return "Đang chia nội dung";
  if (value === "indexing") return "Đang lập chỉ mục";
  if (value === "saving") return "Đang lưu chỉ mục";
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
    state.token && state.currentChatId ? getSelectedDocIdsForCurrentChat() : [];

  if (state.token && state.currentChatId && state.docs.length && !selectedDocumentIds.length) {
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
    if (state.token && state.currentChatId) {
      const ok = await handleAskStream(question, loadingId, selectedDocumentIds);
      if (ok) return;
    }

    /* ---- Fallback: non-streaming ---- */
    let res;
    if (state.token && state.currentChatId) {
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
    const headers = { "Content-Type": "application/json" };
    if (state.token) headers["Authorization"] = `Bearer ${state.token}`;

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

function appendAssistantMessage(text) {
  const id = `msg_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
  const article = document.createElement("article");
  article.className = "message assistant";
  article.dataset.msgId = id;
  article.innerHTML = `
    <div class="avatar assistant-avatar">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" stroke="#0D9488" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </div>
    <div class="bubble"><div class="bubble-content"></div></div>
  `;
  chatTimeline.append(article);
  const bubble = article.querySelector(".bubble");
  void setAssistantBubbleContent(bubble, text, { streaming: false });
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
  const uniqueSources = Array.from(
    new Set(
      (Array.isArray(sources) ? sources : [])
        .map((value) => String(value || "").trim())
        .filter(Boolean)
    )
  );

  if (!uniqueSources.length) {
    bubble.innerHTML = `<div class="bubble-content"></div>`;
    void setAssistantBubbleContent(bubble, text, { streaming: false });
    scrollTimeline();
    return;
  }

  const chips = uniqueSources
    .map(
      (s) =>
        `<span class="source-chip"><span class="source-chip-icon" aria-hidden="true">📄</span>${escapeHtml(s)}</span>`
    )
    .join("");

  bubble.innerHTML = `
    <div class="bubble-content"></div>
    <div class="source-list">
      <span class="source-label">Trích dẫn từ:</span>
      ${chips}
    </div>
  `;
  void setAssistantBubbleContent(bubble, text, { streaming: false });
  scrollTimeline();
}

/* ================================================================
   HELPERS
   ================================================================ */
async function apiFetch(url, opts = {}) {
  const headers = opts.headers ? { ...opts.headers } : {};
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;

  // Don't set Content-Type for FormData — browser handles it
  const res = await fetch(url, { ...opts, headers });
  if (res.status === 401) {
    handleLogout();
    window.location.href = "/login";
    throw new Error("Phiên hết hạn, vui lòng đăng nhập lại.");
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
  return hasConversation;
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
    if (chatId === state.currentChatId) {
      state.currentChatId = null;
      state.docs = [];
      clearChat();
      wsTitle.textContent = "Chọn hoặc tạo workspace để bắt đầu";
      statusPill.textContent = "";
      docsSection.classList.remove("visible");
    }
    renderWorkspaceList();
  } catch (err) {
    await showAlertModal({
      title: "Xóa Workspace Thất Bại",
      message: "Không thể xóa workspace: " + err.message,
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
  try {
    const res = await apiFetch(`/api/v1/workspace/chats/${chatId}/documents/${documentId}`, { method: "DELETE" });
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Lỗi"); }
    if (state.currentChatId === chatId) {
      // Reload from server so upload_index is compacted immediately after delete.
      await loadDocsForChat(chatId);
    } else {
      state.docs = state.docs.filter((d) => d.document_id !== documentId);
      renderDocsList();
    }
    await loadAllDocCounts();
  } catch (err) {
    await showAlertModal({
      title: "Xóa Tài Liệu Thất Bại",
      message: "Không thể xóa tài liệu: " + err.message,
      confirmText: "Đã hiểu",
    });
  }
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
  modal.setAttribute("aria-hidden", "true");
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
      modal.classList.remove("open");
      modal.setAttribute("aria-hidden", "true");
      closeBtn.removeEventListener("click", onCancel);
      cancelBtn.removeEventListener("click", onCancel);
      confirmBtn.removeEventListener("click", onConfirm);
      backdrop.removeEventListener("click", onBackdrop);
      document.removeEventListener("keydown", onKeydown);
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

    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");

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
