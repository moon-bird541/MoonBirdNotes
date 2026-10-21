<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import ConversationHistoryPanel from '../components/ConversationHistoryPanel.vue'
import {
  deleteKnowledgeConversation,
  fetchKnowledgeConversation,
  fetchKnowledgeConversations,
  sendKnowledgeChatMessage,
} from '../services/knowledgeChat'
import { renderAgentAnswer } from '../utils/renderAgentAnswer'

const router = useRouter()
const message = ref('')
const sending = ref(false)
const errorMessage = ref('')
const conversation = ref([])
const conversationId = ref(null)
const savedConversations = ref([])
const historyLoading = ref(false)
const messageStream = ref(null)

const suggestions = [
  '最近的项目笔记里有哪些待处理事项？',
  '帮我总结 Skill Manager 的安装流程。',
  '指定日期的日记记录了什么？',
]

const canSend = computed(() => message.value.trim() && !sending.value)
const hasConversation = computed(() => conversation.value.length > 0)

const scrollToLatest = async () => {
  await nextTick()
  messageStream.value?.scrollTo({
    top: messageStream.value.scrollHeight,
    behavior: 'smooth',
  })
}

const getErrorText = (error) => {
  const code = error.response?.data?.error?.code

  if (code === 'throttled') {
    return '请求有些频繁，请稍后再试。'
  }

  if (code === 'agent_timeout' || code === 'llm_transport_error') {
    return '知识检索暂时超时，请稍后重试。'
  }

  return '暂时无法完成这次对话，请稍后再试。'
}

const loadConversationList = async () => {
  historyLoading.value = true
  try {
    const response = await fetchKnowledgeConversations()
    savedConversations.value = response.data.results || []
  } catch {
    errorMessage.value = '暂时无法读取历史对话。'
  } finally {
    historyLoading.value = false
  }
}

const openConversation = async (id) => {
  if (sending.value || id === conversationId.value) return
  historyLoading.value = true
  errorMessage.value = ''
  try {
    const response = await fetchKnowledgeConversation(id)
    conversationId.value = response.data.id
    conversation.value = response.data.turns.flatMap((turn) => {
      const messages = [{ role: 'user', content: turn.question }]
      if (turn.status === 'completed') {
        messages.push({
          role: 'assistant',
          content: turn.answer,
          sources: turn.sources || [],
          insufficientContext: Boolean(turn.insufficient_context),
          runId: turn.run_id,
          totalTokens: turn.llm_usage?.total_tokens ?? null,
        })
      } else {
        messages.push({
          role: 'assistant',
          content: '本轮请求未完成，可以重新发送问题。',
          sources: [],
          insufficientContext: true,
          runId: turn.run_id,
        })
      }
      return messages
    })
    await scrollToLatest()
  } catch {
    errorMessage.value = '无法打开这条历史对话。'
  } finally {
    historyLoading.value = false
  }
}

const removeConversation = async (id) => {
  if (sending.value || !window.confirm('确定删除这条历史对话吗？')) return
  try {
    await deleteKnowledgeConversation(id)
    if (conversationId.value === id) {
      clearConversation()
    }
    await loadConversationList()
  } catch {
    errorMessage.value = '删除历史对话失败。'
  }
}

const sendMessage = async (preset) => {
  const content = (preset ?? message.value).trim()
  if (!content || sending.value) {
    return
  }

  // 发送前截取历史，当前问题由 message 字段单独传递，避免重复进入上下文。
  const currentHistory = [...conversation.value]
  conversation.value.push({ role: 'user', content })
  message.value = ''
  errorMessage.value = ''
  sending.value = true
  await scrollToLatest()

  try {
    const response = await sendKnowledgeChatMessage(
      content,
      currentHistory,
      conversationId.value,
    )
    conversationId.value = response.data.conversation_id
    conversation.value.push({
      role: 'assistant',
      content: response.data.answer,
      sources: response.data.sources || [],
      insufficientContext: Boolean(response.data.insufficient_context),
      runId: response.data.run_id,
      totalTokens: response.data.llm_usage?.total_tokens ?? null,
    })
    await loadConversationList()
  } catch (error) {
    if (error.response?.data?.conversation_id) {
      conversationId.value = error.response.data.conversation_id
      await loadConversationList()
    }
    errorMessage.value = getErrorText(error)
  } finally {
    sending.value = false
    await scrollToLatest()
  }
}

