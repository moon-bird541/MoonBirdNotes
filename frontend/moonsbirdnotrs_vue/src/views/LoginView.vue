<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import api from '../services/api'

const router = useRouter()
const loading = ref(false)

const form = reactive({
  username: '',
  password: '',
})

const resolveLoginError = (error) => {
  const status = error.response?.status

  if (status === 400 || status === 401) return '用户名或密码错误'

  if (!status) {
    return '无法连接到服务器，请确认后端服务已经启动。'
  }

  if (status >= 500) {
    return '服务器处理登录请求时发生错误，请稍后重试。'
  }

  return '登录失败，请稍后重试。'
}

const submitLogin = async () => {
  if (!form.username || !form.password) {
    ElMessage({
      type: 'warning',
      message: '请输入用户名和密码',
      duration: 3000,
    })
    return
  }

  loading.value = true

  try {
    const { data } = await api.post('/login/', {
      username: form.username,
      password: form.password,
    })

    localStorage.setItem('access_token', data.access)
    localStorage.setItem('refresh_token', data.refresh)
    localStorage.setItem('current_user', JSON.stringify(data.user))

    ElMessage.success('登录成功，正在进入系统。')
    router.push('/')
  } catch (error) {
    ElMessage({
      type: 'error',
      message: resolveLoginError(error),
      duration: 3000,
    })
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-page page-shell">
    <section class="login-hero">
      <div class="hero-copy fade-rise-enter">
        <p class="hero-brand">MoonBirdNotes</p>
        <h1>把文章、笔记和日记，收进一个真正属于自己的知识库。</h1>
        <p class="hero-text">
          让零散的记录慢慢归于有序，在安静而私密的空间里，留下值得反复回看的内容。
        </p>
      </div>

      <div class="hero-points fade-rise-enter-delay">
        <div class="point-item">
          <span class="point-index">01</span>
          <div>
            <strong>集中管理</strong>
            <p>个人文章、学习笔记与日记统一归档。</p>
          </div>
        </div>
        <div class="point-item">
          <span class="point-index">02</span>
          <div>
            <strong>快速检索</strong>
            <p>后续可扩展搜索与智能问答能力，形成长期知识资产。</p>
          </div>
        </div>
      </div>
    </section>

    <section class="login-panel-wrap">
      <div class="login-panel fade-rise-enter-delay-2">
        <div class="panel-head">
          <h2>进入 MoonBirdNotes</h2>
          <p class="panel-text">当前仅开放管理员访问，请使用系统管理员账号登录。</p>
        </div>

        <el-form class="login-form" label-position="top" @submit.prevent="submitLogin">
          <el-form-item label="用户名">
            <el-input
              v-model="form.username"
              size="large"
              placeholder="请输入用户名"
              autocomplete="username"
            />
          </el-form-item>

          <el-form-item label="密码">
            <el-input
              v-model="form.password"
              size="large"
              type="password"
              placeholder="请输入密码"
              show-password
              autocomplete="current-password"
              @keyup.enter="submitLogin"
            />
          </el-form-item>

          <el-button class="login-button" type="primary" size="large" :loading="loading" @click="submitLogin">
            登录
          </el-button>
        </el-form>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(380px, 460px);
  overflow: hidden;
}

.login-page::before,
.login-page::after {
  content: "";
  position: absolute;
  border-radius: 999px;
  filter: blur(12px);
  pointer-events: none;
}

.login-page::before {
  width: 420px;
  height: 420px;
  top: -120px;
  left: -80px;
  background: rgba(37, 99, 235, 0.18);
}

.login-page::after {
  width: 360px;
  height: 360px;
  right: -80px;
  bottom: -80px;
  background: rgba(245, 158, 11, 0.16);
}

.login-hero {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 100vh;
  min-height: 100svh;
  padding: 72px 8vw 56px;
  color: var(--brand-navy);
}

.hero-copy {
  max-width: 620px;
}

.hero-brand {
  margin: 0 0 18px;
  color: var(--brand-blue);
  font-size: 0.95rem;
  font-weight: 700;
  letter-spacing: 0.2em;
  text-transform: uppercase;
}

.hero-copy h1 {
  margin: 0;
  font-size: clamp(2.8rem, 5vw, 5.2rem);
  line-height: 1.02;
  letter-spacing: -0.05em;
}

.hero-text {
  max-width: 520px;
  margin: 24px 0 0;
  color: var(--ink-soft);
  font-size: 1.02rem;
  line-height: 1.9;
}

.hero-points {
  display: grid;
  gap: 18px;
  max-width: 520px;
}

.point-item {
  display: grid;
  grid-template-columns: 64px 1fr;
  gap: 18px;
  align-items: start;
  padding-top: 18px;
  border-top: 1px solid rgba(15, 23, 42, 0.12);
}

.point-index {
  color: var(--brand-gold);
  font-size: 1.2rem;
  font-weight: 700;
}

.point-item strong {
  display: block;
  margin-bottom: 6px;
  font-size: 1.02rem;
}

.point-item p {
  margin: 0;
  color: var(--ink-soft);
  line-height: 1.7;
}

.login-panel-wrap {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 32px;
}

.login-panel {
  position: relative;
  width: 100%;
  max-width: 430px;
  padding: 38px 34px 30px;
  border: 1px solid var(--border-soft);
  border-radius: 28px;
  background: var(--surface);
  backdrop-filter: blur(24px);
  box-shadow: var(--shadow-soft);
}

.panel-head {
  margin-bottom: 28px;
}

.panel-head h2 {
  margin: 0;
  font-size: 2rem;
  line-height: 1.1;
  letter-spacing: -0.04em;
}

.panel-text {
  margin: 12px 0 0;
  color: var(--ink-soft);
  line-height: 1.7;
}

.login-form :deep(.el-form-item) {
  margin-bottom: 20px;
}

.login-form :deep(.el-form-item__label) {
  color: var(--brand-navy);
  font-weight: 600;
}

.login-form :deep(.el-input__wrapper) {
  min-height: 50px;
  border-radius: 14px;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.18) inset;
}

