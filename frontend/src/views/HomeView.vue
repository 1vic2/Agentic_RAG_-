<template>
  <div class="content" style="padding:0;max-width:100%;flex-direction:row;gap:0">
    <div style="width:200px;min-width:200px;display:flex;flex-direction:column;border-right:1px solid var(--border);padding:12px 8px;gap:2px">
      <button @click="switchChat(chatState.newSession().id)" class="sidebar-btn" style="font-size:12px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;padding:6px 10px">＋ 新对话</button>
      <div style="flex:1;min-height:0;overflow-y:auto;display:flex;flex-direction:column;gap:2px">
        <div v-if="!chatState.sessions.length" class="empty-panel" style="padding:16px 0">暂无对话</div>
        <div v-for="s in chatState.sessions" :key="s.id" class="chat-session-row" style="display:flex;align-items:center">
          <button @click="switchChat(s.id)" class="sidebar-btn" :class="{active:s.id===chatState.curId}" style="font-size:12px;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:6px 10px;flex:1;min-width:0" :title="s.title">{{s.title}}</button>
          <button @click="delSession(s.id)" class="del-btn" style="padding:2px 6px;color:var(--text-3);font-size:10px;font-family:var(--mono);transition:color.12s">✕</button>
        </div>
      </div>
    </div>
    <div style="flex:1;display:flex;flex-direction:column;min-width:0;padding:0 16px">
    <!-- 知识库选择器 -->
    <div style="padding:10px 0;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px">
      <span style="font-size:12px;color:var(--text-3);font-family:var(--mono)">知识库:</span>
      <select v-model="curKbId" class="kb-select" aria-label="选择知识库">
        <option value="">全部知识库</option>
        <option v-for="kb in kbList" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
      </select>
      <button @click="loadKBList" style="font-size:11px;color:var(--text-3);background:none;border:none;cursor:pointer;font-family:var(--mono)">刷新</button>
    </div>
    <div ref="scroller" class="chat-scroll">
      <div v-if="!messages.length && !ans" class="empty-state">
        <div class="empty-icon">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--cyan)" stroke-width="1.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
        </div>
        <p style="font-size:18px;font-weight:600">AgenticRAG</p>
        <p style="font-size:13px;max-width:400px;text-align:center;line-height:1.6;color:var(--text-3)">向量检索 + 知识图谱 + LLM 综合生成<br/>为每段回答提供可溯源证据</p>
      </div>
      <div class="chat-inner">
        <div v-for="(m, i) in messages" :key="i" class="msg" :class="{ 'msg-group': i > 0 && messages[i-1].role === m.role }">
          <div class="msg-avatar" :class="m.role">
            <svg v-if="m.role==='assistant'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
            <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
          </div>
          <div class="msg-body">
            <div v-if="m.steps?.length" class="tool-timeline" aria-label="检索工具执行过程">
              <span v-for="(step, stepIndex) in m.steps" :key="stepIndex" class="tool-step" :class="step.state">
                {{ toolLabel(step.tool) }} · {{ step.state === 'running' ? '执行中' : step.state === 'error' ? '失败' : `完成 ${step.count ?? 0} 条` }}<small v-if="step.elapsedMs !== undefined"> {{ step.elapsedMs }}ms</small>
              </span>
            </div>
            <div class="msg-text"><MarkdownViewer :content="m.content" :evidence-count="m.evidence?.length || 0" @citation="index => showCitation(m, i, index)" /><span v-if="m.time" class="msg-time">{{new Date(m.time).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})}}</span></div>
            <div v-if="m.evidence?.length" class="evidence-panel">
              <div class="evidence-header" @click="m._evShow = !m._evShow">
                <svg :style="{ transform: m._evShow ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform .2s cubic-bezier(.25,.46,.45,.94)' }" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 18l6-6-6-6"/></svg>
                <span>{{ m.evidence.length }} 条检索证据</span>
              </div>
              <transition name="ev-slide">
                <div v-if="m._evShow" class="evidence-list">
                  <div v-for="(e, evidenceIndex) in m.evidence" :key="e.id" :id="`evidence-${chatState.curId}-${i}-${evidenceIndex + 1}`" class="evidence-item">
                  <div class="evidence-source"><strong>[{{ evidenceIndex + 1 }}]</strong> {{ e.source }} <span class="evidence-score">{{ (e.score*100).toFixed(0) }}% 匹配</span></div>
                  <div class="evidence-text">{{ e.text }}</div>
                </div>
              </div>
              </transition>
            </div>
          </div>
        </div>
        <div v-if="streaming" class="msg">
          <div class="msg-avatar assistant">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
          </div>
          <div class="msg-body">
            <div v-if="chatState.sessions.find(s => s.id === chatState.curId)?.activeSteps?.length" class="tool-timeline" aria-live="polite">
              <span v-for="(step, stepIndex) in chatState.sessions.find(s => s.id === chatState.curId)?.activeSteps" :key="stepIndex" class="tool-step" :class="step.state">
                {{ toolLabel(step.tool) }} · {{ step.state === 'running' ? '执行中' : step.state === 'error' ? '失败' : `完成 ${step.count ?? 0} 条` }}<small v-if="step.elapsedMs !== undefined"> {{ step.elapsedMs }}ms</small>
              </span>
            </div>
            <div class="msg-text">{{ ans }}<span class="cursor-blink">▍</span></div>
          </div>
        </div>
      </div>
    </div>
    <div class="chat-input-bar">
      <div class="chat-input-inner">
        <textarea v-model="input" class="query-input" placeholder="输入研究问题…" rows="1" :disabled="streaming" @keydown.enter.prevent="submit" />
        <button @click="deepMode=!deepMode" :title="deepMode?'ReAct 深度模式':'快速模式'" aria-label="切换 ReAct 深度模式" style="padding:2px 8px;border-radius:2px;font-size:10px;font-weight:600;font-family:var(--mono);flex-shrink:0;transition:all .12s;text-transform:uppercase;letter-spacing:.5px" :style="deepMode?{background:'rgba(0,188,212,.1)',color:'#00bcd4',border:'1px solid rgba(0,188,212,.2)'}:{background:'rgba(255,255,255,.03)',color:'var(--text-3)',border:'1px solid var(--border)'}">{{deepMode?'🧠 ReAct':'⚡ 快速'}}</button>
        <button @click="useWeb=!useWeb" :title="useWeb?'联网已开':'联网已关'" style="padding:2px 8px;border-radius:2px;font-size:10px;font-weight:600;font-family:var(--mono);flex-shrink:0;transition:all .12s;text-transform:uppercase;letter-spacing:.5px" :style="useWeb?{background:'rgba(0,188,212,.1)',color:'#00bcd4',border:'1px solid rgba(0,188,212,.2)'}:{background:'rgba(255,255,255,.03)',color:'var(--text-3)',border:'1px solid var(--border)'}">{{useWeb?'🌐 联网':'🌐 断网'}}</button>
        <button @click="retryRetrieval=!retryRetrieval" :title="retryRetrieval?'指代追问二次检索已开':'指代追问二次检索已关'" style="padding:2px 8px;border-radius:2px;font-size:10px;font-weight:600;font-family:var(--mono);flex-shrink:0;transition:all .12s;white-space:nowrap" :style="retryRetrieval?{background:'rgba(0,188,212,.1)',color:'#00bcd4',border:'1px solid rgba(0,188,212,.2)'}:{background:'rgba(255,255,255,.03)',color:'var(--text-3)',border:'1px solid var(--border)'}">{{retryRetrieval?'🔁 补检索':'🔁 单检索'}}</button>
        <button v-if="streaming" class="query-submit" @click="cancel">
          <span>停止</span>
        </button>
        <button v-else class="query-submit" :disabled="!input.trim()" @click="submit">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
          <span>发送</span>
        </button>
      </div>
    </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, watch, onMounted } from 'vue'
