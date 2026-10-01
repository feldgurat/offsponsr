<script setup lang="ts">
import { Button, Empty, Tag, TypographyParagraph, TypographyTitle } from 'ant-design-vue'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ProjectInfo } from '@/api/types'
import AddProjectsModal from '@/components/AddProjectsModal.vue'
import SyncPanel from '@/components/SyncPanel.vue'
import { useAccountStore } from '@/stores/account'
import { useProjectsStore } from '@/stores/projects'
import { useSyncStore } from '@/stores/sync'

const { t } = useI18n()
const account = useAccountStore()
const projects = useProjectsStore()
const sync = useSyncStore()
const adding = ref(false)

const dateTime = new Intl.DateTimeFormat('ru', { dateStyle: 'medium', timeStyle: 'short' })

onMounted(() => {
  void projects.load().catch(() => undefined)
})

function syncedAt(project: ProjectInfo): string {
  return project.last_synced_at
    ? t('library.syncedAt', { date: dateTime.format(new Date(project.last_synced_at)) })
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

    <SyncPanel />

    <ul v-if="projects.list.length" class="library__projects">
      <li v-for="project in projects.list" :key="project.id" class="library__project">
        <div class="library__project-text">
          <div class="library__project-title">{{ project.title }}</div>
          <div class="library__project-meta">
            <span>{{ t('library.posts', { n: project.posts }, project.posts) }}</span>
            <span>{{ syncedAt(project) }}</span>
            <span v-if="project.posts_without_text">
              {{ t('library.withoutText', { n: project.posts_without_text }) }}
            </span>
          </div>
        </div>
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

.library__project-text {
  flex: 1;
  min-width: 0;
}

.library__project-title {
  font-size: 16px;
  font-weight: 500;
}

.library__project-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  opacity: 0.65;
}
</style>
