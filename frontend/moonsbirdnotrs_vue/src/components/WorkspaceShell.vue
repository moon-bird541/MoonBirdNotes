<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeftBold, ArrowRightBold, Calendar, CollectionTag, Delete, Document, House, Picture, SwitchButton } from '@element-plus/icons-vue'
import GlobalSearchPanel from './GlobalSearchPanel.vue'
import SettingsPanel from './SettingsPanel.vue'
import api, { clearAuthState } from '../services/api'

const route = useRoute()
const router = useRouter()

const navigationItems = [
  { label: '首页', routeName: 'home', icon: House },
  { label: '笔记列表', routeName: 'note-list', icon: Document },
  { label: '日记', routeName: 'diary', activeRouteNames: ['diary', 'diary-edit'], icon: Calendar },
  { label: '标签管理', routeName: 'tag-management', icon: CollectionTag },
  { label: '图片管理', routeName: 'image-management', icon: Picture },
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

const logout = async () => {
  try {
    await api.post('/logout/')
  } catch {
    // Local logout should still finish if the token was already invalid.
  } finally {
    clearAuthState()
    router.push('/login')
  }
}

const goToRoute = (routeName) => {
  if (route.name === routeName) {
    return
  }

  router.push({ name: routeName })
}

const isNavigationActive = (item) => {
  if (item.activeRouteNames?.includes(route.name)) {
    return true
  }

  return route.name === item.routeName
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
        <div class="sidebar-top" :class="{ 'is-collapsed': sidebarCollapsed && !isMobile }">
          <div class="sidebar-brand" :class="{ 'is-collapsed': sidebarCollapsed && !isMobile }">
            <p v-if="!sidebarCollapsed || isMobile" class="sidebar-kicker">MoonBirdNotes</p>
            <h2>{{ sidebarCollapsed && !isMobile ? 'MB' : '控制台' }}</h2>
          </div>

          <button
            class="collapse-button"
            :class="{ 'is-collapsed': sidebarCollapsed && !isMobile }"
            type="button"
            :aria-label="sidebarCollapsed ? '展开功能栏' : '收起功能栏'"
            @click="toggleSidebar"
          >
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
            :class="{ 'is-active': isNavigationActive(item), 'is-collapsed': sidebarCollapsed && !isMobile }"
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
          <GlobalSearchPanel :collapsed="sidebarCollapsed" :mobile="isMobile" />
          <SettingsPanel :collapsed="sidebarCollapsed" :mobile="isMobile" />
          <button
            class="logout-button"
            :class="{ 'is-collapsed': sidebarCollapsed && !isMobile }"
            type="button"
            :title="sidebarCollapsed && !isMobile ? '退出登录' : undefined"
            @click="logout"
          >
            <el-icon class="logout-icon"><SwitchButton /></el-icon>
            <span v-if="!sidebarCollapsed || isMobile">退出登录</span>
          </button>
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
  position: relative;
  min-height: 100vh;
  min-height: 100svh;
  padding-left: 248px;
  transition: padding-left 0.24s ease;
}

.workspace-shell.sidebar-collapsed {
  padding-left: 98px;
}

.workspace-sidebar {
  position: fixed;
  top: 0;
  left: 0;
  box-sizing: border-box;
  width: 248px;
  min-height: 100vh;
  min-height: 100svh;
  padding: 22px 18px;
  border-right: 1px solid var(--border-soft);
  background: var(--surface);
  backdrop-filter: blur(18px);
  overflow-x: hidden;
  transition:
    width 0.24s ease,
    padding 0.24s ease;
  z-index: 100;
}

.workspace-sidebar.is-collapsed {
  width: 98px;
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

.sidebar-top.is-collapsed {
  display: grid;
  justify-items: center;
  gap: 14px;
}

.sidebar-brand {
  min-width: 0;
}

.sidebar-brand.is-collapsed {
  display: grid;
  justify-items: center;
  width: 100%;
}

.sidebar-brand.is-collapsed h2 {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  border: 1px solid var(--accent-border);
  border-radius: 18px;
  background: var(--accent-soft);
  color: var(--brand-blue);
  font-size: 1.12rem;
  letter-spacing: -0.04em;
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
  border: 1px solid var(--border-soft);
  border-radius: 14px;
  background: var(--surface);
  color: var(--brand-navy);
  cursor: pointer;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

.collapse-button:hover {
  transform: translateY(-1px);
  border-color: var(--accent-border);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
}

.collapse-button.is-collapsed {
  width: 42px;
  height: 42px;
  border-color: var(--accent-border);
  background: var(--surface);
  color: var(--brand-blue);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
}

.sidebar-nav {
  display: grid;
  gap: 10px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
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
  border-color: var(--accent-border);
  background: var(--accent-soft);
}

.nav-item.is-active {
  border-color: var(--accent-border);
  background: var(--accent-soft);
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
  background: var(--accent-soft);
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

.logout-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  min-height: 44px;
  padding: 0 16px;
  border: 1px solid var(--border-soft);
  border-radius: 16px;
  background: var(--surface);
  color: var(--brand-navy);
  font: inherit;
  font-weight: 700;
  letter-spacing: -0.01em;
  cursor: pointer;
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.05);
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease,
    box-shadow 0.2s ease,
    color 0.2s ease;
}

.logout-button:hover {
  transform: translateY(-1px);
  border-color: rgba(239, 68, 68, 0.22);
  background: var(--danger-soft);
  color: #dc2626;
  box-shadow: 0 16px 28px rgba(220, 38, 38, 0.1);
}

.logout-button.is-collapsed {
  width: 46px;
  height: 46px;
  min-height: 46px;
  padding: 0;
  border-radius: 18px;
}

.logout-icon {
  font-size: 1rem;
  flex: 0 0 auto;
}

.workspace-content {
  min-width: 0;
  padding: 0 24px 0 0;
}

@media (max-width: 1400px) {
  .workspace-shell {
    padding-left: 220px;
  }

  .workspace-shell.sidebar-collapsed {
    padding-left: 88px;
  }

  .workspace-sidebar {
    width: 220px;
    padding-inline: 14px;
  }

  .workspace-sidebar.is-collapsed {
    width: 88px;
  }

  .workspace-content {
    padding-right: 18px;
  }
}

@media (max-width: 980px) {
  .workspace-shell,
  .workspace-shell.sidebar-collapsed {
    padding-left: 0;
    padding-top: 0;
  }

  .workspace-sidebar {
    position: static;
    width: 100%;
    min-height: auto;
    padding: 18px 16px 0;
    border-right: none;
    border-bottom: 1px solid var(--border-soft);
    background: transparent;
    backdrop-filter: none;
  }

  .workspace-sidebar.is-collapsed {
    width: 100%;
  }

  .sidebar-stack {
    gap: 18px;
  }

  .sidebar-nav,
  .sidebar-nav.is-collapsed {
    grid-template-columns: repeat(auto-fit, minmax(124px, 1fr));
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

  .logout-button {
    width: 100%;
  }
}

</style>
