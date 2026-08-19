<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'

const props = defineProps({
  open: Boolean,
  loading: Boolean,
  error: String,
  trace: Object,
  embedded: Boolean,
})

const emit = defineEmits(['close', 'retry', 'open-source'])

const stageLabels = {
  'api.request.received': '收到请求',
  'api.request.validated': '参数校验完成',
  'conversation.resolved': '会话上下文就绪',
  'agent.started': 'Agent 开始编排',
  'retrieval.completed': '混合检索完成',
  'agent.tool.completed': '只读工具完成',
  'agent.llm.completed': '模型调用完成',
  'agent.final.repair_requested': '修复最终 JSON',
  'agent.completed': 'Agent 生成结果',
  'conversation.turn.recorded': '对话记录已保存',
  'conversation.turn.failed': '对话记录失败',
  'conversation.memory.checked': '会话记忆已检查',
  'api.response.ready': '响应已生成',
}

const events = computed(() => props.trace?.events || [])
const retrievalEvent = computed(() =>
  events.value.find((item) => item.stage === 'retrieval.completed'),
)
const statusTone = computed(() => {
  if (!props.trace) return 'neutral'
  return props.trace.http_status < 400 ? 'success' : 'danger'
})

const formatDuration = (value) => {
  const number = Number(value || 0)
  return number >= 1000 ? `${(number / 1000).toFixed(2)} s` : `${number.toFixed(1)} ms`
}

const stageIcon = (stage) => {
  if (stage.includes('retrieval')) return 'ph:magnifying-glass'
  if (stage.includes('tool')) return 'ph:wrench'
  if (stage.includes('llm') || stage.includes('agent')) return 'ph:brain'
  if (stage.includes('conversation')) return 'ph:chats-circle'
  return 'ph:check-circle'
}

const eventSummary = (event) => {
  const data = event.metadata || {}
  if (event.stage === 'retrieval.completed') {
    return `Dense ${data.dense_candidate_count || 0} · 关键词 ${data.keyword_candidate_count || 0}`
  }
  if (event.stage === 'agent.tool.completed') {
    return `${data.tool_name || '工具'} · ${data.result_count || 0} 条结果 · ${formatDuration(data.duration_ms)}`
  }
  if (event.stage === 'agent.llm.completed') {
    return `${data.tool_call_count || 0} 次工具调用 · ${formatDuration(data.duration_ms)}`
  }
  if (event.stage === 'agent.completed') {
    return `${data.source_count || 0} 个来源${data.insufficient_context ? ' · 资料不足' : ''}`
  }
  if (event.stage === 'conversation.memory.checked') {
    return data.compressed ? '已压缩更早上下文' : '无需压缩'
  }
  return ''
}

</script>

