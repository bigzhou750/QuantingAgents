<template>
  <div class="register-page">
    <el-card class="register-card" shadow="always">
      <div class="header">
        <img src="/logo.svg" alt="智能投研助手" class="logo" />
        <h1>创建账号</h1>
        <p>注册后开始使用独立的投资研究空间</p>
      </div>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" size="large">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" type="email" autocomplete="email" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm_password">
          <el-input v-model="form.confirm_password" type="password" show-password autocomplete="new-password" @keyup.enter="submit" />
        </el-form-item>
        <el-form-item prop="agreement">
          <el-checkbox v-model="form.agreement">我同意用户协议并确认提供的信息真实有效</el-checkbox>
        </el-form-item>
        <el-button type="primary" :loading="loading" class="submit" @click="submit">注册</el-button>
        <el-button link class="login-link" @click="router.push('/login')">已有账号，返回登录</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref()
const loading = ref(false)
const form = reactive({ username: '', email: '', password: '', confirm_password: '', agreement: false })
const rules: Record<string, any[]> = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }, { min: 3, max: 50, message: '用户名长度为 3-50 位', trigger: 'blur' }],
  email: [{ required: true, message: '请输入邮箱', trigger: 'blur' }, { type: 'email', message: '请输入有效邮箱', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }, { min: 8, message: '密码至少 8 位', trigger: 'blur' }],
  confirm_password: [{ required: true, message: '请确认密码', trigger: 'blur' }, { validator: (_rule: unknown, value: string, callback: (error?: Error) => void) => value === form.password ? callback() : callback(new Error('两次输入的密码不一致')), trigger: 'blur' }],
  agreement: [{ validator: (_rule: unknown, value: boolean, callback: (error?: Error) => void) => value ? callback() : callback(new Error('请先同意用户协议')), trigger: 'change' }]
}

const submit = async () => {
  await formRef.value.validate()
  loading.value = true
  try {
    if (await authStore.register(form)) await router.push('/login')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    const response = await authApi.registrationStatus()
    if (!response.data?.enabled) {
      await router.replace('/login')
    }
  } catch {
    // 查询失败时由后端注册接口继续兜底拒绝
  }
})
</script>

<style scoped>
.register-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px; background: #f4f6f8; }
.register-card { width: min(100%, 420px); }
.header { text-align: center; margin-bottom: 20px; }
.logo { width: 56px; height: 56px; }
.header h1 { margin: 12px 0 6px; }
.header p { margin: 0; color: #667085; }
.submit { width: 100%; }
.login-link { display: block; margin: 12px auto 0; }
</style>
