<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeftBold, ArrowRightBold, Delete, Document, House } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()

const navigationItems = [
  { label: '首页', routeName: 'home', icon: House },
  { label: '笔记列表', routeName: 'note-list', icon: Document },
  { label: '回收站', routeName: 'trash-list', icon: Delete },
]

const sidebarCollapsed = ref(localStorage.getItem('sidebar_collapsed') === 'true')
const isMobile = ref(false)

const currentUser = computed(() => {
  const raw = localStorage.getItem('current_user')
  return raw ? JSON.parse(raw) : null
})

const syncViewportState = () => {
  isMobile.value = window.innerWidth <= 980
}

const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value
  localStorage.setItem('sidebar_collapsed', String(sidebarCollapsed.value))
}

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

onMounted(() => {
  syncViewportState()
  window.addEventListener('resize', syncViewportState)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', syncViewportState)
})
</script>

<template>
  <div class="workspace-shell" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <aside class="workspace-sidebar" :class="{ 'is-collapsed': sidebarCollapsed && !isMobile }">
      <div class="sidebar-stack">
        <div class="sidebar-top">
          <div class="sidebar-brand" :class="{ 'is-collapsed': sidebarCollapsed && !isMobile }">
            <p v-if="!sidebarCollapsed || isMobile" class="sidebar-kicker">MoonBirdNotes</p>
            <h2>{{ sidebarCollapsed && !isMobile ? 'MB' : '控制台' }}</h2>
          </div>

          <button class="collapse-button" type="button" @click="toggleSidebar">
            <el-icon v-if="sidebarCollapsed"><ArrowRightBold /></el-icon>
            <el-icon v-else><ArrowLeftBold /></el-icon>
          </button>
        </div>

        <nav class="sidebar-nav" :class="{ 'is-collapsed': sidebarCollapsed && !isMobile }">
          <button
            v-for="item in navigationItems"
            :key="item.routeName"
            type="button"
            class="nav-item"
            :class="{ 'is-active': route.name === item.routeName, 'is-collapsed': sidebarCollapsed && !isMobile }"
            @click="goToRoute(item.routeName)"
          >
            <span class="nav-badge">
              <el-icon><component :is="item.icon" /></el-icon>
            </span>
            <span v-if="!sidebarCollapsed || isMobile">{{ item.label }}</span>
          </button>
        </nav>

        <div class="sidebar-footer" :class="{ 'is-collapsed': sidebarCollapsed && !isMobile }">
          <p v-if="!sidebarCollapsed || isMobile">{{ currentUser?.username || '管理员' }}</p>
          <el-button plain @click="logout">
            <span v-if="sidebarCollapsed && !isMobile">退出</span>
            <span v-else>退出登录</span>
          </el-button>
        </div>
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
  min-height: 100svh;
  transition: grid-template-columns 0.24s ease;
}

.workspace-shell.sidebar-collapsed {
  grid-template-columns: 98px minmax(0, 1fr);
}

.workspace-sidebar {
  position: sticky;
  top: 0;
  min-height: 100vh;
  min-height: 100svh;
  padding: 22px 18px;
  border-right: 1px solid rgba(148, 163, 184, 0.16);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.72), rgba(255, 255, 255, 0.52)),
    rgba(255, 255, 255, 0.52);
  backdrop-filter: blur(18px);
}

.sidebar-stack {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 24px;
}

.sidebar-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.sidebar-brand {
  min-width: 0;
}

.sidebar-brand.is-collapsed {
  display: grid;
  justify-items: center;
  width: 100%;
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

.collapse-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.88);
  color: var(--brand-navy);
  cursor: pointer;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

.collapse-button:hover {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.22);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
}

.sidebar-nav {
  display: grid;
  gap: 10px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 50px;
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

.nav-item.is-collapsed {
  justify-content: center;
  padding-inline: 10px;
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

.nav-item span:last-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
  font-size: 0.85rem;
  font-weight: 700;
  flex: 0 0 auto;
}

.nav-badge :deep(.el-icon) {
  font-size: 0.95rem;
}

.sidebar-footer {
  display: grid;
  gap: 12px;
  padding-top: 4px;
}

.sidebar-footer.is-collapsed {
  justify-items: center;
}

.sidebar-footer p {
  margin: 0;
  color: var(--ink-soft);
}

.workspace-content {
  min-width: 0;
}

@media (max-width: 1400px) {
  .workspace-shell {
    grid-template-columns: 220px minmax(0, 1fr);
    gap: 18px;
  }

  .workspace-shell.sidebar-collapsed {
    grid-template-columns: 88px minmax(0, 1fr);
  }

  .workspace-sidebar {
    padding-inline: 14px;
  }
}

@media (max-width: 980px) {
  .workspace-shell,
  .workspace-shell.sidebar-collapsed {
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

  .sidebar-stack {
    gap: 18px;
  }

  .sidebar-nav,
  .sidebar-nav.is-collapsed {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .nav-item,
  .nav-item.is-collapsed {
    justify-content: center;
    padding-inline: 12px;
    text-align: center;
  }

  .sidebar-footer {
    padding-bottom: 16px;
  }
}

@media (max-width: 640px) {
  .workspace-shell {
    gap: 16px;
  }

  .workspace-sidebar {
    padding: 14px 12px 0;
  }

  .sidebar-top {
    align-items: center;
  }

  .sidebar-brand h2 {
    font-size: 1.6rem;
  }

  .sidebar-kicker {
    font-size: 0.72rem;
    letter-spacing: 0.14em;
  }

  .sidebar-nav,
  .sidebar-nav.is-collapsed {
    grid-template-columns: 1fr;
  }

  .nav-item,
  .nav-item.is-collapsed {
    justify-content: flex-start;
    text-align: left;
  }

  .sidebar-footer,
  .sidebar-footer.is-collapsed {
    justify-items: stretch;
  }

  .sidebar-footer :deep(.el-button) {
    width: 100%;
  }
}
</style>
