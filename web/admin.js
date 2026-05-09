/* =====================================================
   ChatBoxAI Admin Dashboard – Client-side JavaScript
   ===================================================== */
(function () {
  "use strict";

  const API = "/api/v1";
  const AUTH_TOKEN_KEY = "auth_token";
  const ADMIN_TOKEN_KEY = "admin_token";
  const USERNAME_KEY = "username";
  const USER_ROLE_KEY = "user_role";
  const LEGACY_ACCESS_TOKEN_KEY = "access_token";

  function getStorageValue(key) {
    try {
      const sessionValue = sessionStorage.getItem(key);
      if (sessionValue) return sessionValue;
    } catch {
      // Ignore storage access issues.
    }

    try {
      return localStorage.getItem(key) || "";
    } catch {
      return "";
    }
  }

  function removeStorageItem(key) {
    try { sessionStorage.removeItem(key); } catch (_) { /* ignore */ }
    try { localStorage.removeItem(key); } catch (_) { /* ignore */ }
  }

  function clearAuthStorage() {
    removeStorageItem(AUTH_TOKEN_KEY);
    removeStorageItem(ADMIN_TOKEN_KEY);
    removeStorageItem(USERNAME_KEY);
    removeStorageItem(USER_ROLE_KEY);
    removeStorageItem(LEGACY_ACCESS_TOKEN_KEY);
  }

  let token = getStorageValue(AUTH_TOKEN_KEY)
    || getStorageValue(ADMIN_TOKEN_KEY)
    || getStorageValue(LEGACY_ACCESS_TOKEN_KEY)
    || "";
  let currentPage = "dashboard";
  let usersOffset = 0;
  let auditOffset = 0;
  const PAGE_SIZE = 20;
  const USERS_API_MAX_LIMIT = 200;
  let globalSearchRaw = "";
  let globalSearchQuery = "";
  let configSectionsCache = [];
  let analyticsCache = { top_users: [], messages_per_day: [] };
  let searchDebounceTimer = null;

  /* ---------- helpers ---------- */
  function authHeaders() {
    return { Authorization: "Bearer " + token, "Content-Type": "application/json" };
  }

  async function api(path, opts = {}) {
    const res = await fetch(API + path, {
      headers: authHeaders(),
      ...opts,
    });
    if (res.status === 401 || res.status === 403) {
      clearAuthStorage();
      toast("Phiên đăng nhập hết hạn hoặc không có quyền admin.", "error");
      setTimeout(() => (window.location.href = "/login"), 1500);
      throw new Error("unauthorized");
    }
    return res;
  }

  function qs(sel) { return document.querySelector(sel); }
  function qsa(sel) { return document.querySelectorAll(sel); }

  function normalizeForSearch(value) {
    return String(value || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim();
  }

  function includesSearch(value, query) {
    if (!query) return true;
    return normalizeForSearch(value).includes(query);
  }

  async function readErrorDetail(res, fallbackMessage) {
    try {
      const payload = await res.json();
      if (payload && typeof payload.detail === "string" && payload.detail.trim()) {
        return payload.detail.trim();
      }
    } catch (_) {
      // Ignore invalid/non-JSON error payloads.
    }
    return fallbackMessage;
  }

  function formatNumber(n) {
    if (n === null || n === undefined) return "—";
    return n.toLocaleString("vi-VN");
  }

  function formatUptime(sec) {
    if (!sec) return "—";
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    if (h > 0) return h + "h " + m + "m";
    return m + " phút";
  }

  function timeAgo(isoStr) {
    if (!isoStr) return "";
    const d = new Date(isoStr);
    const now = new Date();
    const diff = Math.floor((now - d) / 1000);
    if (diff < 60) return "vừa xong";
    if (diff < 3600) return Math.floor(diff / 60) + " phút trước";
    if (diff < 86400) return Math.floor(diff / 3600) + " giờ trước";
    return Math.floor(diff / 86400) + " ngày trước";
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function avatarColor(name) {
    const colors = [
      "#0d9488", "#3b82f6", "#8b5cf6", "#ec4899",
      "#f59e0b", "#ef4444", "#06b6d4", "#84cc16",
    ];
    let h = 0;
    for (let i = 0; i < name.length; i++) h = name.charCodeAt(i) + ((h << 5) - h);
    return colors[Math.abs(h) % colors.length];
  }

  /* ---------- toast ---------- */
  function toast(msg, type = "info") {
    const c = qs("#toastContainer");
    const el = document.createElement("div");
    el.className = "toast toast-" + type;
    el.textContent = msg;
    c.appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; setTimeout(() => el.remove(), 300); }, 3500);
  }

  /* ---------- modal ---------- */
  function showModal(title, bodyHtml, footerHtml) {
    qs("#modalTitle").textContent = title;
    qs("#modalBody").innerHTML = bodyHtml;
    qs("#modalFooter").innerHTML = footerHtml;
    qs("#modalOverlay").classList.add("show");
  }
  function hideModal() {
    qs("#modalOverlay").classList.remove("show");
  }
  qs("#modalClose").onclick = hideModal;
  qs("#modalOverlay").onclick = (e) => { if (e.target === qs("#modalOverlay")) hideModal(); };

  /* ---------- theme ---------- */
  function initTheme() {
    const saved = localStorage.getItem("admin_theme") || "light";
    document.documentElement.setAttribute("data-theme", saved);
  }
  qs("#btnThemeToggle").onclick = () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("admin_theme", next);
  };

  /* ---------- sidebar / mobile ---------- */
  qs("#btnMenuToggle").onclick = () => {
    qs("#sidebar").classList.toggle("open");
    qs("#sidebarOverlay").classList.toggle("show");
  };
  qs("#sidebarOverlay").onclick = () => {
    qs("#sidebar").classList.remove("open");
    qs("#sidebarOverlay").classList.remove("show");
  };

  /* ---------- navigation ---------- */
  function navigateTo(page) {
    currentPage = page;
    qsa(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.page === page));
    qsa(".page").forEach((el) => el.classList.remove("active"));
    const target = qs("#page" + page.charAt(0).toUpperCase() + page.slice(1));
    if (target) target.classList.add("active");
    // close mobile sidebar
    qs("#sidebar").classList.remove("open");
    qs("#sidebarOverlay").classList.remove("show");
    // load data
    loadPageData(page);
  }

  qsa(".nav-item").forEach((el) => {
    el.onclick = (e) => { e.preventDefault(); navigateTo(el.dataset.page); };
  });
  qsa("[data-goto]").forEach((el) => {
    el.onclick = (e) => { e.preventDefault(); navigateTo(el.dataset.goto); };
  });

  function inferSearchPage(query) {
    const pageKeywords = {
      dashboard: ["dashboard", "tong quan", "overview", "he thong"],
      users: ["user", "nguoi dung", "tai khoan", "username", "email"],
      metrics: ["metrics", "chi so", "uptime", "request", "status"],
      config: ["config", "cau hinh", "setting", "model", "chunk", "api key"],
      analytics: ["analytics", "phan tich", "su dung", "top user", "tin nhan", "message"],
      audit: ["audit", "nhat ky", "kiem toan", "log", "bao mat"],
    };

    for (const [page, keywords] of Object.entries(pageKeywords)) {
      if (keywords.some((keyword) => query.includes(keyword) || (query.length >= 3 && keyword.includes(query)))) {
        return page;
      }
    }

    if (query.includes("@")) return "users";
    if (currentPage === "dashboard" || currentPage === "metrics") return "users";
    return currentPage;
  }

  function executeGlobalSearch(options = {}) {
    const allowRoute = options.allowRoute !== false;
    const input = qs("#globalSearch");
    globalSearchRaw = (input.value || "").trim();
    globalSearchQuery = normalizeForSearch(globalSearchRaw);

    if (!globalSearchQuery) {
      loadPageData(currentPage);
      return;
    }

    const targetPage = inferSearchPage(globalSearchQuery);
    if (allowRoute && targetPage !== currentPage) {
      navigateTo(targetPage);
      return;
    }

    loadPageData(currentPage);
  }

  function initGlobalSearch() {
    const input = qs("#globalSearch");
    if (!input) return;

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        if (searchDebounceTimer) {
          window.clearTimeout(searchDebounceTimer);
          searchDebounceTimer = null;
        }
        executeGlobalSearch({ allowRoute: true });
        return;
      }

      if (event.key === "Escape") {
        if (searchDebounceTimer) {
          window.clearTimeout(searchDebounceTimer);
          searchDebounceTimer = null;
        }
        input.value = "";
        globalSearchRaw = "";
        globalSearchQuery = "";
        loadPageData(currentPage);
      }
    });

    input.addEventListener("input", () => {
      if (searchDebounceTimer) {
        window.clearTimeout(searchDebounceTimer);
        searchDebounceTimer = null;
      }

      if (!input.value.trim() && globalSearchQuery) {
        globalSearchRaw = "";
        globalSearchQuery = "";
        loadPageData(currentPage);
        return;
      }

      if (!input.value.trim()) return;

      searchDebounceTimer = window.setTimeout(() => {
        executeGlobalSearch({ allowRoute: false });
      }, 220);
    });
  }

  /* ---------- logout ---------- */
  qs("#btnLogout").onclick = () => {
    clearAuthStorage();
    window.location.href = "/login";
  };

  /* ---------- load page data ---------- */
  function loadPageData(page) {
    switch (page) {
      case "dashboard": loadDashboard(); break;
      case "users": loadUsers(); break;
      case "metrics": loadMetrics(); break;
      case "config": loadConfig(); break;
      case "analytics": loadAnalytics(); break;
      case "audit": loadAudit(); break;
    }
  }

  /* ===================== DASHBOARD ===================== */
  async function loadDashboard() {
    try {
      const [dashRes, auditRes, analyticsRes, configRes] = await Promise.all([
        api("/admin/dashboard"),
        api("/admin/audit-logs?limit=5"),
        api("/admin/analytics/usage?days=7"),
        api("/admin/system/config"),
      ]);

      if (dashRes.ok) {
        const d = await dashRes.json();
        qs("#statUsers").textContent = formatNumber(d.total_users);
        qs("#statUsersRecent").textContent = d.recent_registrations_7d || 0;
        qs("#statMessages").textContent = formatNumber(d.total_messages);
        qs("#statDocuments").textContent = formatNumber(d.vector_store_documents);
        qs("#statUptime").textContent = formatUptime(d.uptime_seconds);
        qs("#statRequests").textContent = formatNumber(d.total_requests);
      }

      if (auditRes.ok) {
        const a = await auditRes.json();
        renderAuditPreview(a.logs || []);
      }

      if (analyticsRes.ok) {
        const an = await analyticsRes.json();
        renderChart(an.messages_per_day || [], "chartBars", "chartLabels", 7);
      } else {
        renderChart([], "chartBars", "chartLabels", 7);
      }

      if (configRes.ok) {
        const cfg = await configRes.json();
        renderConfigPreview(cfg);
      }
    } catch (e) {
      console.error("Dashboard load error:", e);
    }
  }

  function renderAuditPreview(logs) {
    const el = qs("#auditPreviewList");
    if (!logs.length) {
      el.innerHTML = '<div class="empty-state">Chưa có nhật ký nào.</div>';
      return;
    }
    el.innerHTML = logs.map((l) => {
      const dotClass = l.action.includes("setup") ? "audit-dot-setup"
        : l.action.includes("role") ? "audit-dot-role"
        : l.action.includes("status") ? "audit-dot-status"
        : l.action.includes("password") ? "audit-dot-password"
        : l.action.includes("delete") ? "audit-dot-delete"
        : "audit-dot-setup";
      const actionMap = {
        setup_first_admin: "thiết lập tài khoản admin",
        update_role: "cập nhật vai trò",
        update_status: "cập nhật trạng thái",
        reset_password: "đặt lại mật khẩu",
        delete_user: "xóa tài khoản",
      };
      const actionText = actionMap[l.action] || l.action;
      return `<div class="audit-preview-item">
        <div class="audit-dot ${dotClass}"></div>
        <div class="audit-preview-content">
          <div class="audit-preview-text">Admin <strong>${escapeHtml(l.admin_username)}</strong> ${escapeHtml(actionText)} cho tài khoản <strong>${escapeHtml(l.target)}</strong></div>
          <div class="audit-preview-time">${timeAgo(l.created_at)}</div>
        </div>
      </div>`;
    }).join("");
  }

  function renderChart(data, barsId, labelsId, maxBars) {
    const barsEl = qs("#" + barsId);
    const labelsEl = qs("#" + labelsId);

    // Fill missing days
    const today = new Date();
    const days = [];
    for (let i = maxBars - 1; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const key = d.toISOString().split("T")[0];
      const found = data.find((x) => x.date === key);
      days.push({ date: key, count: found ? found.count : 0 });
    }

    const maxVal = Math.max(1, ...days.map((d) => d.count));
    barsEl.innerHTML = days.map((d) => {
      const pct = (d.count / maxVal) * 100;
      return `<div class="chart-bar" style="height:${Math.max(4, pct)}%" data-value="${d.count}"></div>`;
    }).join("");
    labelsEl.innerHTML = days.map((d) => {
      const dayName = new Date(d.date).toLocaleDateString("vi-VN", { weekday: "short" });
      return `<div class="chart-label">${dayName}</div>`;
    }).join("");
  }

  function renderConfigPreview(cfg) {
    const el = qs("#configPreviewList");
    const items = [
      ["Embedding model", cfg.embeddings_model || "—"],
      ["Chunk size / overlap", (cfg.chunk_size || "—") + " / " + (cfg.chunk_overlap || "—")],
      ["Database", cfg.database_backend || "—"],
      ["Môi trường", cfg.app_env || "—"],
      ["Đăng ký mở", cfg.enable_registration ? "Bật" : "Tắt"],
      ["Reset password", cfg.has_openai_key ? "AI + Email" : "Manual"],
    ];
    el.innerHTML = items.map(([k, v]) => `<div class="config-row"><span class="config-key">${escapeHtml(k)}</span><span class="config-val">${escapeHtml(String(v))}</span></div>`).join("");
  }

  function applyUserFilters(users, options = {}) {
    const includeGlobalSearch = Boolean(options.includeGlobalSearch);
    const role = qs("#filterRole").value;
    const status = qs("#filterStatus").value;
    let filtered = Array.isArray(users) ? users.slice() : [];

    if (role) filtered = filtered.filter((u) => u.role === role);
    if (status === "active") filtered = filtered.filter((u) => u.is_active);
    if (status === "inactive") filtered = filtered.filter((u) => !u.is_active);

    if (includeGlobalSearch && globalSearchQuery) {
      filtered = filtered.filter((u) => includesSearch(
        `${u.username} ${u.role} ${u.created_at || ""} ${u.is_active ? "active hoat dong" : "inactive khoa"}`,
        globalSearchQuery,
      ));
    }

    return filtered;
  }

  async function fetchUsersPage(offset, limit) {
    const safeOffset = Math.max(0, Number(offset) || 0);
    const safeLimit = Math.min(USERS_API_MAX_LIMIT, Math.max(1, Number(limit) || PAGE_SIZE));
    const res = await api(`/admin/users?offset=${safeOffset}&limit=${safeLimit}`);
    if (!res.ok) {
      const message = await readErrorDetail(res, "Không thể tải danh sách người dùng.");
      throw new Error(message);
    }
    return res.json();
  }

  async function fetchAllUsers() {
    let offset = 0;
    let total = Number.POSITIVE_INFINITY;
    const users = [];

    while (offset < total) {
      const data = await fetchUsersPage(offset, USERS_API_MAX_LIMIT);
      const pageUsers = Array.isArray(data.users) ? data.users : [];
      users.push(...pageUsers);

      const parsedTotal = Number(data.total);
      total = Number.isFinite(parsedTotal) ? parsedTotal : users.length;
      if (!pageUsers.length) break;

      offset += pageUsers.length;
    }

    return { users, total: users.length };
  }

  /* ===================== USERS ===================== */
  async function loadUsers() {
    try {
      const searchingUsers = currentPage === "users" && Boolean(globalSearchQuery);
      const data = searchingUsers
        ? await fetchAllUsers()
        : await fetchUsersPage(usersOffset, PAGE_SIZE);
      const users = applyUserFilters(data.users || [], { includeGlobalSearch: searchingUsers });

      renderUsersTable(users);
      if (searchingUsers) {
        qs("#usersCount").textContent = `Tìm thấy ${users.length} kết quả cho "${globalSearchRaw}"`;
        qs("#usersPagination").innerHTML = "";
      } else {
        qs("#usersCount").textContent = `Hiển thị ${users.length} / ${data.total} người dùng`;
        renderPagination(data.total, usersOffset, PAGE_SIZE, "usersPagination", (off) => {
          usersOffset = off;
          loadUsers();
        });
      }
    } catch (e) {
      console.error("Users load error:", e);
    }
  }

  function renderUsersTable(users) {
    const body = qs("#usersTableBody");
    if (!users.length) {
      body.innerHTML = '<tr><td colspan="5" class="empty-state">Không có người dùng nào.</td></tr>';
      return;
    }
    body.innerHTML = users.map((u) => {
      const color = avatarColor(u.username);
      const initial = u.username.charAt(0).toUpperCase();
      const roleCls = u.role === "admin" ? "role-admin" : "role-user";
      const statusCls = u.is_active ? "status-active" : "status-inactive";
      const statusText = u.is_active ? "Active" : "Inactive";
      return `<tr>
        <td><div class="user-cell"><div class="user-avatar" style="background:${color}">${initial}</div><span class="user-name">${escapeHtml(u.username)}</span></div></td>
        <td><span class="role-badge ${roleCls}">${escapeHtml(u.role)}</span></td>
        <td><span class="status-badge ${statusCls}"><span class="status-dot"></span>${statusText}</span></td>
        <td>${escapeHtml(u.created_at || "—")}</td>
        <td><div class="action-btns">
          <button class="action-btn" title="Đổi vai trò" onclick="AdminApp.changeRole('${escapeHtml(u.username)}','${escapeHtml(u.role)}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          </button>
          <button class="action-btn" title="${u.is_active ? 'Khóa' : 'Mở khóa'}" onclick="AdminApp.toggleStatus('${escapeHtml(u.username)}',${u.is_active})">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">${u.is_active
              ? '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>'
              : '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/>'
            }</svg>
          </button>
          <button class="action-btn" title="Đặt lại mật khẩu" onclick="AdminApp.resetPassword('${escapeHtml(u.username)}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
          </button>
          <button class="action-btn danger" title="Xóa" onclick="AdminApp.deleteUser('${escapeHtml(u.username)}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        </div></td>
      </tr>`;
    }).join("");
  }

  function renderPagination(total, offset, limit, containerId, onNav) {
    const el = qs("#" + containerId);
    const totalPages = Math.ceil(total / limit);
    const currentP = Math.floor(offset / limit) + 1;
    if (totalPages <= 1) { el.innerHTML = ""; return; }
    let html = "";
    for (let i = 1; i <= totalPages && i <= 10; i++) {
      html += `<button class="page-btn ${i === currentP ? "active" : ""}" data-off="${(i-1)*limit}">${i}</button>`;
    }
    el.innerHTML = html;
    el.querySelectorAll(".page-btn").forEach((btn) => {
      btn.onclick = () => onNav(parseInt(btn.dataset.off));
    });
  }

  /* User actions */
  window.AdminApp = {};

  AdminApp.changeRole = function (username, currentRole) {
    const newRole = currentRole === "admin" ? "user" : "admin";
    showModal(
      "Đổi vai trò",
      `<p class="modal-text">Thay đổi vai trò của <strong>${escapeHtml(username)}</strong> thành <strong>${newRole}</strong>?</p>`,
      `<button class="btn-modal btn-modal-cancel" onclick="AdminApp.hideModal()">Hủy</button>
       <button class="btn-modal btn-modal-primary" id="btnConfirmRole">Xác nhận</button>`
    );
    qs("#btnConfirmRole").onclick = async () => {
      const res = await api(`/admin/users/${encodeURIComponent(username)}/role`, {
        method: "PUT",
        body: JSON.stringify({ role: newRole }),
      });
      hideModal();
      if (res.ok) { toast("Đã cập nhật vai trò thành " + newRole, "success"); loadUsers(); }
      else { const d = await res.json(); toast(d.detail || "Lỗi", "error"); }
    };
  };

  AdminApp.toggleStatus = function (username, isActive) {
    const action = isActive ? "khóa" : "mở khóa";
    showModal(
      (isActive ? "Khóa" : "Mở khóa") + " tài khoản",
      `<p class="modal-text">Bạn muốn <strong>${action}</strong> tài khoản <strong>${escapeHtml(username)}</strong>?</p>`,
      `<button class="btn-modal btn-modal-cancel" onclick="AdminApp.hideModal()">Hủy</button>
       <button class="btn-modal ${isActive ? "btn-modal-danger" : "btn-modal-primary"}" id="btnConfirmStatus">${isActive ? "Khóa" : "Mở khóa"}</button>`
    );
    qs("#btnConfirmStatus").onclick = async () => {
      const res = await api(`/admin/users/${encodeURIComponent(username)}/status`, {
        method: "PUT",
        body: JSON.stringify({ is_active: !isActive }),
      });
      hideModal();
      if (res.ok) { toast("Đã " + action + " tài khoản " + username, "success"); loadUsers(); }
      else { const d = await res.json(); toast(d.detail || "Lỗi", "error"); }
    };
  };

  AdminApp.resetPassword = function (username) {
    showModal(
      "Đặt lại mật khẩu",
      `<label class="modal-label">Mật khẩu mới cho ${escapeHtml(username)}</label>
       <input type="password" class="modal-input" id="inputNewPass" placeholder="Nhập mật khẩu mới (tối thiểu 8 ký tự)" autocomplete="new-password" />`,
      `<button class="btn-modal btn-modal-cancel" onclick="AdminApp.hideModal()">Hủy</button>
       <button class="btn-modal btn-modal-primary" id="btnConfirmPass">Đặt lại</button>`
    );
    qs("#btnConfirmPass").onclick = async () => {
      const pw = qs("#inputNewPass").value;
      if (pw.length < 8) { toast("Mật khẩu cần tối thiểu 8 ký tự", "error"); return; }
      const res = await api(`/admin/users/${encodeURIComponent(username)}/reset-password`, {
        method: "POST",
        body: JSON.stringify({ new_password: pw }),
      });
      hideModal();
      if (res.ok) { toast("Đã đặt lại mật khẩu cho " + username, "success"); }
      else { const d = await res.json(); toast(d.detail || "Lỗi", "error"); }
    };
  };

  AdminApp.deleteUser = function (username) {
    showModal(
      "Xóa tài khoản",
      `<p class="modal-text">Bạn chắc chắn muốn <strong style="color:var(--error)">xóa vĩnh viễn</strong> tài khoản <strong>${escapeHtml(username)}</strong>?<br>Hành động này không thể hoàn tác.</p>`,
      `<button class="btn-modal btn-modal-cancel" onclick="AdminApp.hideModal()">Hủy</button>
       <button class="btn-modal btn-modal-danger" id="btnConfirmDelete">Xóa vĩnh viễn</button>`
    );
    qs("#btnConfirmDelete").onclick = async () => {
      const res = await api(`/admin/users/${encodeURIComponent(username)}`, { method: "DELETE" });
      hideModal();
      if (res.ok) { toast("Đã xóa tài khoản " + username, "success"); loadUsers(); }
      else { const d = await res.json(); toast(d.detail || "Lỗi", "error"); }
    };
  };

  AdminApp.hideModal = hideModal;

  /* Filters */
  qs("#filterRole").onchange = () => { usersOffset = 0; loadUsers(); };
  qs("#filterStatus").onchange = () => { usersOffset = 0; loadUsers(); };

  /* Export */
  function getStatusFilterLabel(value) {
    if (value === "active") return "Hoạt động";
    if (value === "inactive") return "Tạm khóa";
    return "Tất cả";
  }

  function buildUsersExportDocument(users) {
    const roleFilter = qs("#filterRole").value;
    const statusFilter = qs("#filterStatus").value;
    const generatedAt = new Date().toLocaleString("vi-VN");
    const searchLabel = globalSearchRaw
      ? ` | Từ khóa: ${escapeHtml(globalSearchRaw)}`
      : "";

    const rows = users.length
      ? users.map((u, idx) => `
          <tr>
            <td>${idx + 1}</td>
            <td>${escapeHtml(u.username)}</td>
            <td>${escapeHtml(u.role)}</td>
            <td>${u.is_active ? "Hoạt động" : "Tạm khóa"}</td>
            <td>${escapeHtml(u.created_at || "—")}</td>
          </tr>
        `).join("")
      : '<tr><td colspan="5">Không có dữ liệu người dùng phù hợp.</td></tr>';

    const wrapper = document.createElement("div");
    wrapper.innerHTML = `
      <div style="font-family: Arial, Helvetica, sans-serif; color:#0f172a; background:#ffffff; padding:20px; width:980px; box-sizing:border-box;">
        <h1 style="margin:0 0 8px; font-size:24px;">Danh sách người dùng</h1>
        <p style="margin:0 0 6px; color:#334155; font-size:13px;">Thời gian xuất: ${escapeHtml(generatedAt)}</p>
        <p style="margin:0 0 6px; color:#334155; font-size:13px;">Bộ lọc: Vai trò ${escapeHtml(roleFilter || "Tất cả")} | Trạng thái ${escapeHtml(getStatusFilterLabel(statusFilter))}${searchLabel}</p>
        <p style="margin:0 0 16px; color:#0d9488; font-size:13px; font-weight:700;">Tổng số người dùng: ${users.length}</p>
        <table style="width:100%; border-collapse:collapse; font-size:12px;">
          <thead>
            <tr style="background:#e2e8f0; color:#0f172a;">
              <th style="border:1px solid #cbd5e1; text-align:left; padding:8px; width:48px;">#</th>
              <th style="border:1px solid #cbd5e1; text-align:left; padding:8px;">Người dùng</th>
              <th style="border:1px solid #cbd5e1; text-align:left; padding:8px; width:110px;">Vai trò</th>
              <th style="border:1px solid #cbd5e1; text-align:left; padding:8px; width:120px;">Trạng thái</th>
              <th style="border:1px solid #cbd5e1; text-align:left; padding:8px; width:210px;">Ngày tạo</th>
            </tr>
          </thead>
          <tbody>
            ${rows}
          </tbody>
        </table>
      </div>
    `;
    return wrapper.firstElementChild;
  }

  async function exportUsersToPdf() {
    if (!window.html2pdf) {
      throw new Error("Thư viện xuất PDF chưa sẵn sàng.");
    }

    const allUsersData = await fetchAllUsers();
    const filteredUsers = applyUserFilters(allUsersData.users, {
      includeGlobalSearch: Boolean(globalSearchQuery),
    });
    const exportDoc = buildUsersExportDocument(filteredUsers);

    const host = document.createElement("div");
    host.style.position = "fixed";
    host.style.left = "-10000px";
    host.style.top = "0";
    host.style.width = "1024px";
    host.style.background = "#ffffff";
    host.appendChild(exportDoc);
    document.body.appendChild(host);

    const dateStamp = new Date().toISOString().split("T")[0];
    const querySuffix = globalSearchQuery ? `_${globalSearchQuery.replace(/\s+/g, "-").slice(0, 20)}` : "";

    try {
      await window.html2pdf()
        .set({
          margin: [8, 8, 8, 8],
          filename: `users_export_${dateStamp}${querySuffix}.pdf`,
          pagebreak: { mode: ["css", "legacy"] },
          image: { type: "jpeg", quality: 0.98 },
          html2canvas: {
            scale: 2,
            useCORS: true,
            backgroundColor: "#ffffff",
            logging: false,
          },
          jsPDF: { unit: "mm", format: "a4", orientation: "landscape" },
        })
        .from(exportDoc)
        .save();
    } finally {
      host.remove();
    }

    return filteredUsers.length;
  }

  qs("#btnExportUsers").onclick = async () => {
    const btn = qs("#btnExportUsers");
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = "Đang xuất PDF...";

    try {
      const exportedCount = await exportUsersToPdf();
      toast(`Đã xuất ${exportedCount} người dùng ra PDF`, "success");
    } catch (e) {
      toast("Lỗi xuất PDF: " + (e && e.message ? e.message : "Không xác định"), "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
  };

  /* ===================== METRICS ===================== */
  async function loadMetrics() {
    try {
      const res = await api("/admin/system/metrics");
      if (!res.ok) return;
      const d = await res.json();

      qs("#metricUptime").textContent = formatUptime(d.uptime_seconds);
      qs("#metricRequests").textContent = formatNumber(d.total_requests);
      qs("#metricFallback").textContent = formatNumber(d.fallback_answers);
      qs("#metricRateLimited").textContent = formatNumber(d.rate_limited_requests);

      // Status bars
      const sc = d.status_counts || {};
      const total = Object.values(sc).reduce((a, b) => a + b, 0) || 1;
      const groups = { "2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0 };
      Object.entries(sc).forEach(([code, cnt]) => {
        const c = parseInt(code);
        if (c < 300) groups["2xx"] += cnt;
        else if (c < 400) groups["3xx"] += cnt;
        else if (c < 500) groups["4xx"] += cnt;
        else groups["5xx"] += cnt;
      });
      qs("#statusBars").innerHTML = Object.entries(groups).map(([g, cnt]) => {
        const pct = Math.max(0.5, (cnt / total) * 100);
        return `<div class="status-bar-row">
          <span class="status-bar-label">${g}</span>
          <div class="status-bar-track"><div class="status-bar-fill status-${g}" style="width:${pct}%"><span class="status-bar-count">${cnt}</span></div></div>
        </div>`;
      }).join("");

      // Endpoints
      const ep = d.endpoint_counts || {};
      const sorted = Object.entries(ep).sort((a, b) => b[1] - a[1]);
      qs("#endpointList").innerHTML = sorted.length
        ? sorted.map(([path, cnt]) => {
            const parts = path.split(" ");
            const method = parts[0] || "GET";
            const route = parts.slice(1).join(" ");
            return `<div class="endpoint-row">
              <span class="endpoint-method method-${method}">${method}</span>
              <span class="endpoint-path">${escapeHtml(route)}</span>
              <span class="endpoint-count">${cnt}</span>
            </div>`;
          }).join("")
        : '<div class="empty-state">Chưa có dữ liệu.</div>';
    } catch (e) {
      console.error("Metrics load error:", e);
    }
  }

  qs("#btnRefreshMetrics").onclick = loadMetrics;

  /* ===================== CONFIG ===================== */
  function renderConfigSections(sections) {
    qs("#configGrid").innerHTML = sections.map((s) =>
      `<div class="config-section-title">${escapeHtml(s.title)}</div>` +
      s.items.map(([k, v]) =>
        `<div class="config-row"><span class="config-key">${escapeHtml(k)}</span><span class="config-val">${escapeHtml(String(v ?? "—"))}</span></div>`
      ).join("")
    ).join("");
  }

  function applyConfigSearchFilter() {
    if (!globalSearchQuery) {
      renderConfigSections(configSectionsCache);
      return;
    }

    const filteredSections = configSectionsCache
      .map((section) => {
        const titleMatches = includesSearch(section.title, globalSearchQuery);
        const items = titleMatches
          ? section.items
          : section.items.filter(([k, v]) => includesSearch(`${k} ${String(v ?? "")}`, globalSearchQuery));
        return { title: section.title, items };
      })
      .filter((section) => section.items.length > 0);

    if (!filteredSections.length) {
      qs("#configGrid").innerHTML = `<div class="empty-state">Không tìm thấy cấu hình phù hợp với "${escapeHtml(globalSearchRaw)}".</div>`;
      return;
    }

    renderConfigSections(filteredSections);
  }

  async function loadConfig() {
    try {
      const res = await api("/admin/system/config");
      if (!res.ok) return;
      const cfg = await res.json();

      configSectionsCache = [
        {
          title: "Ứng dụng",
          items: [
            ["Tên ứng dụng", cfg.app_name],
            ["Môi trường", cfg.app_env],
            ["Database", cfg.database_backend],
            ["Đăng ký mở", cfg.enable_registration ? "Bật" : "Tắt"],
            ["Security headers", cfg.enable_security_headers ? "Bật" : "Tắt"],
          ],
        },
        {
          title: "AI Models",
          items: [
            ["OpenAI model", cfg.openai_model],
            ["Gemini model", cfg.gemini_model],
            ["Groq model", cfg.groq_model],
            ["Embedding model", cfg.embeddings_model],
            ["Local embeddings", cfg.local_semantic_embeddings ? "Bật" : "Tắt"],
          ],
        },
        {
          title: "RAG Settings",
          items: [
            ["Chunk size", cfg.chunk_size],
            ["Chunk overlap", cfg.chunk_overlap],
            ["Top K", cfg.top_k],
            ["Max answer chars", cfg.max_answer_chars],
          ],
        },
        {
          title: "Rate Limiting",
          items: [
            ["Window (giây)", cfg.rate_limit_window_seconds],
            ["Ask rate limit", cfg.ask_rate_limit_per_window],
            ["Upload rate limit", cfg.upload_rate_limit_per_window],
          ],
        },
        {
          title: "API Keys",
          items: [
            ["OpenAI key", cfg.has_openai_key ? "✓ Đã cấu hình" : "✗ Chưa cấu hình"],
            ["Google key", cfg.has_google_key ? "✓ Đã cấu hình" : "✗ Chưa cấu hình"],
            ["Groq key", cfg.has_groq_key ? "✓ Đã cấu hình" : "✗ Chưa cấu hình"],
            ["OAuth Google", cfg.has_oauth_google ? "✓ Đã cấu hình" : "✗ Chưa cấu hình"],
            ["OAuth GitHub", cfg.has_oauth_github ? "✓ Đã cấu hình" : "✗ Chưa cấu hình"],
          ],
        },
        {
          title: "Upload",
          items: [
            ["Extensions", cfg.supported_upload_extensions],
          ],
        },
      ];

      applyConfigSearchFilter();
    } catch (e) {
      console.error("Config load error:", e);
    }
  }

  /* ===================== ANALYTICS ===================== */
  async function loadAnalytics() {
    try {
      const res = await api("/admin/analytics/usage?days=30");
      if (!res.ok) {
        const message = await readErrorDetail(res, "Không thể tải dữ liệu phân tích sử dụng.");
        renderAnalyticsError(message);
        return;
      }
      const data = await res.json();
      analyticsCache = {
        top_users: Array.isArray(data.top_users) ? data.top_users : [],
        messages_per_day: Array.isArray(data.messages_per_day) ? data.messages_per_day : [],
      };

      // Chart
      renderAnalyticsChart(analyticsCache.messages_per_day);
      applyAnalyticsSearchFilter();
    } catch (e) {
      console.error("Analytics load error:", e);
      renderAnalyticsError("Không thể tải dữ liệu phân tích sử dụng.");
    }
  }

  function renderTopUsers(users, emptyMessage = "Chưa có dữ liệu người dùng.") {
    const el = qs("#topUsersList");
    if (!users.length) {
      el.innerHTML = `<div class="empty-state">${escapeHtml(emptyMessage)}</div>`;
      return;
    }

    el.innerHTML = users.map((u, i) => {
      const rankCls = i < 3 ? ` rank-${i + 1}` : "";
      return `<div class="top-user-row">
        <div class="top-user-rank${rankCls}">${i + 1}</div>
        <span class="top-user-name">${escapeHtml(u.username)}</span>
        <span class="top-user-count">${formatNumber(u.message_count)}<span class="top-user-label">tin nhắn</span></span>
      </div>`;
    }).join("");
  }

  function applyAnalyticsSearchFilter() {
    if (!globalSearchQuery) {
      renderTopUsers(analyticsCache.top_users);
      return;
    }

    const users = analyticsCache.top_users.filter((u) =>
      includesSearch(`${u.username} ${u.message_count}`, globalSearchQuery)
    );
    renderTopUsers(users, `Không tìm thấy người dùng phù hợp với "${globalSearchRaw}".`);
  }

  function renderAnalyticsError(message) {
    const safeMessage = escapeHtml(message);
    qs("#analyticsChartBars").innerHTML = `<div class="empty-state">${safeMessage}</div>`;
    qs("#analyticsChartLabels").innerHTML = "";
    renderTopUsers([], message);
  }

  function renderAnalyticsChart(data) {
    const barsEl = qs("#analyticsChartBars");
    const labelsEl = qs("#analyticsChartLabels");

    const today = new Date();
    const days = [];
    for (let i = 29; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const key = d.toISOString().split("T")[0];
      const found = data.find((x) => x.date === key);
      days.push({ date: key, count: found ? found.count : 0 });
    }

    const maxVal = Math.max(1, ...days.map((d) => d.count));
    barsEl.innerHTML = days.map((d) => {
      const pct = (d.count / maxVal) * 100;
      return `<div class="chart-bar" style="height:${Math.max(3, pct)}%" data-value="${d.count}"></div>`;
    }).join("");

    // Show labels every 5 days
    labelsEl.innerHTML = days.map((d, i) => {
      const show = i % 5 === 0 || i === days.length - 1;
      const label = show ? new Date(d.date).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" }) : "";
      return `<div class="chart-label">${label}</div>`;
    }).join("");
  }

  /* ===================== AUDIT ===================== */
  async function loadAudit() {
    try {
      const searchingAudit = currentPage === "audit" && Boolean(globalSearchQuery);
      const reqOffset = searchingAudit ? 0 : auditOffset;
      const reqLimit = searchingAudit ? 10000 : PAGE_SIZE;
      const res = await api(`/admin/audit-logs?offset=${reqOffset}&limit=${reqLimit}`);
      if (!res.ok) return;
      const data = await res.json();
      const logs = data.logs || [];
      const filteredLogs = searchingAudit
        ? logs.filter((l) => includesSearch(
          `${l.admin_username} ${l.action} ${l.target} ${l.detail} ${l.created_at}`,
          globalSearchQuery,
        ))
        : logs;

      const body = qs("#auditTableBody");
      if (!filteredLogs.length) {
        body.innerHTML = '<tr><td colspan="5" class="empty-state">Chưa có nhật ký nào.</td></tr>';
      } else {
        body.innerHTML = filteredLogs.map((l) => `<tr>
          <td style="white-space:nowrap">${escapeHtml(timeAgo(l.created_at))}</td>
          <td><strong>${escapeHtml(l.admin_username)}</strong></td>
          <td><span class="action-badge badge-${l.action.includes('delete') ? 'admin' : l.action.includes('setup') || l.action.includes('role') ? 'read' : 'write'}">${escapeHtml(l.action)}</span></td>
          <td>${escapeHtml(l.target)}</td>
          <td style="color:var(--text-secondary)">${escapeHtml(l.detail)}</td>
        </tr>`).join("");
      }

      if (searchingAudit) {
        qs("#auditCount").textContent = `Tìm thấy ${filteredLogs.length} kết quả cho "${globalSearchRaw}"`;
        qs("#auditPagination").innerHTML = "";
      } else {
        qs("#auditCount").textContent = `${data.total} bản ghi`;
        renderPagination(data.total, auditOffset, PAGE_SIZE, "auditPagination", (off) => {
          auditOffset = off;
          loadAudit();
        });
      }
    } catch (e) {
      console.error("Audit load error:", e);
    }
  }

  /* ===================== INIT ===================== */
  async function init() {
    initTheme();
    initGlobalSearch();

    // Check auth - try to use existing token
    if (!token) {
      window.location.href = "/login";
      return;
    }

    // Verify admin access
    try {
      const res = await api("/admin/dashboard");
      if (!res.ok) {
        clearAuthStorage();
        window.location.href = "/login";
        return;
      }
      const d = await res.json();

      // Set user info
      // Decode JWT to get username
      try {
        const payload = JSON.parse(atob(token.split(".")[1]));
        const username = payload.sub || "Admin";
        qs("#userNameEl").textContent = username;
        qs("#userAvatarEl").textContent = username.charAt(0).toUpperCase();
      } catch (_) { /* ignore */ }

      // Load initial dashboard data
      qs("#statUsers").textContent = formatNumber(d.total_users);
      qs("#statUsersRecent").textContent = d.recent_registrations_7d || 0;
      qs("#statMessages").textContent = formatNumber(d.total_messages);
      qs("#statDocuments").textContent = formatNumber(d.vector_store_documents);
      qs("#statUptime").textContent = formatUptime(d.uptime_seconds);
      qs("#statRequests").textContent = formatNumber(d.total_requests);

      // Load remaining dashboard data
      loadDashboard();
    } catch (e) {
      console.error("Init error:", e);
    }
  }

  init();
})();
