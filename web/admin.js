/* =====================================================
   ChatBoxAI Admin Dashboard – Client-side JavaScript
   ===================================================== */
(function () {
  "use strict";

  const API = "/api/v1";
  let token = localStorage.getItem("auth_token") || localStorage.getItem("admin_token") || "";
  let currentPage = "dashboard";
  let usersOffset = 0;
  let auditOffset = 0;
  const PAGE_SIZE = 20;

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
      toast("Phiên đăng nhập hết hạn hoặc không có quyền admin.", "error");
      setTimeout(() => (window.location.href = "/login"), 1500);
      throw new Error("unauthorized");
    }
    return res;
  }

  function qs(sel) { return document.querySelector(sel); }
  function qsa(sel) { return document.querySelectorAll(sel); }

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

  /* ---------- logout ---------- */
  qs("#btnLogout").onclick = () => {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("admin_token");
    localStorage.removeItem("username");
    localStorage.removeItem("user_role");
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

  /* ===================== USERS ===================== */
  async function loadUsers() {
    try {
      const role = qs("#filterRole").value;
      const status = qs("#filterStatus").value;
      let url = `/admin/users?offset=${usersOffset}&limit=${PAGE_SIZE}`;
      const res = await api(url);
      if (!res.ok) return;
      const data = await res.json();
      let users = data.users || [];

      // client-side filter
      if (role) users = users.filter((u) => u.role === role);
      if (status === "active") users = users.filter((u) => u.is_active);
      if (status === "inactive") users = users.filter((u) => !u.is_active);

      renderUsersTable(users);
      qs("#usersCount").textContent = `Hiển thị ${users.length} / ${data.total} người dùng`;
      renderPagination(data.total, usersOffset, PAGE_SIZE, "usersPagination", (off) => {
        usersOffset = off;
        loadUsers();
      });
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
  qs("#btnExportUsers").onclick = async () => {
    try {
      const res = await api("/admin/users?limit=10000");
      if (!res.ok) return;
      const data = await res.json();
      const rows = [["Username", "Role", "Status", "Created At"]];
      (data.users || []).forEach((u) => {
        rows.push([u.username, u.role, u.is_active ? "active" : "inactive", u.created_at || ""]);
      });
      const csv = rows.map((r) => r.map((c) => '"' + String(c).replace(/"/g, '""') + '"').join(",")).join("\n");
      const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "users_export_" + new Date().toISOString().split("T")[0] + ".csv";
      a.click();
      URL.revokeObjectURL(url);
      toast("Đã xuất danh sách người dùng", "success");
    } catch (e) {
      toast("Lỗi xuất danh sách", "error");
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
  async function loadConfig() {
    try {
      const res = await api("/admin/system/config");
      if (!res.ok) return;
      const cfg = await res.json();

      const sections = [
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

      qs("#configGrid").innerHTML = sections.map((s) =>
        `<div class="config-section-title">${escapeHtml(s.title)}</div>` +
        s.items.map(([k, v]) =>
          `<div class="config-row"><span class="config-key">${escapeHtml(k)}</span><span class="config-val">${escapeHtml(String(v ?? "—"))}</span></div>`
        ).join("")
      ).join("");
    } catch (e) {
      console.error("Config load error:", e);
    }
  }

  /* ===================== ANALYTICS ===================== */
  async function loadAnalytics() {
    try {
      const res = await api("/admin/analytics/usage?days=30");
      if (!res.ok) return;
      const data = await res.json();

      // Chart
      renderAnalyticsChart(data.messages_per_day || []);

      // Top users
      const el = qs("#topUsersList");
      const users = data.top_users || [];
      if (!users.length) {
        el.innerHTML = '<div class="empty-state">Chưa có dữ liệu người dùng.</div>';
      } else {
        el.innerHTML = users.map((u, i) => {
          const rankCls = i < 3 ? ` rank-${i + 1}` : "";
          return `<div class="top-user-row">
            <div class="top-user-rank${rankCls}">${i + 1}</div>
            <span class="top-user-name">${escapeHtml(u.username)}</span>
            <span class="top-user-count">${formatNumber(u.message_count)}<span class="top-user-label">tin nhắn</span></span>
          </div>`;
        }).join("");
      }
    } catch (e) {
      console.error("Analytics load error:", e);
    }
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
      const res = await api(`/admin/audit-logs?offset=${auditOffset}&limit=${PAGE_SIZE}`);
      if (!res.ok) return;
      const data = await res.json();
      const logs = data.logs || [];

      const body = qs("#auditTableBody");
      if (!logs.length) {
        body.innerHTML = '<tr><td colspan="5" class="empty-state">Chưa có nhật ký nào.</td></tr>';
      } else {
        body.innerHTML = logs.map((l) => `<tr>
          <td style="white-space:nowrap">${escapeHtml(timeAgo(l.created_at))}</td>
          <td><strong>${escapeHtml(l.admin_username)}</strong></td>
          <td><span class="action-badge badge-${l.action.includes('delete') ? 'admin' : l.action.includes('setup') || l.action.includes('role') ? 'read' : 'write'}">${escapeHtml(l.action)}</span></td>
          <td>${escapeHtml(l.target)}</td>
          <td style="color:var(--text-secondary)">${escapeHtml(l.detail)}</td>
        </tr>`).join("");
      }

      qs("#auditCount").textContent = `${data.total} bản ghi`;
      renderPagination(data.total, auditOffset, PAGE_SIZE, "auditPagination", (off) => {
        auditOffset = off;
        loadAudit();
      });
    } catch (e) {
      console.error("Audit load error:", e);
    }
  }

  /* ===================== INIT ===================== */
  async function init() {
    initTheme();

    // Check auth - try to use existing token
    if (!token) {
      window.location.href = "/login";
      return;
    }

    // Verify admin access
    try {
      const res = await api("/admin/dashboard");
      if (!res.ok) {
        localStorage.removeItem("admin_token");
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
