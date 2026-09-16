export interface Evidence { id: string; text: string; source: string; score: number; type?: string }
export interface ToolStep { tool: string; state: 'running' | 'done' | 'error'; count?: number; elapsedMs?: number }
export interface Message { role: 'user' | 'assistant'; content: string; evidence?: Evidence[]; steps?: ToolStep[]; time?: number; _evShow?: boolean }
