export interface CitationPart { text: string; index?: number }

export function citationParts(text: string, count: number): CitationPart[] {
  const parts: CitationPart[] = []
  const marker = /\[(\d+)\]/g
  let offset = 0
  for (const match of text.matchAll(marker)) {
    const index = Number(match[1])
    if (index < 1 || index > count) continue
    const position = match.index ?? 0
    if (position > offset) parts.push({ text: text.slice(offset, position) })
    parts.push({ text: match[0], index })
    offset = position + match[0].length
  }
  if (offset < text.length) parts.push({ text: text.slice(offset) })
  return parts.length ? parts : [{ text }]
}

/** Operate on already sanitized HTML, replacing only visible plain text nodes. */
export function linkCitations(html: string, count: number): string {
  if (!count) return html
  const container = document.createElement('div')
  container.innerHTML = html
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT)
  const nodes: Text[] = []
  while (walker.nextNode()) nodes.push(walker.currentNode as Text)
  for (const node of nodes) {
    if (node.parentElement?.closest('a, code, pre, button')) continue
    const parts = citationParts(node.data, count)
    if (!parts.some(part => part.index)) continue
    const fragment = document.createDocumentFragment()
    for (const part of parts) {
      if (part.index) {
        const button = document.createElement('button')
        button.type = 'button'
        button.className = 'citation-link'
        button.dataset.citation = String(part.index)
        button.textContent = part.text
        button.setAttribute('aria-label', `查看证据 ${part.index}`)
        fragment.append(button)
      } else fragment.append(document.createTextNode(part.text))
    }
    node.replaceWith(fragment)
  }
  return container.innerHTML
}
