import { reactive } from 'vue'
import type { Message, ToolStep } from '../types/research'

export interface ChatSession {
  id: string
  serverId?: string
  title: string
  messages: Message[]
  activeSteps?: ToolStep[]
  createdAt: number
}

function loadSessions(): ChatSession[] {
  try { return JSON.parse(localStorage.getItem('chat_sessions') || '[]') } catch { return [] }
}

function saveSessions(ss: ChatSession[]) {
  localStorage.setItem('chat_sessions', JSON.stringify(ss))
}

const sessions = reactive<ChatSession[]>(loadSessions())
let curId = localStorage.getItem('chat_cur_id') || ''

function curSession() { return sessions.find(s => s.id === curId) }

export const chatState = reactive({
  sessions,
  curId,
  get messages(): Message[] { const c = curSession(); return c?.messages || [] },
  setCurId(id: string) { curId = id; this.curId = id; localStorage.setItem('chat_cur_id', id) },
  newSession() {
    const id = `${Date.now().toString(36)}-${crypto.randomUUID().slice(0, 8)}`
    const s: ChatSession = { id, serverId: id, title: '新对话', messages: [], createdAt: Date.now() }
    sessions.unshift(s)
    this.setCurId(s.id)
    saveSessions([...sessions])
    return s
  },
  save() {
    saveSessions([...sessions])
  },
  delSession(id: string) {
    const i = sessions.findIndex(s => s.id === id)
    if (i >= 0) sessions.splice(i, 1)
    if (curId === id) {
      if (sessions.length) this.setCurId(sessions[0].id)
      else { curId = ''; this.curId = ''; localStorage.removeItem('chat_cur_id') }
    }
    saveSessions([...sessions])
  }
})

if (!sessions.length) chatState.newSession()
else if (!curSession()) chatState.setCurId(sessions[0].id)
