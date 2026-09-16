/** 知识库列表缓存，跨页面共享 */
let _cache: any[] | null = null

export async function getKBList(): Promise<any[]> {
  if (_cache) return _cache
  const r = await (await fetch('/api/knowledge-bases')).json()
  const knowledgeBases: any[] = r.knowledge_bases || []
  _cache = knowledgeBases
  return knowledgeBases
}

export function clearKBCache() { _cache = null }
