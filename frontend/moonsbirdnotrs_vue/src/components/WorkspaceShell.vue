<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import GlobalSearchPanel from './GlobalSearchPanel.vue'
import SettingsPanel from './SettingsPanel.vue'
import api, { clearAuthState } from '../services/api'
import moonbirdMark from '../assets/moonbird-mark.png'

const route = useRoute()
const router = useRouter()

const navigationItems = [
  { label: '首页', routeName: 'home', icon: 'ph:house-line' },
  { label: '知识对话', routeName: 'knowledge-chat', icon: 'ph:chats-circle' },
  { label: 'RAG 链路', routeName: 'rag-traces', icon: 'ph:activity' },
  { label: 'Token 用量', routeName: 'token-usage', icon: 'ph:gauge' },
  { label: '笔记列表', routeName: 'note-list', icon: 'ph:notebook' },
  { label: '日记', routeName: 'diary', activeRouteNames: ['diary', 'diary-edit'], icon: 'ph:calendar-blank' },
  { label: '标签管理', routeName: 'tag-management', icon: 'ph:tag' },
  { label: '图片管理', routeName: 'image-management', icon: 'ph:image-square' },
  { label: '回收站', routeName: 'trash-list', icon: 'ph:trash' },
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
            <p v-if="!sidebarCollapsed || isMobile" class="sidebar-kicker">
              <img class="brand-mark" :src="moonbirdMark" alt="" aria-hidden="true" />
              <span>MoonBirdNotes</span>
            </p>
            <h2>{{ sidebarCollapsed && !isMobile ? 'MB' : '书桌' }}</h2>
          </div>

          <button
            class="collapse-button"
            :class="{ 'is-collapsed': sidebarCollapsed && !isMobile }"
            type="button"
            :aria-label="sidebarCollapsed ? '展开功能栏' : '收起功能栏'"
            @click="toggleSidebar"
          >
            <Icon v-if="sidebarCollapsed" icon="ph:caret-double-right" />
            <Icon v-else icon="ph:caret-double-left" />
          </button>
        </div>

        <nav class="sidebar-nav" :class="{ 'is-collapsed': sidebarCollapsed && !isMobile }">
          <button
            v-for="item in navigationItems"
            :key="item.routeName"
            type="button"
            class="nav-item"
            :class="{ 'is-active': isNavigationActive(item), 'is-collapsed': sidebarCollapsed && !isMobile }"
            :title="sidebarCollapsed && !isMobile ? item.label : undefined"
            @click="goToRoute(item.routeName)"
          >
            <span class="nav-badge">
              <Icon class="nav-icon" :icon="item.icon" />
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
            <Icon class="logout-icon" icon="ph:sign-out" />
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
  padding-left: 274px;
  transition: padding-left 0.24s var(--motion-snappy);
}

.workspace-shell.sidebar-collapsed {
  padding-left: 92px;
}

.workspace-sidebar {
  position: fixed;
  top: 0;
  left: 0;
  box-sizing: border-box;
  width: 274px;
  height: 100vh;
  height: 100svh;
  min-height: 100vh;
  min-height: 100svh;
  padding: 28px 22px 26px;
  border-right: 1px solid rgba(123, 83, 58, 0.12);
  background:
    radial-gradient(circle at 46% 64%, rgba(209, 171, 118, 0.1), transparent 30%),
    linear-gradient(180deg, rgba(255, 250, 241, 0.96), rgba(247, 238, 222, 0.88)),
    var(--surface);
  backdrop-filter: blur(18px) saturate(0.92);
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: rgba(101, 119, 99, 0.35) transparent;
  transition:
    width 0.24s var(--motion-snappy),
    padding 0.24s var(--motion-snappy);
  z-index: 100;
}

.workspace-sidebar::-webkit-scrollbar {
  width: 6px;
}

.workspace-sidebar::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(101, 119, 99, 0.3);
}

.workspace-sidebar::after {
  position: absolute;
  right: -42px;
  bottom: 136px;
  left: -8px;
  height: 470px;
  background: url('../assets/sidebar-landscape.png') left bottom / 390px auto no-repeat;
  content: '';
  opacity: 0.78;
  pointer-events: none;
}

.workspace-sidebar::before {
  display: none;
}

.workspace-sidebar.is-collapsed {
  width: 92px;
}

.sidebar-stack {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 28px;
  position: relative;
  z-index: 1;
  min-height: calc(100svh - 54px);
}

.sidebar-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
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
  border-radius: 12px;
  background: var(--accent-soft);
  color: var(--brand-blue);
  font-size: 1.12rem;
  letter-spacing: 0;
}

.sidebar-kicker {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 24px;
  color: var(--brand-blue);
  font-size: 0.82rem;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.brand-mark {
  display: block;
  width: 28px;
  height: 32px;
  object-fit: contain;
}

.sidebar-brand h2 {
  margin: 0;
  color: var(--brand-navy);
  font-size: 2rem;
  font-weight: 850;
  letter-spacing: 0;
}

.collapse-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  background: rgba(255, 250, 241, 0.76);
  color: var(--brand-navy);
  cursor: pointer;
  transition:
    transform 0.2s var(--motion-snappy),
    box-shadow 0.2s var(--motion-calm),
    border-color 0.2s var(--motion-calm),
    background 0.2s var(--motion-calm);
}

