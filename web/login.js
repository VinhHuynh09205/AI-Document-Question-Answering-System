/* ================================================================
   ChatBoxAI – Login Page Logic
   ================================================================ */

const tabLogin = document.getElementById("tabLogin");
const tabRegister = document.getElementById("tabRegister");
const formTitle = document.getElementById("formTitle");
const formSubtitle = document.getElementById("formSubtitle");
const authForm = document.getElementById("authForm");
const btnSubmit = document.getElementById("btnSubmit");
const authError = document.getElementById("authError");
const confirmGroup = document.getElementById("confirmGroup");
const confirmInput = document.getElementById("authConfirmPassword");
const togglePassword = document.getElementById("togglePassword");
const passwordInput = document.getElementById("authPassword");
const forgotPasswordLink = document.getElementById("forgotPasswordLink");
const btnGoogleLogin = document.getElementById("btnGoogleLogin");
const btnGithubLogin = document.getElementById("btnGithubLogin");

let currentMode = "login";
const AUTH_ROLE_KEY = "user_role";

function normalizeRole(role) {
  return String(role || "").trim().toLowerCase() === "admin" ? "admin" : "user";
}

function getRedirectPathByRole(role) {
  return normalizeRole(role) === "admin" ? "/admin" : "/";
}

function persistAuthSession(authPayload, fallbackUsername = "", resolvedRole = null) {
  const token = String(authPayload?.access_token || "").trim();
  const username = String(authPayload?.username || fallbackUsername || "").trim();
  const role = normalizeRole(resolvedRole || authPayload?.role);

  if (token) {
    localStorage.setItem("auth_token", token);
    if (role === "admin") {
      localStorage.setItem("admin_token", token);
    } else {
      localStorage.removeItem("admin_token");
    }
  }

  if (username) {
    localStorage.setItem("username", username);
  }
  localStorage.setItem(AUTH_ROLE_KEY, role);

  return role;
}

async function resolveAuthRole(authPayload) {
  const explicitRole = String(authPayload?.role || "").trim();
  if (explicitRole) {
    return normalizeRole(explicitRole);
  }

  const tokenRole = getRoleFromToken(authPayload?.access_token);
  if (tokenRole) {
    return tokenRole;
  }

  const token = String(authPayload?.access_token || "").trim();
  if (!token) {
    return "user";
  }

  try {
    const res = await fetch("/api/v1/admin/dashboard", {
      headers: { Authorization: "Bearer " + token },
    });
    if (res.ok) {
      return "admin";
    }
  } catch (_) {
    /* fallback to user */
  }

  return "user";
}

function getRoleFromToken(token) {
  try {
    const parts = String(token || "").split(".");
    if (parts.length < 2) return null;

    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
    const payload = JSON.parse(atob(padded));
    if (payload && typeof payload.role === "string") {
      return normalizeRole(payload.role);
    }
  } catch (_) {
    /* ignore malformed token */
  }

  return null;
}

