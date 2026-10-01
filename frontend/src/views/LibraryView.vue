<script setup lang="ts">
import { Button, Empty, Tag, TypographyParagraph, TypographyTitle } from 'ant-design-vue'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import type { ProjectInfo } from '@/api/types'
import AddProjectsModal from '@/components/AddProjectsModal.vue'
import { useFormat } from '@/composables/format'
import { useAccountStore } from '@/stores/account'
import { useProjectsStore } from '@/stores/projects'
import { useSyncStore } from '@/stores/sync'

const { t } = useI18n()
const account = useAccountStore()
const projects = useProjectsStore()
const sync = useSyncStore()
const adding = ref(false)
const { dateTime } = useFormat()

onMounted(() => {
  void projects.load().catch(() => undefined)
})

function syncedAt(project: ProjectInfo): string {
  return project.last_synced_at
    ? t('library.syncedAt', { date: dateTime(project.last_synced_at) })
    : t('library.neverSynced')
}
</script>

<template>
  <section>
    <div class="library__head">
      <TypographyTitle :level="2" class="library__title">{{ t('library.title') }}</TypographyTitle>
      <template v-if="account.info.signed_in">
        <Button @click="adding = true">{{ t('library.addProjects') }}</Button>
        <Button
          v-if="projects.list.length"
          type="primary"
          :disabled="sync.busy"
          @click="sync.start()"
        >
          {{ t('library.updateAll') }}
        </Button>
      </template>
    </div>

    <ul v-if="projects.list.length" class="library__projects">
      <li v-for="project in projects.list" :key="project.id" class="library__project">
        <RouterLink
          class="library__project-link"
          :to="{ name: 'project', params: { id: project.id } }"
        >
          <span class="library__logo">
            <img v-if="project.logo" :src="project.logo" alt="" loading="lazy" />
          </span>
          <span class="library__project-text">
            <span class="library__project-title">{{ project.title }}</span>
            <span class="library__project-meta">
              <span>{{ t('library.posts', { n: project.posts }, project.posts) }}</span>
              <span>{{ syncedAt(project) }}</span>
              <span v-if="project.posts_without_text">
                {{ t('library.withoutText', { n: project.posts_without_text }) }}
              </span>
              <span v-if="!project.sync_enabled">{{ t('library.syncDisabled') }}</span>
            </span>
          </span>
        </RouterLink>
        <Tag v-if="sync.statusOf(project.id) === 'running'" color="processing">
          {{ t('library.running') }}
        </Tag>
        <Tag v-else-if="sync.statusOf(project.id) === 'queued'">{{ t('library.queued') }}</Tag>
        <Button
          v-else-if="account.info.signed_in"
          :disabled="sync.state.cancelling"
          @click="sync.start([project.id])"
        >
          {{ t('library.update') }}
        </Button>
      </li>
    </ul>

    <Empty v-else-if="projects.loaded" :description="t('library.empty')">
      <template v-if="!account.info.signed_in">
        <TypographyParagraph type="secondary">{{ t('library.signInHint') }}</TypographyParagraph>
        <Button type="primary" :loading="account.busy" @click="account.login()">
          {{ t('account.signIn') }}
        </Button>
      </template>
      <template v-else>
        <TypographyParagraph type="secondary">{{ t('library.addHint') }}</TypographyParagraph>
        <Button type="primary" @click="adding = true">{{ t('library.addProjects') }}</Button>
      </template>
    </Empty>

    <AddProjectsModal v-model:open="adding" />
  </section>
</template>

<style scoped>
.library__head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.library__title {
  flex: 1;
  margin: 0;
}

.library__projects {
  margin: 0;
  padding: 0;
  list-style: none;
}

.library__project {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 0;
  border-bottom: 1px solid rgba(128, 128, 128, 0.25);
}

.library__project-link {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 16px;
  min-width: 0;
  color: inherit;
}

.library__project-link:hover .library__project-title {
  color: var(--c-primary, #fa541c);
}

.library__logo {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  overflow: hidden;
  border-radius: 50%;
  background: var(--c-fill, rgba(128, 128, 128, 0.12));
}

.library__logo img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.library__project-text {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.library__project-title {
  font-size: 16px;
  font-weight: 500;
  overflow-wrap: anywhere;
}

.library__project-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  opacity: 0.65;
}
</style>
