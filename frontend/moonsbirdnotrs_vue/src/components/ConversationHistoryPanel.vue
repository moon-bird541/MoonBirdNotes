<script setup>
import { Icon } from '@iconify/vue'

defineProps({
  conversations: { type: Array, default: () => [] },
  activeId: { type: String, default: null },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['select', 'create', 'delete'])

const formatTime = (value) => {
  if (!value) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}
</script>

<template>
  <aside class="history-panel" aria-label="历史对话">
    <div class="history-heading">
      <div>
        <p>History</p>
        <h2>历史对话</h2>
      </div>
      <button type="button" aria-label="新对话" @click="emit('create')">
        <Icon icon="ph:plus" />
      </button>
    </div>

    <div class="history-list">
      <p v-if="loading" class="history-empty">正在读取历史…</p>
      <p v-else-if="!conversations.length" class="history-empty">发送第一条问题后，会话会保存在这里。</p>
      <template v-else>
        <div
          v-for="item in conversations"
          :key="item.id"
          class="history-item"
          :class="{ 'is-active': item.id === activeId }"
        >
          <button class="history-open" type="button" @click="emit('select', item.id)">
            <span class="history-copy">
              <strong>{{ item.title }}</strong>
              <small>{{ formatTime(item.updated_at) }} · {{ item.turn_count }} 轮</small>
            </span>
          </button>
          <button
            class="history-delete"
            type="button"
            aria-label="删除对话"
            @click="emit('delete', item.id)"
          >
            <Icon icon="ph:trash" />
          </button>
        </div>
      </template>
    </div>
  </aside>
</template>

<style scoped>
.history-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-width: 0;
  padding: 26px 18px 22px;
  border-right: 1px solid rgba(76, 67, 53, 0.11);
  background: rgba(255, 251, 244, 0.38);
  overflow: hidden;
}

.history-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 4px 18px;
}

.history-heading p {
  margin: 0 0 4px;
  color: var(--moss, #657763);
  font-size: 0.66rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.history-heading h2 {
  margin: 0;
  color: var(--brand-navy, #25354b);
  font-size: 1rem;
}

.history-heading button {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 1px solid rgba(45, 57, 73, 0.15);
  border-radius: 50%;
  background: transparent;
  color: var(--brand-navy, #25354b);
  cursor: pointer;
}

.history-list {
  overflow-y: auto;
  scrollbar-width: thin;
}

.history-empty {
  margin: 18px 5px;
  color: var(--text-muted, #766f65);
  font-size: 0.78rem;
  line-height: 1.6;
}

.history-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 4px 6px 4px 10px;
  border-bottom: 1px solid rgba(76, 67, 53, 0.09);
  background: transparent;
  color: var(--brand-navy, #25354b);
  transition: background 0.18s ease, padding 0.18s ease;
}

.history-item:hover,
.history-item.is-active {
  padding-left: 14px;
  background: rgba(255, 248, 237, 0.78);
}

.history-item.is-active {
  box-shadow: inset 3px 0 var(--brand-gold, #a57c32);
}

.history-open {
  min-width: 0;
  padding: 8px 0;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.history-copy {
  display: grid;
  min-width: 0;
  gap: 5px;
}

.history-copy strong {
  overflow: hidden;
  font-size: 0.82rem;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-copy small {
  color: var(--text-muted, #766f65);
  font-size: 0.68rem;
}

.history-delete {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 0;
  background: transparent;
  color: var(--text-muted, #766f65);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.18s ease, background 0.18s ease;
}

.history-item:hover .history-delete,
.history-item.is-active .history-delete,
.history-delete:focus-visible {
  opacity: 1;
}

.history-delete:hover {
  background: rgba(150, 67, 50, 0.1);
  color: #984b3d;
}

@media (max-width: 900px) {
  .history-panel {
    grid-template-columns: 150px minmax(0, 1fr);
    grid-template-rows: 1fr;
    gap: 12px;
    padding: 12px 16px;
    border-right: 0;
    border-bottom: 1px solid rgba(76, 67, 53, 0.11);
  }

  .history-heading {
    padding: 0;
  }

  .history-list {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    overflow-y: hidden;
  }

  .history-item {
    flex: 0 0 190px;
    border: 1px solid rgba(76, 67, 53, 0.09);
    border-radius: 11px;
  }
}

@media (max-width: 560px) {
  .history-panel {
    grid-template-columns: 1fr;
  }

  .history-heading h2 {
    font-size: 0.9rem;
  }
}
</style>
