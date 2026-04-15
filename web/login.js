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

let currentMode = "login";

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

    // Store auth
    localStorage.setItem("auth_token", data.access_token);
    localStorage.setItem("username", username);

    // Redirect to main workspace
    window.location.href = "/";
  } catch (err) {
    authError.textContent = err.message;
  } finally {
    btnSubmit.disabled = false;
    btnSubmit.textContent = currentMode === "login" ? "Đăng nhập ngay" : "Đăng ký ngay";
  }
});

/* ---- Check if already logged in ---- */
(function checkAuth() {
  const token = localStorage.getItem("auth_token") || localStorage.getItem("access_token");
  if (token) {
    window.location.href = "/";
  }
})();