const handleComposerKeydown = (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}

const openSource = (source) => {
  if (source.type === 'diary' && source.diary_date) {
    router.push({ name: 'diary', params: { date: source.diary_date } })
    return
  }

  router.push({ name: 'note-detail', params: { id: source.note_id } })
}

const handleAnswerClick = async (event) => {
  const button = event.target.closest('.agent-code-copy')
  if (!button) return
  const code = button.closest('.agent-code-block')?.querySelector('code')?.textContent
  if (!code) return
  try {
    await navigator.clipboard.writeText(code)
    button.textContent = '已复制'
    window.setTimeout(() => {
      button.textContent = '复制代码'
    }, 1600)
  } catch {
    button.textContent = '复制失败'
  }
}

const clearConversation = () => {
  conversationId.value = null
  conversation.value = []
  errorMessage.value = ''
}

onMounted(loadConversationList)
</script>

<template>
  <WorkspaceShell>
    <main class="knowledge-chat-page">
      <header class="chat-header">
        <div>
          <p class="eyebrow">Knowledge Agent</p>
          <h1>与笔记对话</h1>
          <p class="header-note">回答只依据已向量化的笔记与日记，并附上可核对的来源。</p>
        </div>
        <button v-if="hasConversation" class="clear-button" type="button" @click="clearConversation">
          <Icon icon="ph:plus" />
          新对话
        </button>
      </header>

      <div class="chat-body">
        <ConversationHistoryPanel
          :conversations="savedConversations"
          :active-id="conversationId"
          :loading="historyLoading"
          @select="openConversation"
          @create="clearConversation"
          @delete="removeConversation"
        />
        <section ref="messageStream" class="message-stream" aria-live="polite">
        <div v-if="!hasConversation" class="empty-state">
          <span class="empty-mark"><Icon icon="ph:moon-stars" /></span>
          <h2>从你的知识库里找答案</h2>
          <p>可以询问项目细节、日记内容、接口规范或跨章节总结。</p>
          <div class="suggestion-list">
            <button
              v-for="suggestion in suggestions"
              :key="suggestion"
              type="button"
              @click="sendMessage(suggestion)"
            >
              <span>{{ suggestion }}</span>
              <Icon icon="ph:arrow-up-right" />
            </button>
          </div>
        </div>

        <article
          v-for="(item, index) in conversation"
          :key="`${item.role}-${index}`"
          class="message-row"
          :class="`is-${item.role}`"
        >
          <div class="message-identity">
            <Icon :icon="item.role === 'assistant' ? 'ph:bird' : 'ph:user-circle'" />
            <span>{{ item.role === 'assistant' ? 'MoonBird' : '你' }}</span>
          </div>
          <div class="message-body">
            <div
              v-if="item.role === 'assistant'"
              class="message-copy answer-markdown"
              v-html="renderAgentAnswer(item.content)"
              @click="handleAnswerClick"
            ></div>
            <p v-else class="message-copy">{{ item.content }}</p>
            <p v-if="item.insufficientContext" class="insufficient-note">
              <Icon icon="ph:info" />
              当前知识库没有足够资料支持更具体的回答。
            </p>
            <p v-if="item.role === 'assistant' && item.totalTokens != null" class="token-usage">
              本次使用 {{ Number(item.totalTokens).toLocaleString() }} tokens
            </p>
            <div v-if="item.sources?.length" class="source-list">
              <p>引用来源</p>
              <button
                v-for="source in item.sources"
                :key="`${source.note_id}-${source.source_hash}-${source.heading_path?.join('/')}`"
                type="button"
                @click="openSource(source)"
              >
                <span class="source-index">{{ String(source.note_id).padStart(2, '0') }}</span>
                <span class="source-copy">
                  <strong>{{ source.title }}</strong>
                  <small>{{ source.heading_path?.join(' / ') || '整篇笔记' }}</small>
                </span>
                <Icon icon="ph:arrow-up-right" />
              </button>
            </div>
          </div>
        </article>

        <article v-if="sending" class="message-row is-assistant is-loading">
          <div class="message-identity">
            <Icon icon="ph:bird" />
            <span>MoonBird</span>
          </div>
          <div class="thinking-line">
            <span></span><span></span><span></span>
            <p>正在检索笔记并核对来源</p>
          </div>
        </article>
        </section>
      </div>

      <footer class="composer-wrap">
        <p v-if="errorMessage" class="error-message">
          <Icon icon="ph:warning-circle" />
          {{ errorMessage }}
        </p>
        <div class="composer">
          <textarea
            v-model="message"
            rows="1"
            maxlength="4000"
            placeholder="询问你的笔记，Enter 发送，Shift + Enter 换行"
            aria-label="输入知识库问题"
            @keydown="handleComposerKeydown"
          ></textarea>
          <button type="button" :disabled="!canSend" aria-label="发送问题" @click="sendMessage()">
            <Icon icon="ph:arrow-up" />
          </button>
        </div>
        <p class="composer-note">当前会话隔离 · 最近 6 轮完整上下文 · 更早内容自动摘要</p>
      </footer>
    </main>
  </WorkspaceShell>
