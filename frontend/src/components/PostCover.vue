<script setup lang="ts">
import { LockOutlined } from '@ant-design/icons-vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { PostCard } from '@/api/types'

/**
 * A post's cover picture. A closed post gets a lock over it and the level it needs, as on
 * the site. `placeholder` keeps the space even when there is no picture (for the tiles).
 */
const props = defineProps<{ post: PostCard; placeholder?: boolean }>()

const { t } = useI18n()

const shown = computed(() => props.post.cover !== null || props.post.closed || props.placeholder)

const needs = computed(() => {
  const level = props.post.level
  if (!level) {
    return t('post.closedHint')
  }
  return level.price
    ? t('post.needsLevelPriced', { level: level.name, price: level.price.toLocaleString('ru') })
    : t('post.needsLevel', { level: level.name })
})
</script>

<template>
  <div v-if="shown" class="post-cover" :class="{ 'post-cover--closed': post.closed }">
    <img v-if="post.cover" class="post-cover__image" :src="post.cover" alt="" loading="lazy" />
    <div v-if="post.closed" class="post-cover__lock">
      <LockOutlined class="post-cover__icon" />
      <span>{{ needs }}</span>
    </div>
  </div>
</template>

<style scoped>
.post-cover {
  position: relative;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border-radius: 6px;
  background: var(--c-fill, rgba(128, 128, 128, 0.12));
}

.post-cover__image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.post-cover--closed .post-cover__image {
  filter: brightness(0.45);
}

.post-cover__lock {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  color: #fff;
  text-align: center;
}

/* Without a picture behind it the lock sits on the page's own background. */
.post-cover--closed:not(:has(.post-cover__image)) .post-cover__lock {
  color: inherit;
  opacity: 0.75;
}

.post-cover__icon {
  font-size: 28px;
}
</style>
