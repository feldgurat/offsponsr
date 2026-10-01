<script setup lang="ts">
import { Alert, Button, TypographyParagraph, TypographyTitle } from 'ant-design-vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useLibraryStore } from '@/stores/library'

const { t, te } = useI18n()
const library = useLibraryStore()

function reason(code: string): string {
  const key = `libraryError.${code}`
  return t(te(key) ? key : 'libraryError.unknown')
}

/** The user's own failed attempt matters more than the leftover from the previous run. */
const problem = computed(() => {
  if (library.actionFailure) {
    const { code, path } = library.actionFailure
    return { title: reason(code), details: path }
  }
  if (library.lastFailure) {
    const { code, path } = library.lastFailure
    return { title: t('welcome.lastFailure'), details: `${reason(code)}\n${path}` }
  }
  return null
})
</script>

<template>
  <section class="welcome">
    <TypographyTitle class="welcome__title">{{ t('app.title') }}</TypographyTitle>
    <TypographyParagraph class="welcome__lead">{{ t('welcome.lead') }}</TypographyParagraph>

    <Alert
      v-if="problem"
      class="welcome__problem"
      type="warning"
      show-icon
      :message="problem.title"
      :description="problem.details"
    />

    <div class="welcome__actions">
      <Button type="primary" size="large" block :disabled="library.busy" @click="library.create()">
        {{ t('welcome.create') }}
      </Button>
      <Button size="large" block :disabled="library.busy" @click="library.open()">
        {{ t('welcome.open') }}
      </Button>
    </div>

    <TypographyParagraph type="secondary">{{ t('welcome.hint') }}</TypographyParagraph>
  </section>
</template>

<style scoped>
.welcome {
  max-width: 420px;
  margin: 12vh auto 0;
  text-align: center;
}

.welcome__title {
  margin-bottom: 8px;
}

.welcome__lead {
  font-size: 16px;
}

.welcome__problem {
  margin: 24px 0 0;
  text-align: left;
  white-space: pre-line;
  overflow-wrap: anywhere;
}

.welcome__actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 32px 0 24px;
}
</style>
