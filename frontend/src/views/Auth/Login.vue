<template>
  <div class="login-page">
    <!-- Left: Form Panel -->
    <div class="login-left">
      <div class="login-left-inner">
        <!-- Logo -->
        <div class="brand">
          <img src="/logo.svg" alt="智能投研助手" class="brand-logo" />
          <span class="brand-name">智能投研助手</span>
        </div>

        <!-- Form -->
        <div class="form-area">
          <h1 class="form-title">密码登录</h1>

          <el-form
            :model="loginForm"
            :rules="loginRules"
            ref="loginFormRef"
            label-position="top"
            size="large"
            class="login-form"
          >
            <el-form-item label="用户名" prop="username">
              <el-input
                v-model="loginForm.username"
                placeholder="请输入您的用户名"
                class="custom-input"
              />
            </el-form-item>

            <el-form-item label="密码" prop="password">
              <el-input
                v-model="loginForm.password"
                type="password"
                placeholder="请输入您的密码"
                show-password
                class="custom-input"
                @keyup.enter="handleLogin"
              />
            </el-form-item>

            <div class="form-actions">
              <el-button
                class="login-btn"
                :loading="loginLoading"
                @click="handleLogin"
              >
                登 录
              </el-button>
              <a class="forgot-link" href="javascript:void(0)">忘记密码？</a>
            </div>

            <div class="form-links">
              <p v-if="registrationEnabled" class="link-row">
                还没有账号？<a href="javascript:void(0)" @click="router.push('/register')">立即注册</a>
              </p>
            </div>
          </el-form>
        </div>

        <!-- Footer -->
        <div class="login-footer">
          <p>&copy; 2026 智能投研助手 · zhitouagent</p>
          <p class="disclaimer">
            本平台AI分析结果仅供学习研究参考，不构成投资建议。市场有风险，投资需谨慎。
          </p>
        </div>
      </div>
    </div>

    <!-- Right: Animated Gradient Panel -->
    <div class="login-right">
      <div class="gradient-bg"></div>
      <div class="gradient-overlay"></div>
      <!-- Dot grid pattern -->
      <div class="dot-grid"></div>
      <!-- Central visual element -->
      <div class="visual-center">
        <div class="pulse-ring pulse-ring--1"></div>
        <div class="pulse-ring pulse-ring--2"></div>
        <div class="pulse-ring pulse-ring--3"></div>
        <div class="core-icon">
          <svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="8" y="8" width="64" height="64" rx="16" stroke="rgba(255,255,255,0.15)" stroke-width="2"/>
            <path d="M28 52V32l12-8 12 8v20" stroke="rgba(255,255,255,0.6)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M36 52v-12h8v12" stroke="rgba(255,255,255,0.6)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
            <circle cx="40" cy="28" r="3" fill="rgba(255,255,255,0.4)"/>
          </svg>
        </div>
      </div>
      <!-- Floating particles -->
      <div class="particle particle--1"></div>
      <div class="particle particle--2"></div>
      <div class="particle particle--3"></div>
      <div class="particle particle--4"></div>
      <div class="particle particle--5"></div>
      <div class="particle particle--6"></div>
    </div>
    <!-- CI/CD 部署版本标记 -->
    <div style="position:fixed;bottom:8px;right:12px;font-size:11px;color:rgba(255,255,255,0.4);z-index:9999;">
      Build: {{ new Date().toISOString().slice(0, 16) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'

const router = useRouter()
const authStore = useAuthStore()

const loginFormRef = ref()
const loginLoading = ref(false)
const registrationEnabled = ref(true)

const loginForm = reactive({
  username: '',
  password: '',
  rememberMe: false
})

const loginRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }
  ]
}

const handleLogin = async () => {
  if (loginLoading.value) return

  try {
    await loginFormRef.value.validate()

    loginLoading.value = true

    const success = await authStore.login({
      username: loginForm.username,
      password: loginForm.password
    })

    if (success) {
      ElMessage.success('登录成功')
      const redirectPath = authStore.getAndClearRedirectPath()
      router.push(redirectPath)
    } else {
      ElMessage.error('用户名或密码错误')
    }

  } catch (error) {
    const err = error as Error
    if (err.message && !err.message.includes('validate')) {
      ElMessage.error('登录失败，请重试')
    }
  } finally {
    loginLoading.value = false
  }
}

onMounted(async () => {
  try {
    const response = await authApi.registrationStatus()
    registrationEnabled.value = response.data?.enabled ?? true
  } catch {
    registrationEnabled.value = true
  }
})
</script>

<style lang="scss" scoped>
/* ============================================
   LOGIN PAGE — Split-Screen Layout
   Aesthetic: Refined Minimalism + Animated Depth
   ============================================ */

