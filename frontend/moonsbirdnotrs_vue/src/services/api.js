import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

let refreshRequest = null

const clearAuthState = () => {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('current_user')
}

const redirectToLogin = () => {
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

const refreshAccessToken = async () => {
  const refreshToken = localStorage.getItem('refresh_token')

  if (!refreshToken) {
    throw new Error('NO_REFRESH_TOKEN')
  }

  if (!refreshRequest) {
    refreshRequest = axios
      .post('/api/token/refresh/', {
        refresh: refreshToken,
      })
      .then((response) => {
        const nextAccessToken = response.data?.access

        if (!nextAccessToken) {
          throw new Error('INVALID_REFRESH_RESPONSE')
        }

        localStorage.setItem('access_token', nextAccessToken)
        return nextAccessToken
      })
      .finally(() => {
        refreshRequest = null
      })
  }

  return refreshRequest
}

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')

  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }

  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !originalRequest.url?.includes('/login/') &&
      !originalRequest.url?.includes('/token/refresh/')
    ) {
      originalRequest._retry = true

      try {
        const nextAccessToken = await refreshAccessToken()
        originalRequest.headers = originalRequest.headers || {}
        originalRequest.headers.Authorization = `Bearer ${nextAccessToken}`
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
