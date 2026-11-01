import { defineConfig } from 'vitest/config'

// 单元测试只覆盖纯逻辑与可在 jsdom 里断言的渲染结果；
// 需要真实后端/编辑器的场景仍然交给 e2e/*.spec.js（Playwright）。
export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['src/**/__tests__/**/*.test.js'],
    globals: false,
    restoreMocks: true,
  },
})
