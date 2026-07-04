import axios from 'axios'

const CURRENT_USER_STORAGE_KEY = 'current_user'
const LEGACY_ACCESS_TOKEN_STORAGE_KEY = 'access_token'
const LEGACY_REFRESH_TOKEN_STORAGE_KEY = 'refresh_token'
const CSRF_COOKIE_NAME = 'csrftoken'

const isUnsafeMethod = (method = 'get') => !['get', 'head', 'options', 'trace'].includes(method.toLowerCase())

const getCookieValue = (name) => {
  const escapedName = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = document.cookie.match(new RegExp(`(?:^|; )${escapedName}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : ''
}

const removeLegacyTokenStorage = () => {
  localStorage.removeItem(LEGACY_ACCESS_TOKEN_STORAGE_KEY)
  localStorage.removeItem(LEGACY_REFRESH_TOKEN_STORAGE_KEY)
}

removeLegacyTokenStorage()

const buildClient = () =>
  axios.create({
    baseURL: '/api',
    timeout: 10000,
    withCredentials: true,
  })

const api = buildClient()
const refreshClient = buildClient()

let refreshRequest = null
let sessionRequest = null
let sessionChecked = false

export const getStoredCurrentUser = () => {
  const raw = localStorage.getItem(CURRENT_USER_STORAGE_KEY)

  if (!raw) {
    return null
  }

  try {
    return JSON.parse(raw)
  } catch {
    localStorage.removeItem(CURRENT_USER_STORAGE_KEY)
    return null
  }
}

export const setCurrentUser = (user) => {
  if (user) {
    localStorage.setItem(CURRENT_USER_STORAGE_KEY, JSON.stringify(user))
  } else {
    localStorage.removeItem(CURRENT_USER_STORAGE_KEY)
  }

  sessionChecked = true
  return user
}

export const clearAuthState = () => {
  removeLegacyTokenStorage()
  localStorage.removeItem(CURRENT_USER_STORAGE_KEY)
  sessionChecked = false
}

const redirectToLogin = () => {
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

const attachSecurityHeaders = (config) => {
  const nextConfig = config

  if (isUnsafeMethod(nextConfig.method)) {
    const csrfToken = getCookieValue(CSRF_COOKIE_NAME)

    if (csrfToken) {
      nextConfig.headers = nextConfig.headers || {}
      nextConfig.headers['X-CSRFToken'] = csrfToken
    }
  }

  return nextConfig
}

const refreshAccessToken = async () => {
  if (!refreshRequest) {
    refreshRequest = refreshClient
      .post('/token/refresh/')
      .finally(() => {
        refreshRequest = null
      })
  }

  return refreshRequest
}

export const ensureSession = async (force = false) => {
  if (sessionChecked && !force) {
    return getStoredCurrentUser()
  }

  if (!sessionRequest) {
    sessionRequest = api
      .get('/session/')
      .then((response) => setCurrentUser(response.data?.user || null))
      .catch((error) => {
        localStorage.removeItem(CURRENT_USER_STORAGE_KEY)
        sessionChecked = true
        throw error
      })
      .finally(() => {
        sessionRequest = null
      })
  }

  return sessionRequest
}

api.interceptors.request.use(attachSecurityHeaders)
refreshClient.interceptors.request.use(attachSecurityHeaders)

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !originalRequest.url?.includes('/login/') &&
      !originalRequest.url?.includes('/logout/') &&
      !originalRequest.url?.includes('/token/refresh/')
    ) {
      originalRequest._retry = true

      try {
        await refreshAccessToken()
        return api(originalRequest)
      } catch (refreshError) {
        clearAuthState()
        redirectToLogin()
        return Promise.reject(refreshError)
      }
    }

    if (error.response?.status === 401) {
      clearAuthState()
      redirectToLogin()
    }

    return Promise.reject(error)
  }
)

export default api
