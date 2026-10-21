<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Icon } from '@iconify/vue'

import api, { setCurrentUser } from '../services/api'
import birdMark from '../assets/moonbird-mark.png'
import deskImage from '../assets/login-desk-photo.png'

const router = useRouter()
const loading = ref(false)

const form = reactive({
  username: '',
  password: '',
  remember: true,
})

const resolveLoginError = (error) => {
  const status = error.response?.status

  if (status === 400 || status === 401) return '用户名或密码不正确。'

  if (status === 429) return '尝试过于频繁，请稍候。'

  if (!status) {
    return '服务连接失败，请确认后端已启动。'
  }

  if (status >= 500) {
    return '服务器暂时无响应，请稍后再试。'
  }

  return '登录失败，请重新尝试。'
}

const submitLogin = async () => {
  if (!form.username || !form.password) {
    ElMessage({
      type: 'warning',
      message: '请填写用户名与密码。',
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

    setCurrentUser(data.user || null)

    ElMessage.success('登录成功。')
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
    <section class="login-hero" aria-label="MoonBirdNotes 登录介绍">
      <div class="brand-lockup fade-rise-enter">
        <img :src="birdMark" alt="" aria-hidden="true" />
        <span>MoonBirdNotes</span>
      </div>

      <div class="hero-copy fade-rise-enter">
        <h1>知识记录，有序归档。</h1>
        <p>
          统一收纳笔记与日记。
          <br />
          精准检索历史内容。
        </p>
      </div>

      <section class="desk-showcase fade-rise-enter-delay" aria-label="书桌能力">
        <figure class="desk-photo">
          <img :src="deskImage" alt="笔记本、咖啡与钢笔构成的书桌氛围图" />
        </figure>

        <div class="feature-stack">
          <article class="feature-row">
            <span class="feature-icon"><Icon icon="solar:notebook-minimalistic-bold-duotone" /></span>
            <div>
              <h2>系统记录</h2>
              <p>集中保存笔记、日记与创作素材。</p>
            </div>
          </article>

          <article class="feature-row">
            <span class="feature-icon"><Icon icon="solar:magnifer-bold-duotone" /></span>
            <div>
              <h2>高效检索</h2>
              <p>通过搜索与标签定位目标内容。</p>
            </div>
          </article>

          <article class="feature-row">
            <span class="feature-icon"><Icon icon="solar:shield-check-bold-duotone" /></span>
            <div>
              <h2>权限可控</h2>
              <p>本地优先存储，数据权限清晰可靠。</p>
            </div>
          </article>
        </div>
      </section>

      <p class="page-signature">© 2026 MoonBirdNotes · 记录与归档管理系统</p>
    </section>

    <section class="login-panel-wrap" aria-label="登录表单">
      <div class="login-panel fade-rise-enter-delay">
        <div class="panel-head">
          <h2>进入书桌</h2>
          <p class="panel-text">管理员登录后可管理全部记录。</p>
        </div>

        <el-form class="login-form" label-position="top" @submit.prevent="submitLogin">
          <el-form-item label="用户名">
            <el-input
              v-model="form.username"
              size="large"
              placeholder="用户名"
              autocomplete="username"
            >
              <template #prefix>
                <Icon icon="solar:user-rounded-linear" />
              </template>
            </el-input>
          </el-form-item>

          <el-form-item label="密码">
            <el-input
              v-model="form.password"
              size="large"
              type="password"
              placeholder="密码"
              show-password
              autocomplete="current-password"
              @keyup.enter="submitLogin"
            >
              <template #prefix>
                <Icon icon="solar:lock-password-linear" />
              </template>
            </el-input>
          </el-form-item>

          <div class="form-options">
            <el-checkbox v-model="form.remember">记住我</el-checkbox>
            <button type="button">忘记密码？</button>
          </div>

          <el-button class="login-button" type="primary" size="large" :loading="loading" @click="submitLogin">
            登录并进入
          </el-button>
        </el-form>

      </div>

      <p class="policy-note">
        <Icon icon="solar:shield-check-linear" />
        登录即表示你同意 MoonBirdNotes 的
        <a href="#">隐私政策</a>
        与
        <a href="#">使用条款</a>
      </p>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  position: relative;
  display: grid;
  grid-template-columns: minmax(560px, 1.08fr) minmax(400px, 0.78fr);
  height: 100vh;
  height: 100svh;
  max-height: 100svh;
  overflow: hidden;
  background: var(--app-background);
}

.login-page::before {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: min(46vh, 430px);
  background:
    linear-gradient(180deg, transparent, color-mix(in srgb, var(--page-bg) 34%, transparent) 52%, color-mix(in srgb, var(--page-bg) 72%, transparent)),
    url('../assets/login-landscape-bg.png') left bottom / 100% auto no-repeat;
  opacity: 0.92;
  content: '';
  pointer-events: none;
}

.login-page::after {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(color-mix(in srgb, var(--border-soft) 20%, transparent) 1px, transparent 1px),
    linear-gradient(90deg, color-mix(in srgb, var(--border-soft) 18%, transparent) 1px, transparent 1px);
  background-size: 34px 34px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.45), transparent 80%);
  content: '';
  pointer-events: none;
}

.login-hero,
.login-panel-wrap {
  position: relative;
  z-index: 1;
}

.login-hero {
  display: grid;
  grid-template-rows: auto auto auto 1fr;
  align-content: start;
  min-width: 0;
  min-height: 0;
  padding: clamp(34px, 5vh, 56px) clamp(34px, 5.8vw, 104px) 24px;
  color: var(--brand-navy);
}

.brand-lockup {
  display: inline-flex;
  align-items: center;
  gap: 14px;
  width: fit-content;
  color: var(--brand-blue);
  font-size: 1.05rem;
  font-weight: 900;
  letter-spacing: 0;
  text-transform: uppercase;
}

.brand-lockup img {
  width: 34px;
  height: 34px;
  object-fit: contain;
}

.hero-copy {
  margin-top: clamp(42px, 6vh, 68px);
}

.hero-copy h1 {
  max-width: 720px;
  margin: 0;
  color: var(--text-primary);
  font-size: clamp(3.7rem, 5.25vw, 6.45rem);
  font-weight: 950;
  line-height: 0.95;
  text-wrap: balance;
  text-shadow: 0 12px 34px rgba(88, 54, 28, 0.14);
}

.hero-copy p {
  margin: 22px 0 0;
  color: var(--text-muted);
  font-size: clamp(1.08rem, 1.28vw, 1.42rem);
  font-weight: 640;
  line-height: 1.55;
}

.desk-showcase {
  display: grid;
  grid-template-columns: minmax(320px, 0.95fr) minmax(280px, 0.9fr);
  width: min(880px, 100%);
  min-height: clamp(286px, 32vh, 342px);
  margin-top: 28px;
  overflow: hidden;
  border: 1px solid var(--border-soft);
  border-radius: 16px;
  background: var(--panel-background-raised);
  box-shadow: var(--shadow-soft), var(--inset-highlight);
  backdrop-filter: blur(18px);
}

.desk-photo {
  position: relative;
  min-height: 100%;
  margin: 0;
  overflow: hidden;
}

.desk-photo::after {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(90deg, rgba(55, 34, 20, 0.08), transparent 36%),
    linear-gradient(180deg, transparent 54%, rgba(255, 247, 234, 0.1));
  content: '';
  pointer-events: none;
}

.desk-photo img {
  display: block;
  width: 100%;
  height: 100%;
  min-height: clamp(286px, 32vh, 342px);
  object-fit: cover;
  filter: sepia(0.26) saturate(0.72) contrast(0.94) brightness(var(--media-brightness));
}

.feature-stack {
  display: grid;
  align-content: center;
  padding: 18px 34px 18px 30px;
}

.feature-row {
  display: grid;
  grid-template-columns: 50px minmax(0, 1fr);
  gap: 18px;
  align-items: center;
  min-height: clamp(78px, 8.8vh, 94px);
}

.feature-row + .feature-row {
  border-top: 1px solid rgba(123, 83, 58, 0.12);
}

.feature-icon {
  display: grid;
  place-items: center;
  width: 50px;
  height: 50px;
  border: 1px solid rgba(179, 132, 50, 0.18);
  border-radius: 50%;
  background: var(--control-selected-background);
  color: var(--brand-blue);
  font-size: 1.55rem;
}

.feature-row h2 {
  margin: 0 0 6px;
  color: var(--text-primary);
  font-size: 1.1rem;
  font-weight: 900;
}

.feature-row p {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.92rem;
  font-weight: 600;
  line-height: 1.55;
}

.page-signature {
  align-self: end;
  margin: 18px 0 0;
  color: rgba(104, 88, 75, 0.58);
  font-size: 0.9rem;
  font-weight: 650;
  text-align: center;
}

.login-panel-wrap {
  display: grid;
  align-content: center;
  justify-items: center;
  min-width: 0;
  min-height: 0;
  padding: 34px clamp(40px, 5.2vw, 86px) 34px 22px;
}

.login-panel {
  width: min(100%, 604px);
  min-height: 540px;
  padding: 52px 52px 38px;
  border: 1px solid var(--border-soft);
  border-radius: 22px;
  background: var(--overlay-background);
  box-shadow: var(--shadow-soft), var(--inset-highlight);
  backdrop-filter: blur(22px);
}

.panel-head {
  margin-bottom: 32px;
}

.panel-head h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: clamp(2.35rem, 3.1vw, 3.15rem);
  font-weight: 950;
  line-height: 1.05;
}