/* ---- Custom modal ---- */
function ensureLoginModal() {
  let modal = document.getElementById("loginUiModal");
  if (modal) return modal;

  modal = document.createElement("div");
  modal.id = "loginUiModal";
  modal.className = "login-ui-modal";
  modal.setAttribute("aria-hidden", "true");
  modal.innerHTML = `
    <div class="login-ui-modal-backdrop" data-role="backdrop">
      <div class="login-ui-modal-dialog" role="dialog" aria-modal="true" aria-labelledby="loginUiModalTitle">
        <div class="login-ui-modal-header">
          <h3 id="loginUiModalTitle" class="login-ui-modal-title"></h3>
          <button type="button" class="login-ui-modal-close" data-role="close" aria-label="Đóng">✕</button>
        </div>
        <p class="login-ui-modal-message" id="loginUiModalMessage"></p>
        <div class="login-ui-modal-fields" id="loginUiModalFields"></div>
        <p class="login-ui-modal-error" id="loginUiModalError"></p>
        <div class="login-ui-modal-actions">
          <button type="button" class="login-ui-modal-btn login-ui-modal-btn-secondary" data-role="cancel">Hủy</button>
          <button type="button" class="login-ui-modal-btn login-ui-modal-btn-primary" data-role="confirm">Xác nhận</button>
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(modal);
  return modal;
}

function openLoginModal(options) {
  const {
    title,
    message,
    fields = [],
    confirmText = "Xác nhận",
    cancelText = "Hủy",
    hideCancel = false,
    validate,
  } = options;

  return new Promise((resolve) => {
    const modal = ensureLoginModal();
    const backdrop = modal.querySelector("[data-role='backdrop']");
    const closeBtn = modal.querySelector("[data-role='close']");
    const cancelBtn = modal.querySelector("[data-role='cancel']");
    const confirmBtn = modal.querySelector("[data-role='confirm']");
    const titleEl = document.getElementById("loginUiModalTitle");
    const messageEl = document.getElementById("loginUiModalMessage");
    const fieldsEl = document.getElementById("loginUiModalFields");
    const errorEl = document.getElementById("loginUiModalError");

    titleEl.textContent = title || "Thông báo";
    messageEl.textContent = message || "";
    errorEl.textContent = "";

    cancelBtn.style.display = hideCancel ? "none" : "inline-flex";
    cancelBtn.textContent = cancelText;
    confirmBtn.textContent = confirmText;

    fieldsEl.innerHTML = "";
    const inputMap = new Map();

    for (const field of fields) {
      const row = document.createElement("div");
      row.className = "login-ui-modal-field";

      const label = document.createElement("label");
      label.className = "login-ui-modal-label";
      label.textContent = field.label || "";

      const input = document.createElement("input");
      input.className = "login-ui-modal-input";
      input.type = field.type || "text";
      input.placeholder = field.placeholder || "";
      input.value = field.defaultValue || "";
      if (field.maxLength) input.maxLength = field.maxLength;
      if (field.autocomplete) input.autocomplete = field.autocomplete;

      row.appendChild(label);
      row.appendChild(input);
      fieldsEl.appendChild(row);
      inputMap.set(field.name, input);
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

    function collectValues() {
      const values = {};
      for (const [name, input] of inputMap.entries()) {
        values[name] = input.value;
      }
      return values;
    }

    function onConfirm() {
      const values = collectValues();
      if (typeof validate === "function") {
        const validationError = validate(values);
        if (validationError) {
          errorEl.textContent = validationError;
          const firstInput = fieldsEl.querySelector("input");
          if (firstInput) firstInput.focus();
          return;
        }
      }
      done(values);
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
      if (event.key === "Enter") {
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
      const firstInput = fieldsEl.querySelector("input");
      if (firstInput) {
        firstInput.focus();
        firstInput.select?.();
      } else {
        confirmBtn.focus();
      }
    });
  });
}

function showLoginAlert(options) {
  return openLoginModal({
    title: options.title,
    message: options.message,
    confirmText: options.confirmText || "Đã hiểu",
    hideCancel: true,
  });
}

/* ---- Tab switching ---- */
tabLogin.addEventListener("click", () => switchTab("login"));
tabRegister.addEventListener("click", () => switchTab("register"));

function switchTab(mode) {
  currentMode = mode;
  authError.textContent = "";
  authForm.reset();

  tabLogin.classList.toggle("active", mode === "login");
  tabRegister.classList.toggle("active", mode === "register");

  if (mode === "login") {
    formTitle.textContent = "Chào mừng trở lại";
    formSubtitle.textContent = "Đăng nhập để tiếp tục phân tích tài liệu của bạn";
    btnSubmit.textContent = "Đăng nhập ngay";
    confirmGroup.style.display = "none";
    if (confirmInput) confirmInput.removeAttribute("required");
  } else {
    formTitle.textContent = "Tạo tài khoản mới";
    formSubtitle.textContent = "Đăng ký để lưu trữ và đồng bộ phiên làm việc";
    btnSubmit.textContent = "Đăng ký ngay";
    confirmGroup.style.display = "flex";
    if (confirmInput) confirmInput.setAttribute("required", "");
  }
}

/* ---- Toggle password visibility ---- */
togglePassword.addEventListener("click", () => {
  const isHidden = passwordInput.type === "password";
  passwordInput.type = isHidden ? "text" : "password";
  togglePassword.querySelector(".eye-icon").style.display = isHidden ? "none" : "block";
  togglePassword.querySelector(".eye-off-icon").style.display = isHidden ? "block" : "none";
});

/* ---- Forgot password ---- */
forgotPasswordLink?.addEventListener("click", async (e) => {
  e.preventDefault();
  authError.textContent = "";

  const input = await openLoginModal({
    title: "Quên Mật Khẩu",
    message: "Nhập email hoặc tài khoản để nhận liên kết đặt lại mật khẩu.",
    confirmText: "Tiếp tục",
    cancelText: "Hủy",
    fields: [
      {
        name: "username",
        label: "Email / Tài khoản",
        placeholder: "nguyen.van.a@example.com",
        type: "text",
        maxLength: 64,
        autocomplete: "username",
      },
    ],
    validate: (values) => {
      if (!String(values.username || "").trim()) {
        return "Vui lòng nhập email hoặc tài khoản.";
      }
      return "";
    },
  });
  if (!input) return;
  const username = String(input.username || "").trim();

  try {
    const redirectUri = `${window.location.origin}/login`;
    const res = await fetch("/api/v1/auth/forgot-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: username.trim(), redirect_uri: redirectUri }),
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Không thể xử lý yêu cầu quên mật khẩu");

    if (!data.reset_token) {
      await showLoginAlert({
        title: "Yêu Cầu Đã Ghi Nhận",
        message: data.message || "Nếu tài khoản tồn tại, hệ thống sẽ gửi liên kết đặt lại mật khẩu.",
      });
      return;
    }

    await runResetPasswordFlow(data.reset_token, username.trim());
  } catch (err) {
    authError.textContent = err.message;
  }
});

btnGoogleLogin?.addEventListener("click", () => startOAuth("google"));
btnGithubLogin?.addEventListener("click", () => startOAuth("github"));

/* ---- Form submit ---- */
authForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  authError.textContent = "";

  const username = document.getElementById("authUsername").value.trim();
  const password = document.getElementById("authPassword").value;

  if (!username || !password) {
    authError.textContent = "Vui lòng nhập đầy đủ thông tin.";
    return;
  }

  if (currentMode === "register") {
    const confirm = confirmInput ? confirmInput.value : "";
    if (password !== confirm) {
      authError.textContent = "Mật khẩu xác nhận không khớp.";
      return;
    }
  }

  btnSubmit.disabled = true;
  btnSubmit.textContent = currentMode === "login" ? "Đang đăng nhập..." : "Đang đăng ký...";

  const endpoint = currentMode === "login" ? "/api/v1/auth/login" : "/api/v1/auth/register";

  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Thao tác thất bại");

    const role = await resolveAuthRole(data);
    persistAuthSession(data, username, role);
    window.location.href = getRedirectPathByRole(role);
  } catch (err) {
    authError.textContent = err.message;
  } finally {
    btnSubmit.disabled = false;
    btnSubmit.textContent = currentMode === "login" ? "Đăng nhập ngay" : "Đăng ký ngay";
  }
});

async function startOAuth(provider) {
  authError.textContent = "";
  try {
    const redirectUri = `${window.location.origin}/login?oauth_provider=${encodeURIComponent(provider)}`;
    const res = await fetch(
      `/api/v1/auth/oauth/${provider}/start?redirect_uri=${encodeURIComponent(redirectUri)}`,
      { method: "GET" }
    );
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Không thể bắt đầu đăng nhập OAuth");
    window.location.href = data.authorization_url;
  } catch (err) {
    authError.textContent = err.message;
  }
}

async function completeOAuthLogin(provider, code, state) {
  const redirectUri = `${window.location.origin}/login?oauth_provider=${encodeURIComponent(provider)}`;
  const res = await fetch(`/api/v1/auth/oauth/${provider}/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, state, redirect_uri: redirectUri }),
  });

  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Đăng nhập OAuth thất bại");

  const role = await resolveAuthRole(data);
  persistAuthSession(data, provider, role);
  window.location.href = getRedirectPathByRole(role);
}