import MarkdownViewer from '../components/MarkdownViewer.vue'
import { useSSE } from '../utils/sse'
import { chatState } from '../stores/chat'
import { getKBList, clearKBCache } from '../utils/kb'
import type { Message } from '../types/research'

const messages = ref<Message[]>(chatState.messages)
watch(() => chatState.curId, () => { messages.value = chatState.messages })
const streaming = ref(false)
const ans = ref('')
const input = ref('')
const scroller = ref<HTMLDivElement>()

// 知识库选择
const kbList = ref<any[]>([])
const curKbId = ref('')
const toolNames: Record<string, string> = { vector: '向量', vector_retry: '追问补检索', graph: '图谱', web: '联网' }
function toolLabel(tool: string) { return toolNames[tool] || tool }

async function showCitation(message: Message, messageIndex: number, evidenceIndex: number) {
  if (!message.evidence?.[evidenceIndex - 1]) return
  message._evShow = true
  await nextTick()
  const card = document.getElementById(`evidence-${chatState.curId}-${messageIndex}-${evidenceIndex}`)
  card?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  card?.classList.add('citation-target')
  if (card) window.setTimeout(() => card.classList.remove('citation-target'), 1800)
}

async function loadKBList() {
  clearKBCache()
  kbList.value = await getKBList()
}

onMounted(() => {
  loadKBList()
})

function submit() {
  const q = input.value.trim()
  const session = chatState.sessions.find(s => s.id === chatState.curId)
  if (q && session && !streaming.value) { send(session, q, useWeb.value, deepMode.value, curKbId.value, retryRetrieval.value); input.value = '' }
}

function switchChat(id: string) { if (streaming.value) cancel(); chatState.setCurId(id) }
function delSession(id: string) { if (id === chatState.curId && streaming.value) cancel(); chatState.delSession(id) }

const { send, cancel } = useSSE('/api/query/stream', streaming, ans, (session, q) => {
  session.title = q.slice(0, 30)
}, () => chatState.save())
const useWeb = ref(false), deepMode = ref(false), retryRetrieval = ref(false)

watch(messages, () => {
  chatState.save()
}, { deep: true })

watch(ans, () => {
  nextTick(() => scroller.value?.scrollTo({ top: scroller.value.scrollHeight, behavior: 'smooth' }))
})
</script>