.panel-text {
  margin: 10px 0 0;
  color: var(--text-muted);
  font-size: 1.08rem;
  font-weight: 640;
}

.login-form :deep(.el-form-item) {
  margin-bottom: 20px;
}

.login-form :deep(.el-form-item__label) {
  margin-bottom: 10px;
  color: var(--text-secondary);
  font-size: 0.95rem;
  font-weight: 850;
}

.login-form :deep(.el-input__wrapper) {
  min-height: 58px;
  padding: 0 18px;
  border-radius: 9px;
  background: var(--control-background);
  box-shadow: 0 0 0 1px rgba(123, 83, 58, 0.14) inset;
  transition:
    box-shadow 0.18s var(--motion-calm),
    background 0.18s var(--motion-calm);
}

.login-form :deep(.el-input__wrapper.is-focus) {
  background: var(--panel-background-raised);
  box-shadow:
    0 0 0 1px rgba(150, 70, 38, 0.38) inset,
    0 14px 30px rgba(150, 70, 38, 0.1);
}

.login-form :deep(.el-input__prefix) {
  color: rgba(143, 63, 35, 0.72);
  font-size: 1.08rem;
}

.login-form :deep(.el-input__inner) {
  color: var(--text-primary);
  font-weight: 680;
}

.login-form :deep(.el-input__inner::placeholder) {
  color: var(--text-muted);
}

