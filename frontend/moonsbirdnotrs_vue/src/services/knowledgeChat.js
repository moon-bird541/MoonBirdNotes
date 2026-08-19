import api from './api'

const MAX_HISTORY_MESSAGES = 12

export const buildCurrentConversationHistory = (conversation) =>
  conversation
    .filter((item) => ['user', 'assistant'].includes(item.role) && item.content?.trim())
    .slice(-MAX_HISTORY_MESSAGES)
    .map((item) => ({
      role: item.role,
      content: item.content.trim(),
    }))

export const sendKnowledgeChatMessage = (message, conversation, conversationId = null) => {
  const history = buildCurrentConversationHistory(conversation)
  const payload = { message }

  if (conversationId) {
    // 持久化会话由服务端读取可信历史，避免浏览器重复提交或篡改上下文。
    payload.conversation_id = conversationId
  } else if (history.length) {
    payload.history = history
  }

  return api.post('/agent/knowledge/chat/', payload, { timeout: 95000 })
}

export const fetchKnowledgeConversations = () =>
  api.get('/agent/knowledge/conversations/')

export const fetchKnowledgeConversation = (conversationId) =>
  api.get(`/agent/knowledge/conversations/${conversationId}/`)

export const deleteKnowledgeConversation = (conversationId) =>
  api.delete(`/agent/knowledge/conversations/${conversationId}/`)

// 运行轨迹只包含脱敏诊断元数据，正文仍由对话接口单独管理。
export const fetchKnowledgeRunTrace = (runId) =>
  api.get(`/agent/knowledge/runs/${runId}/trace/`)

export const fetchKnowledgeRuns = () =>
  api.get('/agent/knowledge/runs/')

export const fetchKnowledgeTokenUsage = (params = {}) =>
  api.get('/agent/knowledge/token-usage/', { params })
