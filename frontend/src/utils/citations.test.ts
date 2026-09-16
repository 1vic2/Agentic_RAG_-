import { describe, expect, it } from 'vitest'
import { citationParts } from './citations'

describe('citationParts', () => {
  it('only links evidence indices that exist', () => {
    expect(citationParts('根据资料[1]与[3]；[0]无效。', 2)).toEqual([
      { text: '根据资料' }, { text: '[1]', index: 1 },
      { text: '与[3]；[0]无效。' },
    ])
  })

  it('keeps repeated references to the same source', () => {
    expect(citationParts('[2]、[2]', 2)).toEqual([
      { text: '[2]', index: 2 }, { text: '、' }, { text: '[2]', index: 2 },
    ])
  })
})
