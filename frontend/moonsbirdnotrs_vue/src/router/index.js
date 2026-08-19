import { createRouter, createWebHistory } from 'vue-router'
import { ensureSession } from '../services/api'

const routes = [
  {
    path: '/',
    name: 'home',
    component: () => import('../views/HomeView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/notes',
    name: 'note-list',
    component: () => import('../views/NoteListView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/knowledge-chat',
    name: 'knowledge-chat',
    component: () => import('../views/KnowledgeChatView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/rag-traces',
    name: 'rag-traces',
    component: () => import('../views/RagTraceView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/token-usage',
    name: 'token-usage',
    component: () => import('../views/TokenUsageView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/notes/upload',
    name: 'note-upload',
    component: () => import('../views/NoteUploadView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/diary/:date?',
    name: 'diary',
    component: () => import('../views/DiaryView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/diary/:date/edit',
    name: 'diary-edit',
    component: () => import('../views/DiaryEditView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/tags',
    name: 'tag-management',
    component: () => import('../views/TagManagementView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/images',
    name: 'image-management',
    component: () => import('../views/ImageManagementView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/notes/:id/edit',
    name: 'note-edit',
    component: () => import('../views/NoteEditView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/notes/:id',
    name: 'note-detail',
    component: () => import('../views/NoteDetailView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/trash',
    name: 'trash-list',
    component: () => import('../views/TrashNoteListView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
    meta: { guestOnly: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  if (!to.meta.requiresAuth && !to.meta.guestOnly) {
    return true
  }

  try {
    const currentUser = await ensureSession()

    if (to.meta.requiresAuth) {
      return currentUser ? true : { name: 'login' }
    }

    if (to.meta.guestOnly && currentUser) {
      return { name: 'home' }
    }
  } catch {
    if (to.meta.requiresAuth) {
      return { name: 'login' }
    }

    return true
  }

  return true
})

export default router