.form-options {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin: 0 0 24px;
}

.form-options :deep(.el-checkbox) {
  height: auto;
  color: var(--text-muted);
  font-weight: 650;
}

.form-options :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
  border-color: var(--brand-blue);
  background-color: var(--brand-blue);
}

.form-options :deep(.el-checkbox__input.is-checked + .el-checkbox__label) {
  color: var(--text-muted);
}

.form-options button {
  border: 0;
  background: transparent;
  color: var(--brand-blue);
  cursor: pointer;
  font: inherit;
  font-weight: 760;
}

.login-button {
  width: 100%;
  min-height: 58px;
  border: 1px solid rgba(150, 70, 38, 0.18) !important;
  border-radius: 9px !important;
  background: linear-gradient(180deg, #c3673e, #a64227) !important;
  color: var(--text-on-accent) !important;
  font-size: 1.05rem;
  font-weight: 900;
  box-shadow: 0 16px 28px rgba(150, 70, 38, 0.2) !important;
}

.login-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 20px 34px rgba(150, 70, 38, 0.24) !important;
}

.policy-note {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  margin: 22px 0 0;
  color: var(--text-muted);
  font-size: 0.9rem;
  font-weight: 650;
  text-align: center;
}

.policy-note a {
  color: var(--brand-blue);
  font-weight: 840;
}

