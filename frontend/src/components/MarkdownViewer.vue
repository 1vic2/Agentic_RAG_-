<template>
  <div class="markdown" v-html="html" @click="handleClick"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { linkCitations } from '../utils/citations'

const props = defineProps<{ content: string; evidenceCount?: number }>()
const emit = defineEmits<{ citation: [index: number] }>()
const html = computed(() => linkCitations(DOMPurify.sanitize(marked(props.content, { breaks: true }) as string), props.evidenceCount || 0))

function handleClick(event: MouseEvent) {
  const target = event.target as HTMLElement
  const button = target.closest<HTMLButtonElement>('button[data-citation]')
  if (button) emit('citation', Number(button.dataset.citation))
}
</script>
