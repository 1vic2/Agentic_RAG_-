import { describe, expect, it } from 'vitest'
import { createSSEParser, type SSEEvent } from './sseParser'


describe('createSSEParser', () => {
  it('keeps an event split across chunks', () => {
    const events: SSEEvent[] = []
    const parser = createSSEParser(event => events.push(event))
    parser.push('event: token\ndata: {"tok')
    parser.push('en":"你好"}\n\n')
    expect(events).toEqual([{ event: 'token', data: '{"token":"你好"}' }])
  })

  it('parses CRLF and multiple events in one chunk', () => {
    const events: SSEEvent[] = []
    const parser = createSSEParser(event => events.push(event))
    parser.push('event: status\r\ndata: {"status":"检索中"}\r\n\r\nevent: token\r\ndata: {"token":"答"}\r\n\r\n')
    expect(events).toEqual([
      { event: 'status', data: '{"status":"检索中"}' },
      { event: 'token', data: '{"token":"答"}' },
    ])
  })

  it('preserves UTF-8 characters split between network chunks', () => {
    const events: SSEEvent[] = []
    const parser = createSSEParser(event => events.push(event))
    const bytes = new TextEncoder().encode('event: token\ndata: {"token":"你好"}\n\n')
    const splitAt = bytes.indexOf(0xe4) + 1
    const decoder = new TextDecoder()
    parser.push(decoder.decode(bytes.slice(0, splitAt), { stream: true }))
    parser.push(decoder.decode(bytes.slice(splitAt), { stream: true }))
    parser.push(decoder.decode())
    expect(events).toEqual([{ event: 'token', data: '{"token":"你好"}' }])
  })

  it('joins multi-line data and flushes a final event without a blank line', () => {
    const events: SSEEvent[] = []
    const parser = createSSEParser(event => events.push(event))
    parser.push('event: note\ndata: first\ndata: second')
    parser.finish()
    expect(events).toEqual([{ event: 'note', data: 'first\nsecond' }])
  })

  it('ignores comments and dispatches message events without an event field', () => {
    const events: SSEEvent[] = []
    const parser = createSSEParser(event => events.push(event))
    parser.push(': keep-alive\ndata: hello\n\n')
    expect(events).toEqual([{ event: 'message', data: 'hello' }])
  })
})