@media (max-width: 1360px) {
  .login-page {
    grid-template-columns: minmax(500px, 1fr) minmax(370px, 0.78fr);
  }

  .login-hero {
    padding-inline: clamp(28px, 4.5vw, 68px);
  }

  .desk-showcase {
    grid-template-columns: minmax(300px, 0.92fr) minmax(260px, 0.9fr);
  }

  .login-panel {
    min-height: 512px;
    padding: 44px 38px 34px;
  }
}

@media (max-width: 1080px) {
  .login-page {
    grid-template-columns: minmax(410px, 1fr) minmax(340px, 0.82fr);
    overflow: hidden;
  }

  .login-page::before {
    right: -42%;
    left: -34%;
    height: 340px;
    background-size: auto 100%;
  }

  .login-hero {
    min-height: 0;
    padding: 34px 24px 20px;
  }

  .hero-copy {
    margin-top: 38px;
  }

  .hero-copy h1 {
    font-size: clamp(3.1rem, 5vw, 4.2rem);
  }

  .hero-copy p {
    font-size: 1rem;
  }

  .desk-showcase {
    width: 100%;
  }

  .page-signature {
    display: none;
  }

  .login-panel-wrap {
    padding: 24px 22px;
  }

  .login-panel {
    width: min(100%, 620px);
    min-height: 486px;
    padding: 38px 30px 30px;
  }

  .panel-head h2 {
    font-size: 2.1rem;
  }

  .login-form :deep(.el-input__wrapper),
  .login-button {
    min-height: 54px;
  }
}

@media (max-width: 820px) {
  .login-page {
    grid-template-columns: 1fr;
    height: auto;
    min-height: 100svh;
    max-height: none;
    overflow-y: auto;
  }

  .login-hero {
    display: none;
  }

  .login-panel-wrap {
    padding: 22px 18px;
  }
}

/* 浏览器放大会减少可用高度，登录页必须允许完整表单滚动出现。 */
@media (max-height: 760px) {
  .login-page {
    height: auto;
    min-height: 100svh;
    max-height: none;
    overflow-y: auto;
  }
}

@media (max-width: 720px) {
  .login-hero {
    padding-inline: 18px;
  }

  .brand-lockup {
    gap: 10px;
    font-size: 0.9rem;
  }

  .brand-lockup img {
    width: 30px;
    height: 30px;
  }

  .hero-copy {
    margin-top: 44px;
  }

  .hero-copy h1 {
    font-size: 3.25rem;
  }

  .hero-copy p {
    margin-top: 22px;
    font-size: 1.1rem;
  }

  .desk-showcase {
    grid-template-columns: 1fr;
    min-height: 0;
    border-radius: 14px;
  }

  .desk-photo img {
    min-height: 250px;
    aspect-ratio: 1.36;
  }

  .feature-stack {
    padding: 18px 22px 20px;
  }

  .feature-row {
    min-height: 92px;
    grid-template-columns: 48px minmax(0, 1fr);
    gap: 16px;
  }

  .feature-icon {
    width: 48px;
    height: 48px;
  }

  .login-panel-wrap {
    padding-inline: 18px;
  }

  .login-panel {
    padding: 36px 24px 28px;
    border-radius: 18px;
  }

  .panel-head {
    margin-bottom: 30px;
  }

  .login-form :deep(.el-input__wrapper),
  .login-button {
    min-height: 58px;
  }

  .form-options {
    align-items: flex-start;
  }

  .policy-note {
    flex-wrap: wrap;
    margin-top: 24px;
  }
}

@media (max-width: 420px) {
  .hero-copy h1 {
    font-size: 2.7rem;
  }

  .feature-row {
    grid-template-columns: 1fr;
    gap: 10px;
    padding: 16px 0;
  }

  .login-panel {
    padding: 30px 18px 24px;
  }
}
</style>
