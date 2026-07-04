import api from '../services/api'

const getExportFilename = (response, fallback) => {
  const disposition = response.headers?.['content-disposition'] || ''
  const encodedMatch = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (encodedMatch?.[1]) {
    try {
      return decodeURIComponent(encodedMatch[1])
    } catch {
      return fallback
    }
  }

  const quotedMatch = disposition.match(/filename="([^"]+)"/i)
  return quotedMatch?.[1] || fallback
}

const downloadBlob = (blob, filename) => {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

export const getNoteExportErrorDetail = async (error) => {
  const data = error.response?.data

  if (data instanceof Blob) {
    try {
      const text = await data.text()
      const payload = JSON.parse(text)
      return payload.detail
    } catch {
      return ''
    }
  }

  return data?.detail
}

export const exportNoteFile = async (note, format) => {
  const response = await api.get(`/notes/${note.id}/export/`, {
    params: { format },
    responseType: 'blob',
  })
  const fallbackExtension = format === 'html' ? 'html' : 'md'
  const filename = getExportFilename(response, `${note.title || 'note'}.${fallbackExtension}`)
  downloadBlob(response.data, filename)
}

export const exportNoteBatchFile = async (noteIds, format) => {
  const response = await api.post('/notes/batch-export/', {
    note_ids: noteIds,
    format,
  }, {
    responseType: 'blob',
  })
  const filename = getExportFilename(response, `moonbird-notes-${format}.zip`)
  downloadBlob(response.data, filename)
}