.collapse-button:hover {
  transform: translateY(-1px);
  border-color: var(--accent-border);
  background: var(--accent-soft);
  box-shadow: 0 10px 24px rgba(42, 33, 23, 0.08);
}

.collapse-button.is-collapsed {
  width: 42px;
  height: 42px;
  border-color: var(--accent-border);
  background: var(--surface);
  color: var(--brand-blue);
  box-shadow: 0 10px 24px rgba(42, 33, 23, 0.06);
}

.sidebar-nav {
  display: grid;
  gap: 14px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 13px;
  min-width: 0;
  min-height: 54px;
  padding: 14px 22px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  color: #425645;
  text-align: left;
  cursor: pointer;
  transition:
    transform 0.2s var(--motion-snappy),
    border-color 0.2s var(--motion-calm),
    background 0.2s var(--motion-calm),
    color 0.2s var(--motion-calm);
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
  border-color: rgba(171, 91, 58, 0.18);
  background: linear-gradient(180deg, rgba(255, 246, 237, 0.95), rgba(249, 232, 216, 0.86));
  color: var(--brand-blue);
  font-weight: 700;
  box-shadow: 0 10px 22px rgba(117, 79, 52, 0.06);
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
  width: 22px;
  height: 22px;
  border-radius: 0;
  background: transparent;
  color: currentColor;
  font-size: 0.85rem;
  font-weight: 700;
  flex: 0 0 auto;
}

.nav-icon,
.logout-icon,
.collapse-button :deep(svg) {
  width: 1.12rem;
  height: 1.12rem;
}

.sidebar-footer {
  display: grid;
  gap: 10px;
  margin-top: auto;
  padding-top: 4px;
}

.sidebar-footer.is-collapsed {
  justify-items: center;
}

.sidebar-footer p {
  display: none;
  margin: 0;
  color: var(--ink-soft);
}

.logout-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  min-height: 58px;
  padding: 0 18px;
  border: 1px solid rgba(123, 83, 58, 0.13);
  border-radius: 12px;
  background: rgba(255, 250, 241, 0.76);
  color: #2f3430;
  font: inherit;
  font-weight: 700;
  letter-spacing: -0.01em;
  cursor: pointer;
  box-shadow: 0 10px 22px rgba(117, 79, 52, 0.04);
  transition:
    transform 0.2s var(--motion-snappy),
    border-color 0.2s var(--motion-calm),
    background 0.2s var(--motion-calm),
    box-shadow 0.2s var(--motion-calm),
    color 0.2s var(--motion-calm);
}

.logout-button:hover {
  transform: translateY(-1px);
  border-color: rgba(158, 47, 34, 0.22);
  background: var(--danger-soft);
  color: var(--danger);
  box-shadow: 0 16px 28px rgba(158, 47, 34, 0.1);
}

.logout-button.is-collapsed {
  width: 46px;
  height: 46px;
  min-height: 46px;
  padding: 0;
  border-radius: 12px;
}

.workspace-content {
  min-width: 0;
  padding: 0;
}

@media (max-width: 1400px) {
  .workspace-shell {
    padding-left: 246px;
  }

  .workspace-shell.sidebar-collapsed {
    padding-left: 86px;
  }

  .workspace-sidebar {
    width: 246px;
    padding-inline: 18px;
  }

  .workspace-sidebar.is-collapsed {
    width: 86px;
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
    height: auto;
    min-height: auto;
    padding: 18px 16px 0;
    border-right: none;
    border-bottom: 1px solid var(--border-soft);
    background: transparent;
    backdrop-filter: none;
    overflow: visible;
  }

  .sidebar-stack {
    min-height: auto;
  }

  .workspace-sidebar::after,
  .workspace-sidebar::before {
    display: none;
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
    display: flex;
    gap: 8px;
    margin-inline: -12px;
    padding: 0 12px 4px;
    overflow-x: auto;
    scroll-snap-type: x proximity;
    scrollbar-width: none;
  }

  .sidebar-nav::-webkit-scrollbar {
    display: none;
  }

  .nav-item,
  .nav-item.is-collapsed {
    flex: 0 0 auto;
    min-height: 44px;
    padding: 10px 13px;
    justify-content: center;
    scroll-snap-align: start;
    text-align: center;
  }

  .sidebar-footer,
  .sidebar-footer.is-collapsed {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    align-items: stretch;
    justify-items: stretch;
  }

  .logout-button {
    width: 100%;
    min-height: 48px;
    padding-inline: 10px;
    font-size: 0.82rem;
  }
}

/* 高倍缩放会显著降低可用高度，压缩桌面侧栏间距并保留所有入口。 */
@media (max-height: 760px) and (min-width: 981px) {
  .workspace-sidebar {
    padding-block: 18px;
  }

  .sidebar-stack {
    gap: 16px;
  }

  .nav-item {
    min-height: 44px;
    padding-block: 10px;
  }

  .logout-button {
    min-height: 48px;
  }
}

@media (max-width: 420px) {
  .sidebar-brand h2 {
    font-size: 1.35rem;
  }

  .sidebar-footer,
  .sidebar-footer.is-collapsed {
    grid-template-columns: 1fr;
  }
}

</style>