<template>
  <Transition name="trace-fade">
      <div v-if="open" class="trace-overlay" :class="{ 'is-embedded': embedded }" @click.self="emit('close')">
        <aside class="trace-panel" :class="{ 'is-embedded': embedded }" role="region" aria-label="RAG 运行轨迹">
          <header class="trace-header">
            <div>
              <p>RUN DIAGNOSTICS</p>
              <h2>RAG 全流程轨迹</h2>
            </div>
            <button v-if="!embedded" type="button" aria-label="关闭运行轨迹" @click="emit('close')">
              <Icon icon="ph:x" />
            </button>
          </header>

          <div v-if="loading" class="trace-state">
            <span class="trace-spinner"></span>
            <p>正在读取运行轨迹…</p>
          </div>

          <div v-else-if="error" class="trace-state is-error">
            <Icon icon="ph:warning-circle" />
            <h3>轨迹暂时不可用</h3>
            <p>{{ error }}</p>
            <button type="button" @click="emit('retry')">重新读取</button>
          </div>

          <template v-else-if="trace">
            <section class="trace-overview">
              <div>
                <span>状态</span>
                <strong :class="`is-${statusTone}`">HTTP {{ trace.http_status }}</strong>
              </div>
              <div>
                <span>总耗时</span>
                <strong>{{ formatDuration(trace.duration_ms) }}</strong>
              </div>
              <div>
                <span>阶段</span>
                <strong>{{ events.length }}</strong>
              </div>
            </section>

            <section v-if="retrievalEvent" class="retrieval-strip">
              <div class="retrieval-status">
                <Icon :icon="retrievalEvent.metadata.semantic_available ? 'ph:check-circle' : 'ph:warning'" />
                <div>
                  <span>检索通道</span>
                  <strong>{{ retrievalEvent.metadata.semantic_available ? '语义 + 关键词' : '已降级为关键词' }}</strong>
                </div>
              </div>
              <p v-if="retrievalEvent.metadata.degradation_code">
                降级码：{{ retrievalEvent.metadata.degradation_code }}
              </p>
            </section>

            <section class="trace-timeline">
              <article
                v-for="(event, index) in events"
                :key="`${event.stage}-${index}`"
                class="trace-event"
                :style="{ '--event-index': index }"
              >
                <div class="event-marker"><Icon :icon="stageIcon(event.stage)" /></div>
                <div class="event-copy">
                  <div class="event-title">
                    <strong>{{ stageLabels[event.stage] || event.stage }}</strong>
                    <time>+{{ formatDuration(event.offset_ms) }}</time>
                  </div>
                  <p v-if="eventSummary(event)">{{ eventSummary(event) }}</p>

                  <div v-if="event.stage === 'retrieval.completed' && event.metadata.candidates?.length" class="candidate-list">
                    <button
                      v-for="(candidate, candidateIndex) in event.metadata.candidates"
                      :key="`${candidate.note_id}-${candidateIndex}`"
                      type="button"
                      @click="emit('open-source', candidate)"
                    >
                      <span>{{ String(candidateIndex + 1).padStart(2, '0') }}</span>
                      <div>
                        <strong>笔记 {{ candidate.note_id }}</strong>
                        <small>{{ candidate.heading_path?.join(' / ') || '整篇笔记' }}</small>
                      </div>
                      <em>{{ Number(candidate.score || 0).toFixed(4) }}</em>
                      <Icon icon="ph:arrow-up-right" />
                    </button>
                  </div>

                  <div
                    v-if="event.stage === 'agent.tool.completed' && event.metadata.result_items?.length"
                    class="candidate-list tool-result-list"
                  >
                    <button
                      v-for="(item, itemIndex) in event.metadata.result_items"
                      :key="`${item.parent_id || item.note_id || itemIndex}-${itemIndex}`"
                      type="button"
                      @click="item.note_id && emit('open-source', item)"
                    >
                      <span>{{ String(itemIndex + 1).padStart(2, '0') }}</span>
                      <div>
                        <strong>{{ item.title || `笔记 ${item.note_id || '未知'}` }}</strong>
                        <small>{{ item.heading_path?.join(' / ') || '整篇笔记' }}</small>
                      </div>
                      <em v-if="item.score != null">{{ Number(item.score).toFixed(4) }}</em>
                      <Icon v-if="item.note_id" icon="ph:arrow-up-right" />
                    </button>
                  </div>
                </div>
              </article>
            </section>

            <footer class="trace-footer">
              <span>RUN ID</span>
              <code>{{ trace.run_id }}</code>
              <p>轨迹仅保留脱敏状态、数量与来源定位，不包含问题和笔记正文。</p>
            </footer>
          </template>
        </aside>
      </div>
  </Transition>
</template>

