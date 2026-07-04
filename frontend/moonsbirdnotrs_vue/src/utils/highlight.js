export const getSearchTerms = (keyword = '') => {
  const terms = String(keyword)
    .trim()
    .split(/\s+/)
    .map((term) => term.trim())
    .filter(Boolean)

  return [...new Map(terms.map((term) => [term.toLowerCase(), term])).values()].sort(
    (a, b) => b.length - a.length
  )
}

export const buildHighlightParts = (text = '', keyword = '') => {
  const source = String(text || '')
  const terms = getSearchTerms(keyword)

  if (!source || !terms.length) {
    return [{ text: source, highlight: false }]
  }

  const lowerSource = source.toLowerCase()
  const parts = []
  let cursor = 0

  while (cursor < source.length) {
    let nextMatch = null

    for (const term of terms) {
      const index = lowerSource.indexOf(term.toLowerCase(), cursor)
      if (index === -1) {
        continue
      }

      if (!nextMatch || index < nextMatch.index || (index === nextMatch.index && term.length > nextMatch.term.length)) {
        nextMatch = { index, term }
      }
    }

    if (!nextMatch) {
      parts.push({ text: source.slice(cursor), highlight: false })
      break
    }

    if (nextMatch.index > cursor) {
      parts.push({ text: source.slice(cursor, nextMatch.index), highlight: false })
    }

    const end = nextMatch.index + nextMatch.term.length
    parts.push({ text: source.slice(nextMatch.index, end), highlight: true })
    cursor = end
  }

  return parts
}
