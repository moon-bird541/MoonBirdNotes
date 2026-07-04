import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return undefined
          }

          if (id.includes('prosemirror-')) {
            return 'prosemirror-vendor'
          }

          if (id.includes('@toast-ui/toastmark')) {
            return 'toastmark-vendor'
          }

          if (id.includes('@toast-ui/editor')) {
            return 'toastui-editor'
          }

          if (id.includes('element-plus') || id.includes('@element-plus/icons-vue')) {
            return 'element-vendor'
          }

          if (id.includes('/vue/') || id.includes('vue-router')) {
            return 'vue-vendor'
          }

          return 'vendor'
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