</template>

<style scoped>
.knowledge-chat-page {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  height: 100vh;
  height: 100svh;
  overflow: hidden;
  background:
    linear-gradient(90deg, transparent 0, transparent 68%, rgba(101, 119, 99, 0.045) 68%, rgba(101, 119, 99, 0.045) 68.15%, transparent 68.15%),
    var(--page-bg, #f7f2e8);
}

.chat-body {
  display: grid;
  grid-template-columns: 238px minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
}

.chat-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 32px;
  padding: 34px clamp(28px, 5vw, 76px) 24px;
  border-bottom: 1px solid rgba(76, 67, 53, 0.12);
  animation: header-in 0.45s ease-out both;
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--moss, #657763);
  font-size: 0.74rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.chat-header h1 {
  margin: 0;
  color: var(--brand-navy, #25354b);
  font-family: Georgia, 'Noto Serif SC', serif;
  font-size: clamp(2rem, 3.5vw, 3.25rem);
  font-weight: 700;
  letter-spacing: -0.04em;
}

.header-note {
  margin: 10px 0 0;
  color: var(--text-muted, #766f65);
  font-size: 0.92rem;
}

.clear-button,
.suggestion-list button,
.source-list button,
.composer button {
  font: inherit;
}

.clear-button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 15px;
  border: 1px solid rgba(45, 57, 73, 0.18);
  border-radius: 999px;
  background: transparent;
  color: var(--brand-navy, #25354b);
  cursor: pointer;
  transition: background 0.18s ease, transform 0.18s ease;
}

.clear-button:hover {
  background: var(--control-hover-background);
  transform: translateY(-1px);
}

.message-stream {
  overflow-y: auto;
  padding: 34px clamp(28px, 7vw, 112px) 48px;
  scroll-behavior: smooth;
}

.empty-state {
  width: min(760px, 100%);
  margin: clamp(42px, 9vh, 112px) auto 0;
  animation: empty-in 0.55s ease-out both;
}

.empty-mark {
  display: grid;
  place-items: center;
  width: 54px;
  height: 54px;
  margin-bottom: 26px;
  border: 1px solid rgba(101, 119, 99, 0.28);
  border-radius: 50%;
  color: var(--moss, #657763);
  font-size: 1.45rem;
}

.empty-state h2 {
  margin: 0;
  color: var(--brand-navy, #25354b);
  font-family: Georgia, 'Noto Serif SC', serif;
  font-size: clamp(1.65rem, 3vw, 2.5rem);
}

.empty-state > p {
  margin: 12px 0 34px;
  color: var(--text-muted, #766f65);
}

.suggestion-list {
  border-top: 1px solid rgba(76, 67, 53, 0.13);
}

.suggestion-list button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 18px 2px;
  border: 0;
  border-bottom: 1px solid rgba(76, 67, 53, 0.13);
  background: transparent;
  color: var(--brand-navy, #25354b);
  text-align: left;
  cursor: pointer;
  transition: color 0.18s ease, padding 0.18s ease;
}

.suggestion-list button:hover {
  padding-left: 10px;
  color: var(--moss, #657763);
}

.message-row {
  display: grid;
  width: min(1040px, 100%);
  margin: 0 auto 18px;
  padding: 8px 0;
  animation: message-in 0.32s ease-out both;
}

.message-row.is-user {
  grid-template-areas: 'body identity';
  grid-template-columns: minmax(220px, 620px) 88px;
  justify-content: end;
  gap: 16px;
  color: var(--brand-navy, #25354b);
}

.message-row.is-assistant {
  grid-template-areas: 'identity body';
  grid-template-columns: 96px minmax(260px, 760px);
  justify-content: start;
  gap: 18px;
}

.message-identity {
  grid-area: identity;
  display: flex;
  align-items: center;
  align-self: start;
  gap: 8px;
  padding-top: 3px;
  color: var(--text-muted, #766f65);
  font-size: 0.78rem;
  font-weight: 750;
}

.is-user .message-identity {
  justify-content: flex-end;
  padding-top: 14px;
}

.is-assistant .message-identity {
  padding-top: 14px;
}

.message-identity svg {
  font-size: 1.1rem;
}

.message-body {
  grid-area: body;
  min-width: 0;
  padding: 18px 22px;
  border: 1px solid rgba(76, 67, 53, 0.1);
  border-radius: 20px 20px 20px 6px;
  background: var(--panel-background-soft);
  box-shadow: 0 8px 24px rgba(70, 58, 42, 0.045);
}

.is-user .message-body {
  justify-self: end;
  width: fit-content;
  max-width: 100%;
  border-color: rgba(155, 82, 49, 0.14);
  border-radius: 20px 20px 6px 20px;
  background: var(--control-selected-background);
  box-shadow: 0 8px 24px rgba(131, 72, 43, 0.055);
}

.is-assistant .message-body {
  width: min(780px, 100%);
  padding: 10px 0 24px;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.message-copy {
  margin: 0;
  color: var(--brand-navy, #25354b);
  font-size: 1rem;
  line-height: 1.85;
}

.is-assistant .message-copy {
  font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif;
  font-size: 0.98rem;
  line-height: 1.78;
}

.is-user .message-copy {
  line-height: 1.7;
  white-space: pre-wrap;
}

.token-usage {
  margin: 10px 0 0;
  color: var(--text-muted, #766f65);
  font-size: 0.72rem;
  letter-spacing: 0.01em;
}

.answer-markdown :deep(> :first-child) {
  margin-top: 0;
}

.answer-markdown :deep(> :last-child) {
  margin-bottom: 0;
}

.answer-markdown :deep(p) {
  margin: 0 0 16px;
  color: var(--text-secondary);
}

.answer-markdown :deep(h1),
.answer-markdown :deep(h2),
.answer-markdown :deep(h3),
.answer-markdown :deep(h4) {
  color: var(--text-primary);
  font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif;
  font-weight: 720;
  line-height: 1.35;
  letter-spacing: -0.015em;
}

.answer-markdown :deep(h1) {
  margin: 4px 0 18px;
  font-size: 1.42rem;
}

.answer-markdown :deep(h2) {
  margin: 30px 0 13px;
  padding: 0;
  border: 0;
  font-size: 1.2rem;
}

.answer-markdown :deep(h3) {
  margin: 26px 0 12px;
  padding: 0;
  font-size: 1.08rem;
}

.answer-markdown :deep(h4) {
  margin: 19px 0 10px;
  font-size: 0.98rem;
}

.answer-markdown :deep(strong) {
  color: var(--text-secondary);
  font-weight: 760;
}

/* 模型常用整行粗体表示接口章节，将其呈现为真正的阅读层级。 */
.answer-markdown :deep(p:has(> strong:only-child)) {
  margin: 26px 0 12px;
  padding: 0;
  color: var(--text-primary);
  font-size: 1.08rem;
  line-height: 1.4;
}

.answer-markdown :deep(hr) {
  display: none;
}

.answer-markdown :deep(ul),
.answer-markdown :deep(ol) {
  margin: 8px 0 18px;
  padding-left: 1.45rem;
  color: var(--text-secondary);
}

.answer-markdown :deep(li) {
  padding-left: 0.18rem;
  line-height: 1.68;
}

.answer-markdown :deep(li)::marker {
  color: var(--text-muted);
}

.answer-markdown :deep(li + li) {
  margin-top: 5px;
}

.answer-markdown :deep(li > p) {
  margin: 0;
}

.answer-markdown :deep(code) {
  padding: 0.16em 0.42em;
  border: 1px solid rgba(143, 73, 48, 0.14);
  border-radius: 6px;
  background: rgba(143, 73, 48, 0.065);
  color: var(--accent);
  font-family: 'Cascadia Code', 'SFMono-Regular', Consolas, monospace;
  font-size: 0.88em;
  overflow-wrap: anywhere;
}

.answer-markdown :deep(.agent-code-block) {
  margin: 16px 0 22px;
  overflow: hidden;
  border: 1px solid rgba(76, 67, 53, 0.14);
  border-radius: 12px;
  background: var(--panel-background-raised);
  box-shadow: 0 3px 12px rgba(70, 58, 42, 0.045);
}

.answer-markdown :deep(.agent-code-toolbar) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 38px;
  padding: 0 14px;
  border-bottom: 1px solid var(--border-soft);
  background: var(--panel-background-raised);
  color: var(--text-muted);
  font: 600 0.68rem/1 'Cascadia Code', Consolas, monospace;
}

.answer-markdown :deep(.agent-code-copy) {
  padding: 6px 0;
  border: 0;
  background: transparent;
  color: var(--moss);
  font: inherit;
  cursor: pointer;
}

.answer-markdown :deep(.agent-code-copy:hover) {
  color: var(--text-primary);
}

.answer-markdown :deep(pre) {
  max-width: 100%;
  margin: 0;
  padding: 16px 18px 18px;
  border: 0;
  border-radius: 0;
  background: var(--panel-background-raised);
  box-shadow: none;
  color: var(--text-secondary);
  overflow-x: auto;
  scrollbar-width: thin;
}

.answer-markdown :deep(pre code) {
  display: block;
  min-width: max-content;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.82rem;
  line-height: 1.62;
  overflow-wrap: normal;
  white-space: pre;
}

.answer-markdown :deep(blockquote) {
  margin: 18px 0;
  padding: 10px 14px;
  border-left: 3px solid rgba(165, 124, 50, 0.58);
  background: rgba(165, 124, 50, 0.055);
  color: var(--text-muted, #766f65);
}

.answer-markdown :deep(a) {
  color: var(--moss, #657763);
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
}

.answer-markdown :deep(table) {
  width: 100%;
  margin: 16px 0 20px;
  border-collapse: collapse;
  font-size: 0.88rem;
}

.answer-markdown :deep(th),
.answer-markdown :deep(td) {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(76, 67, 53, 0.12);
  text-align: left;
  vertical-align: top;
}

.answer-markdown :deep(th) {
  background: rgba(101, 119, 99, 0.07);
  color: var(--text-primary);
  font-weight: 750;
}

.insufficient-note,
.error-message {
  display: flex;
  align-items: center;
  gap: 8px;
}

.insufficient-note {
  margin: 18px 0 0;
  color: var(--accent);
  font-size: 0.84rem;
}

.source-list {
  margin-top: 24px;
  border-top: 1px solid rgba(76, 67, 53, 0.13);
}

.source-list > p {
  margin: 18px 0 8px;
  color: var(--text-muted, #766f65);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.source-list button {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 13px 0;
  border: 0;
  border-bottom: 1px solid rgba(76, 67, 53, 0.1);
  background: transparent;
  color: var(--brand-navy, #25354b);
  text-align: left;
  cursor: pointer;
  transition: color 0.18s ease, transform 0.18s ease;
}

.source-list button:hover {
  color: var(--moss, #657763);
  transform: translateX(4px);
}


.source-index {
  color: var(--brand-gold, #a57c32);
  font-family: Georgia, serif;
  font-size: 0.8rem;
}

.source-copy {
  display: grid;
  gap: 3px;
}

.source-copy strong {
  font-size: 0.9rem;
}

.source-copy small {
  overflow: hidden;
  color: var(--text-muted, #766f65);
  font-size: 0.76rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thinking-line {
  grid-area: body;
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  width: fit-content;
  padding: 16px 20px;
  border: 1px solid rgba(76, 67, 53, 0.09);
  border-radius: 20px 20px 20px 6px;
  background: var(--panel-background-soft);
}

.thinking-line span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--moss, #657763);
  animation: thinking 1s ease-in-out infinite;
}

.thinking-line span:nth-child(2) { animation-delay: 0.12s; }
.thinking-line span:nth-child(3) { animation-delay: 0.24s; }

.thinking-line p {
  margin: 0 0 0 8px;
  color: var(--text-muted, #766f65);
  font-size: 0.85rem;
}

.composer-wrap {
  padding: 14px clamp(28px, 7vw, 112px) 22px;
  border-top: 1px solid var(--border-soft);
  background: color-mix(in srgb, var(--overlay-background) 94%, transparent);
  backdrop-filter: blur(16px);
}

.composer {
  display: flex;
  align-items: flex-end;
  gap: 14px;
  width: min(900px, 100%);
  margin: 0 auto;
  padding: 12px 12px 12px 18px;
  border: 1px solid var(--border-soft);
  border-radius: 18px;
  background: var(--control-background);
  box-shadow: var(--shadow-soft);
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

.composer:focus-within {
  border-color: rgba(101, 119, 99, 0.52);
  box-shadow: 0 14px 38px rgba(70, 58, 42, 0.12);
}

.composer textarea {
  flex: 1;
  min-height: 28px;
  max-height: 140px;
  padding: 5px 0;
  border: 0;
  outline: 0;
  resize: vertical;
  background: transparent;
  color: var(--brand-navy, #25354b);
  font: inherit;
  line-height: 1.55;
}

.composer textarea::placeholder {
  color: var(--text-muted);
}

.composer button {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  width: 42px;
  height: 42px;
  border: 0;
  border-radius: 50%;
  background: var(--brand-navy, #25354b);
  color: var(--text-on-accent);
  cursor: pointer;
  transition: transform 0.18s ease, opacity 0.18s ease;
}

.composer button:hover:not(:disabled) {
  transform: translateY(-2px);
}

.composer button:disabled {
  cursor: not-allowed;
  opacity: 0.35;
}

.composer-note {
  margin: 8px auto 0;
  width: min(900px, 100%);
  color: var(--text-muted, #766f65);
  font-size: 0.7rem;
  text-align: center;
}

.error-message {
  width: min(900px, 100%);
  margin: 0 auto 10px;
  color: var(--danger);
  font-size: 0.82rem;
}

@keyframes header-in {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes empty-in {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes message-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes thinking {
  0%, 100% { opacity: 0.3; transform: translateY(0); }
  50% { opacity: 1; transform: translateY(-3px); }
}

@media (max-width: 760px) {
  .chat-header {
    align-items: flex-start;
    padding: 24px 20px 18px;
  }

  .header-note {
    max-width: 260px;
  }

  .clear-button {
    padding: 9px;
  }

  .clear-button svg + * {
    display: none;
  }

  .message-stream {
    padding: 22px 20px 34px;
  }

  .empty-state {
    margin-top: 34px;
  }

  .message-row {
    width: 100%;
    margin-bottom: 12px;
    padding: 4px 0;
  }

  .message-row.is-assistant {
    grid-template-areas:
      'identity'
      'body';
    grid-template-columns: minmax(0, 1fr);
    gap: 8px;
  }

  .message-row.is-user {
    grid-template-areas:
      'identity'
      'body';
    grid-template-columns: minmax(0, 1fr);
    justify-items: end;
    gap: 8px;
  }

  .message-identity,
  .is-user .message-identity,
  .is-assistant .message-identity {
    padding-top: 0;
  }

  .message-body {
    max-width: min(88%, 620px);
    padding: 15px 17px;
  }

  .is-assistant .message-body {
    justify-self: start;
    max-width: 94%;
  }

  .thinking-line {
    justify-self: start;
  }

  .composer-wrap {
    padding: 12px 16px 16px;
  }
}

@media (max-width: 900px) {
  .chat-body {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(0, 1fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
