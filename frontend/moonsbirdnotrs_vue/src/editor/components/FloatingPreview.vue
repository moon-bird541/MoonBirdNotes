<script setup>
import { computed } from 'vue'
import DOMPurify from 'dompurify'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  title: {
    type: String,
    default: '',
  },
  ready: {
    type: Boolean,
    default: false,
  },
  bodyHtml: {
    type: String,
    default: '',
  },
})

const sanitizedBodyHtml = computed(() => {
  if (!props.bodyHtml) {
    return ''
  }

  return DOMPurify.sanitize(props.bodyHtml, {
    USE_PROFILES: {
      html: true,
    },
  })
})
</script>

<template>
  <transition name="preview-float">
    <aside v-show="visible" class="floating-preview">
      <div class="floating-preview-head">
        <div>
          <p>Preview</p>
          <strong>{{ title }}</strong>
        </div>
        <span>{{ ready ? '实时更新' : '加载中' }}</span>
      </div>
      <div
        v-if="sanitizedBodyHtml"
        class="floating-preview-body markdown-body"
        v-html="sanitizedBodyHtml"
      ></div>
      <div v-else class="floating-preview-empty">
        <strong>预览会在编辑时出现</strong>
      </div>
    </aside>
  </transition>
</template>

<style scoped>
.floating-preview {
  position: fixed;
  right: 28px;
  bottom: 28px;
  z-index: 198;
  display: grid;
  gap: 12px;
  width: min(380px, calc(100vw - 32px));
  max-height: min(360px, 48vh);
  padding: 16px;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 22px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.94)),
    rgba(255, 255, 255, 0.94);
  box-shadow:
    0 24px 64px rgba(15, 23, 42, 0.16),
    0 8px 24px rgba(37, 99, 235, 0.08);
  backdrop-filter: blur(18px);
}

.floating-preview-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.floating-preview-head p {
  margin: 0 0 6px;
  color: var(--brand-blue);
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.floating-preview-head strong {
  display: block;
  color: var(--brand-navy);
  font-size: 1rem;
  line-height: 1.35;
}

.floating-preview-head span {
  color: var(--ink-soft);
  font-size: 0.8rem;
  white-space: nowrap;
}

.floating-preview-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.floating-preview-tag {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
  font-size: 0.78rem;
  font-weight: 600;
}

.floating-preview-body {
  min-height: 0;
  overflow: auto;
  padding-right: 4px;
}

.floating-preview-body :deep(*) {
  font-size: 0.92rem;
}

.floating-preview-body :deep(h1),
.floating-preview-body :deep(h2),
.floating-preview-body :deep(h3) {
  margin-top: 0;
}

.floating-preview-body :deep(.floating-preview-inline-tags) {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.floating-preview-body :deep(.floating-preview-inline-tag) {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
  font-size: 0.78rem;
  font-weight: 600;
}

.floating-preview-empty {
  color: var(--ink-soft);
}

.floating-preview-empty strong {
  color: var(--brand-navy);
  font-size: 0.94rem;
}

.preview-float-enter-active,
.preview-float-leave-active {
  transition:
    opacity 0.18s ease,
    transform 0.18s ease;
}

.preview-float-enter-from,
.preview-float-leave-to {
  opacity: 0;
  transform: translateY(10px);
}

@media (max-width: 720px) {
  .floating-preview {
    right: 16px;
    bottom: 16px;
    width: min(340px, calc(100vw - 24px));
  }
}

@media (max-width: 520px) {
  .floating-preview {
    right: 12px;
    bottom: 12px;
    width: calc(100vw - 24px);
    max-height: 42vh;
    padding: 14px;
    border-radius: 18px;
  }
}
</style>
