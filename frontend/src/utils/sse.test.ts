import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import type { ChatSession } from '../stores/chat'
import { useSSE } from './sse'


function session(id: string): ChatSession {
  return { id, serverId: `server-${id}`, title: 'test', messages: [], createdAt: 0 }
}

function streamResponse(events: string): Response {
  return new Response(events, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

describe('useSSE', () => {
  beforeEach(() => {
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      queueMicrotask(() => callback(0))
      return 1
    })
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
  })

  afterEach(() => vi.unstubAllGlobals())

  it('sends and stores the backend ID on the originating session', async () => {
    const origin = session('a')
    const fetchMock = vi.fn().mockResolvedValue(streamResponse(
      'event: start\ndata: {"conversation_id":"backend-a"}\n\n' +
      'event: token\ndata: {"token":"answer"}\n\n' +
      'event: done\ndata: {"conversation_id":"backend-a","answer":"answer","evidence":[]}\n\n',
    ))
    vi.stubGlobal('fetch', fetchMock)
    const streaming = ref(false)
    const answer = ref('')
    const { send } = useSSE('/query', streaming, answer)

    await send(origin, 'question')

    const request = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(request.conversation_id).toBe('server-a')
    expect(request.retry_retrieval).toBe(false)
    expect(origin.serverId).toBe('backend-a')
    expect(origin.messages.map(message => message.content)).toEqual(['question', 'answer'])
    expect(streaming.value).toBe(false)
  })

  it('sends an explicit opt-in retrieval retry flag', async () => {
    const origin = session('a')
    const fetchMock = vi.fn().mockResolvedValue(streamResponse(
      'event: done\ndata: {"conversation_id":"server-a","answer":"done","evidence":[]}\n\n',
    ))
    vi.stubGlobal('fetch', fetchMock)
    await useSSE('/query', ref(false), ref('')).send(origin, '它多久轮换？', false, false, 'demo', true)
    const request = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(request.retry_retrieval).toBe(true)
    expect(request.kb_id).toBe('demo')
    expect(request.use_web).toBe(false)
  })

  it('turns an incomplete stream into a visible assistant error', async () => {
    const origin = session('a')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse(
      'event: start\ndata: {"conversation_id":"backend-a"}\n\n',
    )))
    const { send } = useSSE('/query', ref(false), ref(''))

    await send(origin, 'question')

    expect(origin.messages[origin.messages.length - 1]?.role).toBe('assistant')
    expect(origin.messages[origin.messages.length - 1]?.content).toContain('连接提前结束')
  })

  it('reports HTTP failures and allows another request afterwards', async () => {
    const origin = session('a')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: '后端不可用' }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      }))
      .mockResolvedValueOnce(streamResponse(
        'event: done\ndata: {"conversation_id":"server-a","answer":"recovered","evidence":[]}\n\n',
      ))
    vi.stubGlobal('fetch', fetchMock)
    const { send } = useSSE('/query', ref(false), ref(''))

    await send(origin, 'first')
    await send(origin, 'second')

    expect(origin.messages.some(message => message.content.includes('后端不可用'))).toBe(true)
    expect(origin.messages[origin.messages.length - 1]?.content).toBe('recovered')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('cancels the active request and leaves the session reusable', async () => {
    const origin = session('a')
    const fetchMock = vi.fn().mockImplementation((_url, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
    }))
    vi.stubGlobal('fetch', fetchMock)
    const streaming = ref(false)
    const { send, cancel } = useSSE('/query', streaming, ref(''))

    const pending = send(origin, 'question')
    await Promise.resolve()
    cancel()
    await pending

    expect(origin.messages[origin.messages.length - 1]?.content).toBe('已停止生成')
    expect(streaming.value).toBe(false)
  })

  it('stores tool progress only when the event belongs to the originating conversation', async () => {
    const origin = session('a')
    const savedSteps: string[] = []
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse(
      'event: start\ndata: {"conversation_id":"server-a"}\n\n' +
      'event: tool_start\ndata: {"conversation_id":"other","tool":"web"}\n\n' +
      'event: tool_start\ndata: {"conversation_id":"server-a","tool":"vector"}\n\n' +
      'event: tool_end\ndata: {"conversation_id":"server-a","tool":"vector","ok":true,"count":2,"elapsed_ms":25}\n\n' +
      'event: done\ndata: {"conversation_id":"server-a","answer":"done","evidence":[]}\n\n',
    )))
    await useSSE('/query', ref(false), ref(''), undefined, () => {
      savedSteps.push(JSON.stringify(origin.activeSteps))
    }).send(origin, 'question')
    expect(origin.messages[origin.messages.length - 1]?.steps).toEqual([
      { tool: 'vector', state: 'done', count: 2, elapsedMs: 25 },
    ])
    expect(origin.activeSteps).toEqual([])
    expect(savedSteps[savedSteps.length - 1]).toBe('[]')
  })
})
