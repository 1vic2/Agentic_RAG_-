export interface SSEEvent {
  event: string
  data: string
}

export interface SSEParser {
  push(chunk: string): void
  finish(): void
}

export function createSSEParser(onEvent: (event: SSEEvent) => void): SSEParser {
  let buffer = ''

  function dispatch(block: string) {
    if (!block) return
    let event = 'message'
    const data: string[] = []
    for (const rawLine of block.split(/\r?\n/)) {
      const line = rawLine.replace(/^\uFEFF/, '')
      if (!line || line.startsWith(':')) continue
      const separator = line.indexOf(':')
      const field = separator >= 0 ? line.slice(0, separator) : line
      let value = separator >= 0 ? line.slice(separator + 1) : ''
      if (value.startsWith(' ')) value = value.slice(1)
      if (field === 'event') event = value || 'message'
      if (field === 'data') data.push(value)
    }
    if (data.length) onEvent({ event, data: data.join('\n') })
  }

  return {
    push(chunk: string) {
      buffer += chunk
      while (true) {
        const boundary = /\r?\n\r?\n/.exec(buffer)
        if (!boundary || boundary.index === undefined) break
        dispatch(buffer.slice(0, boundary.index))
        buffer = buffer.slice(boundary.index + boundary[0].length)
      }
    },
    finish() {
      dispatch(buffer.replace(/\r?\n$/, ''))
      buffer = ''
    },
  }
}
