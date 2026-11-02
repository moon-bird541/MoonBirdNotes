export const TASK_URGENCY_OPTIONS = [
  { value: 1, label: '低', tone: 'low' },
  { value: 2, label: '中', tone: 'medium' },
  { value: 3, label: '高', tone: 'high' },
  { value: 4, label: '紧急', tone: 'urgent' },
]

export const TASK_SORT_OPTIONS = [
  { value: 'urgency', label: '紧急程度优先' },
  { value: 'due', label: '截止时间优先' },
  { value: 'created', label: '最近创建' },
]

export const TASK_SEGMENTS = [
  { value: 'todo', label: '待办', hint: '24 小时内完成' },
  { value: 'project', label: '项目', hint: '跨多天推进' },
]

const pad = (value) => String(value).padStart(2, '0')

export const toLocalInputValue = (value) => {
  if (!value) {
    return ''
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return ''
  }

  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export const fromLocalInputValue = (value) => {
  if (!value) {
    return null
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return null
  }

  return date.toISOString()
}

export const formatTaskTime = (value) => {
  if (!value) {
    return '时间未定'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return '时间未定'
  }

  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export const formatTaskRange = (task) => {
  if (!task?.has_time) {
    return '时间未定'
  }

  return `${formatTaskTime(task.start_at)} → ${formatTaskTime(task.end_at)}`
}

export const resolveUrgencyTone = (urgency) =>
  TASK_URGENCY_OPTIONS.find((item) => item.value === Number(urgency))?.tone || 'low'

export const resolveUrgencyLabel = (task) =>
  task?.urgency_display || TASK_URGENCY_OPTIONS.find((item) => item.value === Number(task?.urgency))?.label || ''

/**
 * 按 segment 把任务拆成「待办 / 项目」两段。
 * 排序已经在后端完成，这里只做分组，不重新排序。
 */
export const groupTasksBySegment = (tasks = []) => {
  const groups = { todo: [], project: [] }

  tasks.forEach((task) => {
    const segment = task.segment === 'todo' ? 'todo' : 'project'
    groups[segment].push(task)
  })

  return groups
}