async function runResetPasswordFlow(token, usernameHint = "") {
  const result = await openLoginModal({
    title: "Đổi Mật Khẩu",
    message: "Nhập mật khẩu mới cho tài khoản của bạn.",
    confirmText: "Cập nhật",
    cancelText: "Hủy",
    fields: [
      {
        name: "newPassword",
        label: "Mật khẩu mới",
        placeholder: "Ít nhất 8 ký tự",
        type: "password",
        maxLength: 128,
        autocomplete: "new-password",
      },
      {
        name: "confirmPassword",
        label: "Xác nhận mật khẩu",
        placeholder: "Nhập lại mật khẩu mới",
        type: "password",
        maxLength: 128,
        autocomplete: "new-password",
      },
    ],
    validate: (values) => {
      const newPassword = String(values.newPassword || "");
      const confirmPassword = String(values.confirmPassword || "");
      if (newPassword.length < 8) {
        return "Mật khẩu mới phải có ít nhất 8 ký tự.";
      }
      if (newPassword !== confirmPassword) {
        return "Mật khẩu xác nhận không khớp.";
      }
      return "";
    },
  });

  if (!result) return;
  const newPassword = String(result.newPassword || "");

  const res = await fetch("/api/v1/auth/reset-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, new_password: newPassword }),
  });

  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Không thể đặt lại mật khẩu");

  await showLoginAlert({
    title: "Đổi Mật Khẩu Thành Công",
    message: data.message || "Đặt lại mật khẩu thành công. Vui lòng đăng nhập lại.",
  });
  switchTab("login");
  if (usernameHint) {
    const usernameInput = document.getElementById("authUsername");
    if (usernameInput) usernameInput.value = usernameHint;
  }
}

