<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const navigationItems = [
  { label: '首页', routeName: 'home' },
  { label: '笔记列表', routeName: 'note-list' },
  { label: '回收站', routeName: 'trash-list' },
]

const currentUser = computed(() => {
  const raw = localStorage.getItem('current_user')
  return raw ? JSON.parse(raw) : null
})

const logout = () => {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('current_user')
  router.push('/login')
}

const goToRoute = (routeName) => {
  if (route.name === routeName) {
    return
  }

  router.push({ name: routeName })
}
</script>

<template>
  <div class="workspace-shell">
    <aside class="workspace-sidebar">
      <div class="sidebar-brand">
        <p class="sidebar-kicker">MoonBirdNotes</p>
        <h2>控制台</h2>
      </div>

      <nav class="sidebar-nav">
        <button
          v-for="item in navigationItems"
          :key="item.routeName"
          type="button"
          class="nav-item"
          :class="{ 'is-active': route.name === item.routeName }"
          @click="goToRoute(item.routeName)"
        >
          {{ item.label }}
        </button>
      </nav>

      <div class="sidebar-footer">
        <p>{{ currentUser?.username || '管理员' }}</p>
        <el-button plain @click="logout">退出登录</el-button>
      </div>
    </aside>

    <section class="workspace-content">
      <slot />
    </section>
  </div>
</template>

<style scoped>
.workspace-shell {
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr);
  gap: 24px;
  min-height: 100vh;
}

.workspace-sidebar {
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 100vh;
  padding: 28px 22px;
  border-right: 1px solid rgba(148, 163, 184, 0.16);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.72), rgba(255, 255, 255, 0.52)),
    rgba(255, 255, 255, 0.52);
  backdrop-filter: blur(18px);
}

.sidebar-kicker {
  margin: 0 0 10px;
  color: var(--brand-blue);
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.sidebar-brand h2 {
  margin: 0;
  color: var(--brand-navy);
  font-size: 2rem;
  letter-spacing: -0.05em;
}

.sidebar-nav {
  display: grid;
  gap: 10px;
  margin-top: 28px;
}

.nav-item {
  padding: 14px 16px;
  border: 1px solid transparent;
  border-radius: 16px;
  background: transparent;
  color: var(--brand-navy);
  text-align: left;
  cursor: pointer;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease;
}

.nav-item:hover {
  transform: translateX(2px);
  border-color: rgba(37, 99, 235, 0.16);
  background: rgba(37, 99, 235, 0.05);
}

.nav-item.is-active {
  border-color: rgba(37, 99, 235, 0.18);
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.12), rgba(245, 158, 11, 0.08));
  color: var(--brand-blue);
  font-weight: 700;
}

.sidebar-footer {
  display: grid;
  gap: 12px;
}

.sidebar-footer p {
  margin: 0;
  color: var(--ink-soft);
}

.workspace-content {
  min-width: 0;
}

@media (max-width: 980px) {
  .workspace-shell {
    grid-template-columns: 1fr;
  }

  .workspace-sidebar {
    position: static;
    min-height: auto;
    padding: 18px 16px 0;
    border-right: none;
    border-bottom: 1px solid rgba(148, 163, 184, 0.16);
    background: transparent;
    backdrop-filter: none;
  }

  .sidebar-nav {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .sidebar-footer {
    margin-top: 16px;
    padding-bottom: 16px;
  }
}
</style>