// --- Google Fonts import via CSS ---
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&display=swap');

.login-page {
  display: flex;
  min-height: 100vh;
  font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  overflow: hidden;
}

// ========================
// LEFT PANEL — Form Area
// ========================
.login-left {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #ffffff;
  padding: 48px;
  position: relative;
  z-index: 2;
  min-width: 0;

  @media (max-width: 900px) {
    padding: 32px 24px;
  }
}

.login-left-inner {
  width: 100%;
  max-width: 420px;
  display: flex;
  flex-direction: column;
  min-height: 80vh;
  justify-content: center;
}

// --- Brand ---
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 64px;

  .brand-logo {
    width: 36px;
    height: 36px;
  }

  .brand-name {
    font-size: 20px;
    font-weight: 700;
    color: #0a0a0a;
    letter-spacing: -0.02em;
  }
}

// --- Form Area ---
.form-area {
  flex: 1;
}

.form-title {
  font-size: 36px;
  font-weight: 700;
  color: #0a0a0a;
  margin: 0 0 40px 0;
  letter-spacing: -0.03em;
  line-height: 1.2;
}

.login-form {
  :deep(.el-form-item__label) {
    font-size: 14px;
    font-weight: 500;
    color: #1a1a1a;
    padding-bottom: 8px;
    line-height: 1;
  }

  :deep(.el-form-item) {
    margin-bottom: 24px;
  }

  // Custom input styling — clean, borderless bottom-line style
  :deep(.custom-input) {
    .el-input__wrapper {
      box-shadow: none !important;
      border-radius: 0;
      border-bottom: 1.5px solid #e5e5e5;
      padding: 8px 0;
      transition: border-color 0.3s ease;
      background: transparent;

      &:hover {
        border-bottom-color: #999;
      }

      &.is-focus {
        border-bottom-color: #0a0a0a;
      }
    }

    .el-input__inner {
      font-size: 15px;
      color: #1a1a1a;
      height: 36px;

      &::placeholder {
        color: #c0c0c0;
        font-weight: 300;
      }
    }

    // Password eye icon
    .el-input__suffix {
      .el-icon {
        color: #bbb;
        font-size: 16px;

        &:hover {
          color: #666;
        }
      }
    }
  }
}

// --- Form Actions ---
.form-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 32px;
  margin-bottom: 24px;
}

.login-btn {
  background: #0a0a0a !important;
  color: #fff !important;
  border: none !important;
  border-radius: 28px !important;
  padding: 12px 40px !important;
  font-size: 15px !important;
  font-weight: 500 !important;
  letter-spacing: 0.08em;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: none !important;

  &:hover {
    background: #333 !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15) !important;
  }

  &:active {
    transform: translateY(0);
  }

  &.is-loading {
    opacity: 0.7;
  }
}

.forgot-link {
  font-size: 14px;
  color: #888;
  text-decoration: none;
  transition: color 0.2s;
  cursor: pointer;

  &:hover {
    color: #0a0a0a;
  }
}

// --- Links ---
.form-links {
  margin-top: 8px;
}

.link-row {
  font-size: 14px;
  color: #888;
  margin: 0 0 12px 0;
  line-height: 1.8;

  a {
    color: #0a0a0a;
    font-weight: 600;
    text-decoration: none;
    margin-left: 4px;
    transition: opacity 0.2s;

    &:hover {
      opacity: 0.6;
    }
  }
}

// --- Footer ---
.login-footer {
  margin-top: auto;
  padding-top: 48px;

  p {
    margin: 0;
    font-size: 12px;
    color: #c0c0c0;
    line-height: 1.6;
  }

  .disclaimer {
    margin-top: 4px;
    font-size: 11px;
    color: #d0d0d0;
  }
}

// ========================
// RIGHT PANEL — Animated Gradient
// ========================
.login-right {
  flex: 1;
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;

  @media (max-width: 900px) {
    display: none;
  }
}

// --- Animated gradient background ---
.gradient-bg {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    135deg,
    #0a0a0a 0%,
    #1a1a2e 25%,
    #16213e 50%,
    #0f3460 75%,
    #0a0a0a 100%
  );
  background-size: 400% 400%;
  animation: gradientShift 12s ease infinite;
}

@keyframes gradientShift {
  0% {
    background-position: 0% 50%;
  }
  25% {
    background-position: 100% 0%;
  }
  50% {
    background-position: 100% 100%;
  }
  75% {
    background-position: 0% 100%;
  }
  100% {
    background-position: 0% 50%;
  }
}

// --- Overlay for depth ---
.gradient-overlay {
  position: absolute;
  inset: 0;
  background: radial-gradient(
    ellipse at 30% 50%,
    rgba(30, 64, 175, 0.15) 0%,
    transparent 60%
  );
  animation: overlayPulse 8s ease-in-out infinite alternate;
}

