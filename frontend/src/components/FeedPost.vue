<script setup lang="ts">
import {
  ClockCircleOutlined,
  LockOutlined,
  PaperClipOutlined,
  SoundOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons-vue'
import { Button, Tag } from 'ant-design-vue'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import type { FeedView, PostCard } from '@/api/types'
import { useFormat } from '@/composables/format'
import { audioPlacedInText } from '@/post/content'

import MediaAudio from './MediaAudio.vue'
import PostBadges from './PostBadges.vue'
import PostBody from './PostBody.vue'
import PostCover from './PostCover.vue'

/** How many audio players a post shows in the stream; a post with more keeps them for its own page. */
const AUDIO_IN_STREAM = 3

/** One post in a project's feed, laid out in one of the four ways the feed can be shown. */
const props = defineProps<{ post: PostCard; view: FeedView }>()

const { t } = useI18n()
const { duration, postDate } = useFormat()

const to = computed(() => ({ name: 'post', params: { id: props.post.id } }))

const length = computed(() => {
  const { duration_text, duration_audio, duration_video } = props.post
  const seconds = (duration_text ?? 0) + (duration_audio ?? 0) + (duration_video ?? 0)
  return seconds > 0 ? duration(seconds) : ''
})

/** Audio that has no place of its own in the text: the stream shows its players under the text. */
const looseAudio = computed(() => {
  const placed = audioPlacedInText(props.post.html, props.post.media)
  return props.post.media.filter((item) => item.kind === 'audio' && !placed.has(item.id))
})

const attachments = computed(() => props.post.media.filter((item) => item.kind === 'attach').length)

// The stream shows the beginning of a text; «Развернуть» opens the rest in place.
const expanded = ref(false)
const overflowing = ref(false)
const text = ref<HTMLElement | null>(null)

function measure(): void {
  const element = text.value
  if (element && !expanded.value) {
    overflowing.value = element.scrollHeight > element.clientHeight + 1
  }
}

onMounted(measure)
watch(
  () => [props.post.html, props.view],
  () => void nextTick(measure),
)
</script>

<template>
  <!-- Список: one line per post. -->
  <RouterLink v-if="view === 'list'" :to="to" class="feed-row">
    <span class="feed-row__thumb">
      <img v-if="post.cover" :src="post.cover" alt="" loading="lazy" />
    </span>
    <span class="feed-row__title">{{ post.title }}</span>
    <span class="feed-row__icons">
      <LockOutlined v-if="post.closed" :title="t('post.closed')" />
      <SoundOutlined v-if="post.has_audio" :title="t('post.hasAudio')" />
      <VideoCameraOutlined v-if="post.has_video" :title="t('post.hasVideo')" />
    </span>
    <span class="feed-row__date">{{ postDate(post.date) }}</span>
  </RouterLink>

  <article v-else class="feed-post" :class="`feed-post--${view}`">
    <header class="feed-post__head">
      <span>{{ postDate(post.date) }}</span>
      <span class="feed-post__length">
        <SoundOutlined v-if="post.has_audio" :title="t('post.hasAudio')" />
        <VideoCameraOutlined v-if="post.has_video" :title="t('post.hasVideo')" />
        <template v-if="length"><ClockCircleOutlined /> {{ length }}</template>
      </span>
    </header>

    <PostCover v-if="view === 'tile'" :post="post" placeholder />

    <h2 class="feed-post__title">
      <RouterLink :to="to">{{ post.title }}</RouterLink>
    </h2>

    <template v-if="view === 'stream'">
      <PostCover v-if="post.closed" :post="post" />
      <template v-else-if="post.html">
        <div
          ref="text"
          class="feed-post__text"
          :class="{
            'feed-post__text--collapsed': !expanded,
            'feed-post__text--cut': !expanded && overflowing,
          }"
          @load.capture="measure"
        >
          <PostBody :html="post.html" :media="post.media" />
        </div>
        <Button
          v-if="overflowing || expanded"
          type="link"
          class="feed-post__more"
          @click="expanded = !expanded"
        >
          {{ expanded ? t('feed.collapse') : t('feed.expand') }}
        </Button>
      </template>
      <template v-if="!post.closed">
        <MediaAudio
          v-for="audio in looseAudio.slice(0, AUDIO_IN_STREAM)"
          :key="audio.id"
          :media="audio"
        />
        <p v-if="looseAudio.length > AUDIO_IN_STREAM" class="feed-post__note">
          {{ t('feed.moreAudio', { n: looseAudio.length - AUDIO_IN_STREAM }) }}
        </p>
        <p v-if="attachments" class="feed-post__note">
          <PaperClipOutlined /> {{ t('feed.attachments', { n: attachments }) }}
        </p>
      </template>
    </template>

    <template v-else-if="view === 'feed'">
      <PostCover v-if="post.closed" :post="post" />
      <p v-if="post.excerpt" class="feed-post__excerpt">{{ post.excerpt }}</p>
      <RouterLink v-if="!post.closed" :to="to" class="feed-post__read">
        {{ t('feed.readOn') }}
      </RouterLink>
    </template>

    <footer class="feed-post__foot">
      <PostBadges :post="post" />
      <span v-if="view !== 'tile'" class="feed-post__tags">
        <Tag v-for="tag in post.tags" :key="tag.id">{{ tag.name }}</Tag>
      </span>
      <RouterLink v-if="view === 'stream'" :to="to" class="feed-post__open">
        <Button>{{ t('feed.openPost') }}</Button>
      </RouterLink>
    </footer>
  </article>
