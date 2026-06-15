<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import api from '../services/api'

const router = useRouter()
const creating = ref(false)

const currentUser = computed(() => {
  const raw = localStorage.getItem('current_user')
  return raw ? JSON.parse(raw) : null
})

const goToNotes = () => {
  router.push('/notes')
}

const createNewNote = async () => {
  creating.value = true

  try {
    const { data } = await api.post('/notes/create/', {
      title: '未命名笔记',
      markdown_content: '',
      tag_names: ['未分类'],
    })

    ElMessage.success('笔记创建成功，正在跳转...')
    // 跳转到编辑页面
    router.push({ name: 'note-edit', params: { id: data.id } })
  } catch (error) {
    const detail =
      error.response?.data?.title?.[0] ||
      error.response?.data?.tag_names?.[0] ||
      error.response?.data?.detail ||
      '创建笔记失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <main class="home-page page-shell">
    <WorkspaceShell>
      <section class="home-stage">
        <div class="home-topbar">
          <div>
            <p class="home-brand">MoonBirdNotes</p>
            <h1>个人知识库工作台</h1>
          </div>
        </div>

        <div class="home-grid">
          <div class="home-intro">
            <p class="home-kicker">Current Access</p>
            <h2>欢迎回来，{{ currentUser?.username || '管理员' }}</h2>
            <p>
              当前已经具备管理员登录、Markdown 笔记上传和笔记列表展示能力。你可以继续进入笔记列表，
              管理已经上传的内容。
            </p>

            <div class="home-cta">
              <el-button class="cta-button" type="primary" size="large" @click="createNewNote" :loading="creating">
                创建笔记
              </el-button>
              <el-button class="cta-button-secondary" size="large" @click="goToNotes">
                查看笔记列表
              </el-button>
            </div>
          </div>

          <div class="home-status">
            <div class="status-line">
              <span>登录状态</span>
              <strong>已认证</strong>
            </div>
            <div class="status-line">
              <span>权限角色</span>
              <strong>超级管理员</strong>
            </div>
            <div class="status-line">
              <span>当前重点</span>
              <strong>笔记列表</strong>
            </div>
          </div>
        </div>
      </section>
    </WorkspaceShell>
  </main>
</template>

<style scoped>
.home-page {
  padding: 20px;
}

.home-stage {
  min-height: calc(100vh - 20px);
  min-height: calc(100svh - 20px);
  margin-top: 20px;
  padding: 32px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 32px;
  background:
    linear-gradient(160deg, rgba(255, 255, 255, 0.82), rgba(255, 255, 255, 0.62)),
    radial-gradient(circle at top right, rgba(29, 78, 216, 0.16), transparent 28%);
  box-shadow: var(--shadow-soft);
}

.home-topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.home-brand,
.home-kicker {
  margin: 0 0 10px;
  color: var(--brand-blue);
  font-size: 0.86rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.home-topbar h1 {
  margin: 0;
  font-size: clamp(2rem, 4vw, 3.8rem);
  line-height: 1;
  letter-spacing: -0.05em;
}

.home-grid {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: 28px;
  margin-top: 64px;
}

.home-intro h2 {
  margin: 0;
  font-size: clamp(1.8rem, 3vw, 3rem);
  line-height: 1.05;
  letter-spacing: -0.04em;
}

.home-intro p:last-of-type {
  max-width: 620px;
  margin: 18px 0 0;
  color: var(--ink-soft);
  font-size: 1rem;
  line-height: 1.9;
}

.home-cta {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 28px;
}

.cta-button {
  min-height: 50px;
  padding-inline: 24px;
  border: none;
  border-radius: 16px;
  background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 46%, #f59e0b 160%);
  box-shadow: 0 18px 36px rgba(37, 99, 235, 0.24);
}

.cta-button-secondary {
  min-height: 50px;
  padding-inline: 24px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.82);
  color: var(--brand-navy);
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.cta-button-secondary:hover {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.3);
  background: rgba(255, 255, 255, 0.95);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.1);
}

.home-status {
  align-self: end;
  padding: 10px 0;
}

.status-line {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 22px 0;
  border-bottom: 1px solid rgba(15, 23, 42, 0.1);
}

.status-line span {
  color: var(--ink-soft);
}

.status-line strong {
  color: var(--brand-navy);
}

@media (max-width: 980px) {
  .home-page {
    padding: 16px;
  }

  .home-stage {
    min-height: auto;
    margin-top: 0;
    padding: 24px;
    border-radius: 24px;
  }

  .home-topbar,
  .home-grid {
    grid-template-columns: 1fr;
    display: grid;
  }

  .home-grid {
    margin-top: 36px;
  }
}

@media (max-width: 640px) {
  .home-stage {
    padding: 20px;
    border-radius: 22px;
  }

  .home-topbar h1 {
    font-size: 2rem;
  }

  .home-intro h2 {
    font-size: 1.6rem;
  }

  .status-line {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
    padding: 18px 0;
  }

  .cta-button {
    width: 100%;
  }

  .cta-button-secondary {
    width: 100%;
  }
}
</style>