@keyframes overlayPulse {
  0% {
    opacity: 0.6;
    background: radial-gradient(
      ellipse at 30% 50%,
      rgba(30, 64, 175, 0.15) 0%,
      transparent 60%
    );
  }
  50% {
    opacity: 1;
    background: radial-gradient(
      ellipse at 70% 40%,
      rgba(245, 158, 11, 0.08) 0%,
      transparent 60%
    );
  }
  100% {
    opacity: 0.8;
    background: radial-gradient(
      ellipse at 50% 70%,
      rgba(59, 130, 246, 0.12) 0%,
      transparent 60%
    );
  }
}

// --- Dot grid pattern ---
.dot-grid {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(
    rgba(255, 255, 255, 0.06) 1px,
    transparent 1px
  );
  background-size: 24px 24px;
  animation: dotDrift 20s linear infinite;
}

@keyframes dotDrift {
  0% {
    background-position: 0 0;
  }
  100% {
    background-position: 24px 24px;
  }
}

// --- Central visual ---
.visual-center {
  position: relative;
  width: 200px;
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
}

.pulse-ring {
  position: absolute;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.06);
  animation: pulseExpand 4s ease-out infinite;

  &--1 {
    width: 120px;
    height: 120px;
    animation-delay: 0s;
  }

  &--2 {
    width: 180px;
    height: 180px;
    animation-delay: 1.3s;
  }

  &--3 {
    width: 240px;
    height: 240px;
    animation-delay: 2.6s;
  }
}

@keyframes pulseExpand {
  0% {
    transform: scale(0.8);
    opacity: 0;
    border-color: rgba(255, 255, 255, 0.1);
  }
  50% {
    opacity: 1;
    border-color: rgba(255, 255, 255, 0.06);
  }
  100% {
    transform: scale(1.4);
    opacity: 0;
    border-color: rgba(255, 255, 255, 0);
  }
}

.core-icon {
  width: 80px;
  height: 80px;
  animation: coreFloat 6s ease-in-out infinite;

  svg {
    width: 100%;
    height: 100%;
    filter: drop-shadow(0 0 20px rgba(255, 255, 255, 0.05));
  }
}

@keyframes coreFloat {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-8px);
  }
}

// --- Floating particles ---
.particle {
  position: absolute;
  width: 3px;
  height: 3px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 50%;
  animation: particleFloat 10s ease-in-out infinite;

  &--1 {
    top: 15%;
    left: 20%;
    animation-delay: 0s;
    animation-duration: 12s;
  }

  &--2 {
    top: 70%;
    left: 75%;
    animation-delay: -2s;
    animation-duration: 14s;
    width: 2px;
    height: 2px;
  }

  &--3 {
    top: 30%;
    right: 15%;
    animation-delay: -4s;
    animation-duration: 11s;
  }

  &--4 {
    bottom: 20%;
    left: 30%;
    animation-delay: -6s;
    animation-duration: 13s;
    width: 4px;
    height: 4px;
    background: rgba(245, 158, 11, 0.1);
  }

  &--5 {
    top: 50%;
    left: 50%;
    animation-delay: -3s;
    animation-duration: 15s;
    width: 2px;
    height: 2px;
  }

  &--6 {
    top: 85%;
    right: 25%;
    animation-delay: -7s;
    animation-duration: 10s;
    background: rgba(59, 130, 246, 0.12);
  }
}

@keyframes particleFloat {
  0%, 100% {
    transform: translate(0, 0) scale(1);
    opacity: 0.3;
  }
  25% {
    transform: translate(15px, -20px) scale(1.2);
    opacity: 0.8;
  }
  50% {
    transform: translate(-10px, -35px) scale(0.8);
    opacity: 0.4;
  }
  75% {
    transform: translate(20px, -15px) scale(1.1);
    opacity: 0.7;
  }
}

// ========================
// RESPONSIVE
// ========================
@media (max-width: 900px) {
  .login-page {
    flex-direction: column;
  }

  .login-left {
    min-height: 100vh;
    padding: 40px 28px;
  }

  .login-left-inner {
    min-height: auto;
    max-width: 380px;
  }

  .brand {
    margin-bottom: 48px;
  }

  .form-title {
    font-size: 28px;
    margin-bottom: 32px;
  }

  .login-footer {
    padding-top: 32px;
  }
}

@media (max-width: 480px) {
  .login-left {
    padding: 32px 20px;
  }

  .form-title {
    font-size: 24px;
  }

  .login-btn {
    width: 100% !important;
    padding: 12px 24px !important;
  }

  .form-actions {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;

    .forgot-link {
      text-align: center;
    }
  }
}
</style>