function clearTransientAuthParams() {
  const url = new URL(window.location.href);
  [
    "code",
    "state",
    "scope",
    "authuser",
    "prompt",
    "error",
    "error_description",
    "reset_token",
  ].forEach((k) => url.searchParams.delete(k));

  const search = url.searchParams.toString();
  const finalUrl = search ? `${url.pathname}?${search}` : url.pathname;
  window.history.replaceState({}, "", finalUrl);
}

async function handleOAuthAndResetCallbacks() {
  const params = new URLSearchParams(window.location.search);

  const resetToken = params.get("reset_token");
  if (resetToken) {
    try {
      await runResetPasswordFlow(resetToken);
    } catch (err) {
      authError.textContent = err.message;
    } finally {
      clearTransientAuthParams();
    }
    return true;
  }

  const oauthError = params.get("error");
  if (oauthError) {
    authError.textContent = "Đăng nhập OAuth bị hủy hoặc thất bại. Vui lòng thử lại.";
    clearTransientAuthParams();
    return true;
  }

  const code = params.get("code");
  const state = params.get("state");
  const provider = params.get("oauth_provider");

  if (!code || !state || !provider) {
    return false;
  }

  try {
    btnSubmit.disabled = true;
    btnSubmit.textContent = "Đang xác thực OAuth...";
    await completeOAuthLogin(provider, code, state);
  } catch (err) {
    authError.textContent = err.message;
    clearTransientAuthParams();
  } finally {
    btnSubmit.disabled = false;
    btnSubmit.textContent = currentMode === "login" ? "Đăng nhập ngay" : "Đăng ký ngay";
  }

  return true;
}

/* ---- Check if already logged in ---- */
async function checkAuth() {
  const token = localStorage.getItem("auth_token") || localStorage.getItem("access_token");
  if (token) {
    const roleFromToken = getRoleFromToken(token);
    if (roleFromToken) {
      localStorage.setItem(AUTH_ROLE_KEY, roleFromToken);
      window.location.href = getRedirectPathByRole(roleFromToken);
      return;
    }

    // Fallback for legacy tokens without role claim
    try {
      const res = await fetch("/api/v1/admin/dashboard", {
        headers: { Authorization: "Bearer " + token },
      });
      if (res.ok) {
        localStorage.setItem(AUTH_ROLE_KEY, "admin");
        window.location.href = "/admin";
        return;
      }
    } catch (_) {
      /* fallback to user route */
    }

    localStorage.setItem(AUTH_ROLE_KEY, "user");
    window.location.href = "/";
  }
}

(async function initAuthPage() {
  const handled = await handleOAuthAndResetCallbacks();
  if (!handled) {
    checkAuth();
  }
})();
