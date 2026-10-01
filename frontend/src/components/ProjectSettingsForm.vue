<script setup lang="ts">
import { Modal, Select, Switch } from 'ant-design-vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  MediaMode,
  PendingMedia,
  ProjectInfo,
  ProjectSettings,
  VideoQuality,
} from '@/api/types'
import { useFormat } from '@/composables/format'
import { useProjectsStore } from '@/stores/projects'

/** A project's settings: whether it is updated with the rest, and what media it downloads by itself. */
const props = defineProps<{ project: ProjectInfo }>()

const { t } = useI18n()
const { bytes } = useFormat()
const projects = useProjectsStore()
const saving = ref(false)
const failed = ref(false)

const modes = computed(() => [
  { value: 'auto', label: t('projectSettings.auto') },
  { value: 'manual', label: t('projectSettings.manual') },
])

/** Ant's Select has no null among its values, so "the best" travels as 0. */
const BEST = 0
const qualities = computed(() => [
  { value: BEST, label: t('projectSettings.best') },
  ...[1080, 720, 480, 360].map((height) => ({ value: height, label: `${height}p` })),
])

const kinds = [
  { field: 'media_mode_audio', label: 'projectSettings.audio' },
  { field: 'media_mode_video', label: 'projectSettings.video' },
  { field: 'media_mode_attach', label: 'projectSettings.attach' },
] as const

/** A kind was switched to «сразу» and there are files of it to get: ask before taking them. */
function offer(pending: PendingMedia): void {
  if (pending.files === 0) {
    return
  }
  const lines = [t('projectSettings.offer.files', { n: pending.files }, pending.files)]
  if (pending.bytes > 0) {
    lines.push(t('projectSettings.offer.size', { size: bytes(pending.bytes) }))
  }
  if (pending.files_without_size > 0) {
    lines.push(t('projectSettings.offer.unknown', { n: pending.files_without_size }))
  }
  Modal.confirm({
    title: t('projectSettings.offer.title'),
    content: lines.join(' '),
    okText: t('projectSettings.offer.ok'),
    cancelText: t('projectSettings.offer.later'),
    onOk: () => projects.download(props.project.id).catch(() => undefined),
  })
}

async function change(settings: ProjectSettings): Promise<void> {
  saving.value = true
  failed.value = false
  try {
    offer(await projects.change(props.project.id, settings))
  } catch {
    failed.value = true
  } finally {
    saving.value = false
  }
}

function setMode(field: (typeof kinds)[number]['field'], mode: MediaMode): void {
  void change({ [field]: mode })
}

function setQuality(value: number): void {
  void change({ video_quality: (value === BEST ? null : value) as VideoQuality })
}
</script>

<template>
  <div class="project-settings">
    <label class="project-settings__row">
      <span>{{ t('projectSettings.syncEnabled') }}</span>
      <Switch
        :checked="project.sync_enabled"
        :loading="saving"
        @change="(checked) => change({ sync_enabled: Boolean(checked) })"
      />
    </label>
    <label v-for="kind in kinds" :key="kind.field" class="project-settings__row">
      <span>{{ t(kind.label) }}</span>
      <Select
        class="project-settings__select"
        :value="project[kind.field]"
        :options="modes"
        :disabled="saving"
        @change="(mode) => setMode(kind.field, mode as MediaMode)"
      />
    </label>
    <label class="project-settings__row">
      <span>{{ t('projectSettings.quality') }}</span>
      <Select
        class="project-settings__select"
        :value="project.video_quality ?? BEST"
        :options="qualities"
        :disabled="saving"
        @change="(height) => setQuality(Number(height))"
      />
    </label>
    <p class="project-settings__hint">{{ t('projectSettings.qualityHint') }}</p>
    <p v-if="failed" class="project-settings__error">{{ t('projectSettings.failed') }}</p>
  </div>
</template>

<style scoped>
.project-settings {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.project-settings__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.project-settings__select {
  width: 200px;
}

.project-settings__hint {
  margin: 0;
  font-size: 13px;
  opacity: 0.65;
}

.project-settings__error {
  margin: 0;
  color: var(--c-error, #cf1322);
}
</style>
