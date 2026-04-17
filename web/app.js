/* ================================================================
   ChatBoxAI – Workspace Frontend
   ================================================================ */

const state = {
  token: null,
  username: null,
  currentChatId: null,
  chats: [],
  docs: [],
  hasChatActivity: false,
};

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
  localStorage.removeItem("auth_token");
  localStorage.removeItem("username");
  showLoggedOut();
  workspaceList.innerHTML = "";
  docsList.innerHTML = "";
  docsSection.classList.remove("visible");
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
    renderDocsList();
  } catch { state.docs = []; renderDocsList(); }
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
    return;
  }
  docsSection.classList.add("visible");
  const idx = state.chats.findIndex((c) => c.chat_id === state.currentChatId);
  docsLabel.textContent = `Tài liệu trong workspace ${String(idx + 1).padStart(2, "0")} (${state.docs.length})`;

  state.docs.forEach((doc) => {
    const el = document.createElement("div");
    el.className = "doc-item";
    el.innerHTML = `
      <div class="doc-icon-wrap">
        <svg viewBox="0 0 24 24" fill="none"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="#0D9488" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><polyline points="14 2 14 8 20 8" stroke="#0D9488" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </div>
      <div class="doc-meta">
        <div class="doc-name">${escapeHtml(doc.original_name)}</div>
        <div class="doc-status">Đã phân tích</div>
      </div>
      <button class="doc-item-actions" title="Tùy chọn">⋯</button>
    `;
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
    statusPill.textContent = `Sẵn sàng trả lời từ ${docCount} tài liệu`;
  } else {
    statusPill.textContent = "";
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

  // Add temp doc items
  files.forEach((f) => addTempDoc(f.name));

  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));

  try {
    const res = await apiFetch(`/api/v1/workspace/chats/${state.currentChatId}/upload`, {
      method: "POST",
      body: formData,
    });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.detail || "Upload thất bại");

    appendAssistantMessage(
      buildUploadSuccessMessage(payload.original_names || [])
    );
    state.hasChatActivity = true;
    await loadDocsForChat(state.currentChatId);
    renderWorkspaceList();
  } catch (err) {
    appendAssistantMessage(`Không thể tải tài liệu: ${err.message}`);
  }
}

function addTempDoc(name) {
  docsSection.classList.add("visible");
  const el = document.createElement("div");
  el.className = "doc-item";
  el.innerHTML = `
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

  appendUserMessage(question);
  state.hasChatActivity = true;
  questionInput.value = "";
  autoGrowTextarea();

  const loadingId = showThinkingIndicator();

  try {
    /* ---- Try streaming first (workspace chat only) ---- */
    if (state.token && state.currentChatId) {
      const ok = await handleAskStream(question, loadingId);
      if (ok) return;
    }

    /* ---- Fallback: non-streaming ---- */
    let res;
    if (state.token && state.currentChatId) {
      res = await apiFetch(`/api/v1/workspace/chats/${state.currentChatId}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
    } else {
      res = await fetch("/api/v1/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
    }

    const payload = await res.json();
    if (!res.ok) throw new Error(payload.detail || "Không thể trả lời");

    replaceAssistantMessage(loadingId, payload.answer, payload.sources || []);
  } catch (err) {
    replaceAssistantMessage(loadingId, `Lỗi khi hỏi đáp: ${err.message}`);
  }
}

/**
 * Stream answer via SSE. Returns true if streaming succeeded, false to fallback.
 */
async function handleAskStream(question, loadingId) {
  try {
    const headers = { "Content-Type": "application/json" };
    if (state.token) headers["Authorization"] = `Bearer ${state.token}`;

    const res = await fetch(
      `/api/v1/workspace/chats/${state.currentChatId}/ask/stream`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({ question }),
      }
    );

    if (!res.ok || !res.body) return false;

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let fullText = "";
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

        if (payload.done) break;
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

    replaceAssistantMessage(loadingId, fullText);
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
  const safeText = formatMessageHtml(text);
  bubble.innerHTML = `<p>${safeText}</p>`;
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
  const formatted = formatMessageHtml(text);
  article.innerHTML = `
    <div class="avatar assistant-avatar">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" stroke="#0D9488" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </div>
    <div class="bubble"><p>${formatted}</p></div>
  `;
  chatTimeline.append(article);
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
  const safeText = formatMessageHtml(text);

  if (!sources.length) {
    bubble.innerHTML = `<p>${safeText}</p>`;
    scrollTimeline();
    return;
  }

  const chips = sources
    .map((s) => `<span class="source-chip">📎 ${escapeHtml(s)}</span>`)
    .join("");

  bubble.innerHTML = `
    <p>${safeText}</p>
    <div class="source-list">
      <span class="source-label">Trích dẫn từ:</span>
      ${chips}
    </div>
  `;
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

function buildUploadSuccessMessage(names) {
  if (!names.length) return "Đã xử lý xong tài liệu. Bạn có thể bắt đầu đặt câu hỏi!";
  const nameList = names.map((n) => `"${n}"`).join(", ");
  if (names.length === 1) {
    return `Đã xử lý xong tài liệu ${nameList} ✅\nBạn có thể đặt câu hỏi về tài liệu này ngay bây giờ!`;
  }
  return `Đã xử lý xong ${names.length} tài liệu: ${nameList} ✅\nBạn có thể đặt câu hỏi về các tài liệu này ngay bây giờ!`;
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
    state.docs = state.docs.filter((d) => d.document_id !== documentId);
    renderDocsList();
    renderWorkspaceList();
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

  const bubbles = chatTimeline.querySelectorAll(".bubble p");
  let total = 0;

  bubbles.forEach((p) => {
    const text = p.textContent;
    const lower = text.toLowerCase();
    if (!lower.includes(query)) return;

    let result = "";
    let idx = 0;
    let searchIdx;
    while ((searchIdx = lower.indexOf(query, idx)) !== -1) {
      result += escapeHtml(text.slice(idx, searchIdx));
      result += `<mark class="search-highlight">${escapeHtml(text.slice(searchIdx, searchIdx + query.length))}</mark>`;
      idx = searchIdx + query.length;
      total++;
    }
    result += escapeHtml(text.slice(idx));
    p.innerHTML = result;
  });

  if (total > 0) {
    const firstMark = chatTimeline.querySelector(".search-highlight");
    if (firstMark) firstMark.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  searchCount.textContent = total > 0 ? `${total} kết quả` : "Không tìm thấy";
}

function clearSearchHighlights() {
  chatTimeline.querySelectorAll(".search-highlight").forEach((mark) => {
    const parent = mark.parentNode;
    mark.replaceWith(mark.textContent);
    parent.normalize();
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