</template>

<style scoped>
.feed-post {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  padding: 20px 24px;
  border: 1px solid var(--c-border, rgba(128, 128, 128, 0.25));
  border-radius: 8px;
  background: var(--c-card, transparent);
}

.feed-post--tile {
  padding: 16px;
}

.feed-post__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
  opacity: 0.65;
}

.feed-post__length {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.feed-post__title {
  margin: 0;
  font-size: 22px;
  font-weight: 500;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.feed-post--tile .feed-post__title {
  display: -webkit-box;
  overflow: hidden;
  font-size: 16px;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  line-clamp: 3;
}

.feed-post__title a {
  color: inherit;
}

.feed-post__title a:hover {
  color: var(--c-primary, #fa541c);
}

.feed-post__text--collapsed {
  position: relative;
  max-height: 420px;
  overflow: hidden;
}

/* The text fades out where it is cut, so that the cut doesn't look like the end. */
.feed-post__text--cut::after {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 72px;
  background: linear-gradient(transparent, var(--c-card, #fff));
  content: '';
  pointer-events: none;
}

.feed-post__more {
  align-self: flex-start;
  padding: 0;
}

.feed-post__excerpt {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  line-clamp: 3;
}

.feed-post__read {
  align-self: flex-start;
  color: var(--c-primary, #fa541c);
}

.feed-post__note {
  margin: 0;
  opacity: 0.65;
}

.feed-post__foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: auto;
}

.feed-post__tags {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px 0;
}

.feed-post__open {
  margin-left: auto;
}

.feed-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--c-border, rgba(128, 128, 128, 0.25));
  color: inherit;
}

.feed-row:hover .feed-row__title {
  color: var(--c-primary, #fa541c);
}

.feed-row__thumb {
  flex-shrink: 0;
  width: 64px;
  height: 36px;
  overflow: hidden;
  border-radius: 4px;
  background: var(--c-fill, rgba(128, 128, 128, 0.12));
}

.feed-row__thumb img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.feed-row__title {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}

.feed-row__icons {
  display: inline-flex;
  flex-shrink: 0;
  gap: 8px;
  opacity: 0.55;
}

.feed-row__date {
  flex-shrink: 0;
  font-size: 13px;
  opacity: 0.65;
  white-space: nowrap;
}
</style>