<style scoped>
.trace-overlay { position: fixed; inset: 0; z-index: 4000; display: flex; justify-content: flex-end; background: rgba(28, 33, 39, .34); backdrop-filter: blur(4px); }
.trace-panel { width: min(560px, 100vw); height: 100%; overflow-y: auto; background: #f8f4eb; box-shadow: -20px 0 60px rgba(24, 31, 39, .18); color: #25354b; }
.trace-overlay.is-embedded { position: static; display: block; height: 100%; background: transparent; backdrop-filter: none; }
.trace-panel.is-embedded { width: 100%; min-height: 100%; height: auto; box-shadow: none; }
.trace-header { position: sticky; top: 0; z-index: 2; display: flex; align-items: center; justify-content: space-between; padding: 28px 30px 22px; border-bottom: 1px solid rgba(45, 57, 73, .12); background: rgba(248, 244, 235, .94); backdrop-filter: blur(18px); }
.trace-header p { margin: 0 0 6px; color: #657763; font-size: .68rem; font-weight: 800; letter-spacing: .18em; }
.trace-header h2 { margin: 0; font: 700 1.65rem/1.2 Georgia, 'Noto Serif SC', serif; }
.trace-header button { display: grid; place-items: center; width: 38px; height: 38px; border: 1px solid rgba(45, 57, 73, .14); border-radius: 50%; background: transparent; color: inherit; cursor: pointer; }
.trace-overview { display: grid; grid-template-columns: repeat(3, 1fr); padding: 24px 30px; border-bottom: 1px solid rgba(45, 57, 73, .1); }
.trace-overview div { display: grid; gap: 7px; padding-left: 18px; border-left: 1px solid rgba(45, 57, 73, .12); }
.trace-overview div:first-child { padding-left: 0; border-left: 0; }
.trace-overview span, .retrieval-status span, .trace-footer span { color: #847d72; font-size: .7rem; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
.trace-overview strong { font-size: 1.05rem; }
.trace-overview .is-success { color: #58715a; }
.trace-overview .is-danger { color: #a24d3f; }
.retrieval-strip { margin: 22px 30px 0; padding: 15px 0; border-block: 1px solid rgba(101, 119, 99, .2); }
.retrieval-status { display: flex; align-items: center; gap: 12px; }
.retrieval-status > svg { color: #657763; font-size: 1.4rem; }
.retrieval-status div { display: grid; gap: 3px; }
.retrieval-strip p { margin: 9px 0 0 36px; color: #a24d3f; font-size: .78rem; }
.trace-timeline { padding: 26px 30px 38px; }
.trace-event { display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 12px; opacity: 0; animation: event-in .32s ease-out forwards; animation-delay: calc(var(--event-index) * 35ms); }
.event-marker { position: relative; display: grid; place-items: center; align-self: start; width: 28px; height: 28px; border: 1px solid rgba(101, 119, 99, .28); border-radius: 50%; background: #f8f4eb; color: #657763; }
.trace-event:not(:last-child) .event-marker::after { position: absolute; top: 28px; left: 13px; width: 1px; height: calc(100% + 14px); background: rgba(101, 119, 99, .2); content: ''; }
.event-copy { min-width: 0; padding: 4px 0 25px; }
.event-title { display: flex; justify-content: space-between; gap: 14px; }
.event-title strong { font-size: .91rem; }
.event-title time { flex: 0 0 auto; color: #847d72; font: .72rem 'Cascadia Code', Consolas, monospace; }
.event-copy > p { margin: 6px 0 0; color: #766f65; font-size: .78rem; }
.candidate-list { margin-top: 13px; border-top: 1px solid rgba(45, 57, 73, .1); }
.candidate-list button { display: grid; grid-template-columns: 25px minmax(0, 1fr) auto auto; align-items: center; gap: 10px; width: 100%; padding: 11px 2px; border: 0; border-bottom: 1px solid rgba(45, 57, 73, .09); background: transparent; color: inherit; text-align: left; cursor: pointer; transition: padding .18s ease, color .18s ease; }
.candidate-list button:hover { padding-left: 8px; color: #657763; }
.candidate-list button > span { color: #a57c32; font: .7rem Georgia, serif; }
.candidate-list button div { display: grid; min-width: 0; gap: 2px; }
.candidate-list small { overflow: hidden; color: #847d72; font-size: .7rem; text-overflow: ellipsis; white-space: nowrap; }
.candidate-list em { color: #657763; font: normal .68rem 'Cascadia Code', Consolas, monospace; }
.trace-footer { margin: 0 30px 30px; padding-top: 20px; border-top: 1px solid rgba(45, 57, 73, .12); }
.trace-footer code { display: block; margin-top: 7px; color: #657763; font-size: .72rem; overflow-wrap: anywhere; }
.trace-footer p { margin: 10px 0 0; color: #847d72; font-size: .72rem; line-height: 1.6; }
.trace-state { display: grid; place-items: center; align-content: center; min-height: 60vh; padding: 40px; color: #766f65; text-align: center; }
.trace-state > svg { margin-bottom: 14px; color: #a24d3f; font-size: 2rem; }
.trace-state h3 { margin: 0; color: #25354b; }
.trace-state p { max-width: 320px; line-height: 1.6; }
.trace-state button { padding: 9px 15px; border: 1px solid rgba(45, 57, 73, .18); border-radius: 999px; background: transparent; color: #25354b; cursor: pointer; }
.trace-spinner { width: 28px; height: 28px; border: 2px solid rgba(101, 119, 99, .2); border-top-color: #657763; border-radius: 50%; animation: spin .7s linear infinite; }
.trace-fade-enter-active, .trace-fade-leave-active { transition: background .22s ease; }
.trace-fade-enter-active .trace-panel, .trace-fade-leave-active .trace-panel { transition: transform .28s cubic-bezier(.22, 1, .36, 1); }
.trace-fade-enter-from, .trace-fade-leave-to { background: transparent; }
.trace-fade-enter-from .trace-panel, .trace-fade-leave-to .trace-panel { transform: translateX(100%); }
@keyframes event-in { from { opacity: 0; transform: translateY(7px); } to { opacity: 1; transform: translateY(0); } }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 560px) { .trace-header, .trace-timeline { padding-inline: 20px; } .trace-overview { grid-template-columns: 1fr; gap: 12px; padding-inline: 20px; } .trace-overview div { padding: 0 0 12px; border-left: 0; border-bottom: 1px solid rgba(45, 57, 73, .1); } .trace-overview div:last-child { padding-bottom: 0; border-bottom: 0; } .retrieval-strip, .trace-footer { margin-inline: 20px; } .event-title { align-items: flex-start; flex-direction: column; gap: 4px; } .candidate-list button { grid-template-columns: 24px minmax(0, 1fr) auto; } .candidate-list em { display: none; } }
@media (prefers-reduced-motion: reduce) { .trace-event { opacity: 1; animation: none; } }
</style>
