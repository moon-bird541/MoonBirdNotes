import { createRouter, createWebHistory } from 'vue-router'

import HomeView from '../views/HomeView.vue'
import LoginView from '../views/LoginView.vue'
import NoteListView from '../views/NoteListView.vue'
import NoteUploadView from '../views/NoteUploadView.vue'
import TrashNoteListView from '../views/TrashNoteListView.vue'

const routes = [
  {
    path: '/',
    name: 'home',
    component: HomeView,
    meta: { requiresAuth: true },
  },
  {
    path: '/notes',
    name: 'note-list',
    component: NoteListView,
    meta: { requiresAuth: true },
  },
  {
    path: '/notes/upload',
    name: 'note-upload',
    component: NoteUploadView,
    meta: { requiresAuth: true },
  },
  {
    path: '/trash',
    name: 'trash-list',
    component: TrashNoteListView,
    meta: { requiresAuth: true },
  },
  {
    path: '/login',
    name: 'login',
    component: LoginView,
    meta: { guestOnly: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const token = localStorage.getItem('access_token')

  if (to.meta.requiresAuth && !token) {
    return { name: 'login' }
  }

  if (to.meta.guestOnly && token) {
    return { name: 'home' }
  }

  return true
})

export default router
