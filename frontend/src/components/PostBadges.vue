<script setup lang="ts">
import { CheckCircleOutlined, LockOutlined, PushpinOutlined } from '@ant-design/icons-vue'
import { Tag } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'

import type { PostCard } from '@/api/types'

/** What a post is, at a glance: who may read it and what has happened to it on the site. */
defineProps<{ post: PostCard }>()

const { t } = useI18n()
</script>

<template>
  <span class="post-badges">
    <Tag v-if="post.pinned" :bordered="false">
      <template #icon><PushpinOutlined /></template>
      {{ t('post.pinned') }}
    </Tag>
    <Tag v-if="post.closed" :bordered="false">
      <template #icon><LockOutlined /></template>
      {{ post.level?.name ?? t('post.closed') }}
    </Tag>
    <Tag v-else :bordered="false">
      <template #icon><CheckCircleOutlined /></template>
      {{ post.level?.name ?? t('post.free') }}
    </Tag>
    <Tag v-if="post.status === 'deleted_on_site'" color="error" :bordered="false">
      {{ t('post.deleted') }}
    </Tag>
    <Tag v-else-if="post.status === 'unavailable'" color="warning" :bordered="false">
      {{ t('post.unavailable') }}
    </Tag>
    <Tag v-if="!post.closed && !post.text_is_full" color="warning" :bordered="false">
      {{ t('post.partial') }}
    </Tag>
  </span>
</template>

<style scoped>
.post-badges {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px 0;
}
</style>