.login-form :deep(.el-input__wrapper.is-focus) {
  box-shadow:
    0 0 0 1px rgba(37, 99, 235, 0.72) inset,
    0 12px 32px rgba(37, 99, 235, 0.12);
}

.login-button {
  width: 100%;
  min-height: 52px;
  margin-top: 6px;
  border: none;
  border-radius: 16px;
  background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 46%, #f59e0b 160%);
  box-shadow: 0 18px 36px rgba(37, 99, 235, 0.24);
}

.login-button:hover {
  transform: translateY(-1px);
}

@media (max-width: 1080px) {
  .login-page {
    grid-template-columns: 1fr;
  }

  .login-hero {
    min-height: auto;
    padding: 56px 24px 24px;
  }

  .login-panel-wrap {
    padding: 0 24px 40px;
    justify-content: flex-start;
  }
}

@media (max-width: 640px) {
  .login-page {
    overflow: visible;
  }

  .login-hero {
    padding: 40px 20px 16px;
  }

  .hero-copy h1 {
    font-size: 2.3rem;
  }

  .hero-text {
    font-size: 0.95rem;
    line-height: 1.8;
  }

  .hero-points {
    gap: 14px;
  }

  .point-item {
    grid-template-columns: 52px 1fr;
    gap: 14px;
  }

  .login-panel-wrap {
    padding: 0 20px 28px;
  }

  .login-panel {
    padding: 28px 22px 24px;
    border-radius: 22px;
  }

  .panel-head h2 {
    font-size: 1.7rem;
  }
}

@media (max-width: 420px) {
  .hero-copy h1 {
    font-size: 2rem;
  }

  .point-item {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .point-index {
    font-size: 1rem;
  }

  .login-panel-wrap {
    padding: 0 14px 20px;
  }

  .login-panel {
    padding: 24px 18px 20px;
  }
}
</style>
