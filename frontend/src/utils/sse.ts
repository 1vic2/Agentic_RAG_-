import type { Ref } from 'vue'
import type { ChatSession } from '../stores/chat'
import type { Evidence } from '../types/research'
import type { ToolStep } from '../types/research'
import { createSSEParser } from './sseParser'


export function useSSE(
  url: string,
  streaming: Ref<boolean>,
  ans: Ref<string>,
  onFirstMsg?: (session: ChatSession, question: string) => void,
  onChanged?: () => void,
) {
  let activeController: AbortController | null = null
  let tokenBuffer = ''
  let frame: number | null = null

  function flushTokens() {
    if (frame !== null) {
      cancelAnimationFrame(frame)
      frame = null
    }
    if (tokenBuffer) {
      ans.value += tokenBuffer
      tokenBuffer = ''
    }
  }

  function pushToken(token: string) {
    tokenBuffer += token
    if (frame === null) frame = requestAnimationFrame(flushTokens)
  }

  function cancel() {
    activeController?.abort()
  }

  async function send(
    session: ChatSession,
    question: string,
    useWeb = true,
    deepMode = false,
    kbId = '',
    retryRetrieval = false,
  ) {
    if (activeController) return
    const wasEmpty = session.messages.length === 0
    session.activeSteps = []
    session.messages.push({ role: 'user', content: question, time: Date.now() })
    if (wasEmpty) onFirstMsg?.(session, question)
    onChanged?.()

    tokenBuffer = ''
    flushTokens()
    ans.value = ''
    streaming.value = true
    const controller = new AbortController()
    activeController = controller
    let streamingStarted = false
    let doneReceived = false
    let eventError = ''

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          question,
          conversation_id: session.serverId || session.id,
          use_web: useWeb,
          deep_mode: deepMode,
          kb_id: kbId,
          retry_retrieval: retryRetrieval,
        }),
      })
      if (!response.ok) {
        let detail = `HTTP ${response.status}`
        try {
          const body = await response.json()
          detail = body.detail || detail
        } catch { /* response was not JSON */ }
        throw new Error(detail)
      }
      if (!response.body) throw new Error('服务器未返回数据流')

      const parser = createSSEParser(({ event, data }) => {
        let payload: any
        try {
          payload = JSON.parse(data)
        } catch {
          eventError = '服务器返回了无法解析的流数据'
          return
        }
        if (event === 'start') {
          session.serverId = payload.conversation_id
          onChanged?.()
        } else if (event === 'status') {
          if (!streamingStarted) ans.value = payload.status || ''
        } else if (event === 'token') {
          if (!streamingStarted) {
            streamingStarted = true
            ans.value = ''
          }
          pushToken(payload.token || '')
        } else if (event === 'tool_start' || event === 'tool_end') {
          if (payload.conversation_id !== session.serverId) return
          const steps = session.activeSteps || (session.activeSteps = [])
          if (event === 'tool_start') {
            steps.push({ tool: payload.tool, state: 'running' })
          } else {
            const running = [...steps].reverse().find(step => step.tool === payload.tool && step.state === 'running')
            const result: ToolStep = { tool: payload.tool, state: payload.ok ? 'done' : 'error', count: payload.count || 0, elapsedMs: payload.elapsed_ms || 0 }
            if (running) Object.assign(running, result)
            else steps.push(result)
          }
          onChanged?.()
        } else if (event === 'error') {
          eventError = payload.error || '生成失败'
        } else if (event === 'done') {
          flushTokens()
          doneReceived = true
          session.serverId = payload.conversation_id || session.serverId
          session.messages.push({
            role: 'assistant',
            content: payload.answer || ans.value,
            evidence: (payload.evidence || []) as Evidence[],
            steps: [...(session.activeSteps || [])],
            time: Date.now(),
          })
          ans.value = ''
          onChanged?.()
        }
      })

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          parser.push(decoder.decode(value, { stream: true }))
        }
        parser.push(decoder.decode())
        parser.finish()
      } finally {
        reader.releaseLock()
      }
      if (eventError) throw new Error(eventError)
      if (!doneReceived) throw new Error('连接提前结束，未收到完整回答')
    } catch (error) {
      flushTokens()
      if (!doneReceived) {
        const stopped = error instanceof DOMException && error.name === 'AbortError'
        const detail = error instanceof Error ? error.message : String(error)
        const suffix = stopped ? '已停止生成' : `请求失败：${detail}`
        const partial = streamingStarted && ans.value ? `${ans.value}\n\n${suffix}` : suffix
        session.messages.push({ role: 'assistant', content: partial, steps: [...(session.activeSteps || [])], time: Date.now() })
        onChanged?.()
      }
      ans.value = ''
    } finally {
      if (activeController === controller) activeController = null
      session.activeSteps = []
      onChanged?.()
      streaming.value = false
    }
  }

  return { send, cancel }
}
