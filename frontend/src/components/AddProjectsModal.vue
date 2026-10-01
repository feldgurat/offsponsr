<script setup lang="ts">
import {
  Alert,
  Checkbox,
  Input,
  Modal,
  Spin,
  TypographyParagraph,
  TypographyTitle,
} from 'ant-design-vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { api, ApiError } from '@/api/client'
import type { SubscriptionInfo } from '@/api/types'
import { useProjectsStore } from '@/stores/projects'

const open = defineModel<boolean>('open', { required: true })

const { t, te } = useI18n()
const projects = useProjectsStore()

const subscriptions = ref<SubscriptionInfo[]>([])
const loading = ref(false)
/** Why the subscriptions couldn't be loaded; the address field still works then. */
const loadFailure = ref<string | null>(null)
const chosen = ref<number[]>([])
const address = ref('')
const submitting = ref(false)
const submitFailure = ref<string | null>(null)

const nothingToAdd = computed(() => chosen.value.length === 0 && address.value.trim() === '')

function codeOf(error: unknown): string {
  return (error instanceof ApiError ? error.code : null) ?? 'unknown'
}

function reason(code: string): string {
  const key = `addProjects.errors.${code}`
  return t(te(key) ? key : 'addProjects.errors.unknown')
}

async function loadSubscriptions(): Promise<void> {
  loading.value = true
  loadFailure.value = null
  try {
    subscriptions.value = await api.get<SubscriptionInfo[]>('/subscriptions')
  } catch (error) {
    subscriptions.value = []
    loadFailure.value = codeOf(error)
  } finally {
    loading.value = false
  }
}

watch(open, (isOpen) => {
  if (isOpen) {
    chosen.value = []
    address.value = ''
    submitFailure.value = null
    void loadSubscriptions()
  }
})

function toggle(id: number, checked: boolean): void {
  chosen.value = checked ? [...chosen.value, id] : chosen.value.filter((other) => other !== id)
}

async function submit(): Promise<void> {
  submitting.value = true
  submitFailure.value = null
  try {
    await projects.add(chosen.value, address.value)
    open.value = false
  } catch (error) {
    submitFailure.value = codeOf(error)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Modal
    v-model:open="open"
    :title="t('addProjects.title')"
    :ok-text="t('addProjects.submit')"
    :ok-button-props="{ disabled: nothingToAdd }"
    :confirm-loading="submitting"
    @ok="submit"
  >
    <TypographyTitle :level="5">{{ t('addProjects.subscriptions') }}</TypographyTitle>
    <Spin v-if="loading" />
    <Alert v-else-if="loadFailure" type="warning" show-icon :message="reason(loadFailure)" />
    <TypographyParagraph v-else-if="subscriptions.length === 0" type="secondary">
      {{ t('addProjects.noSubscriptions') }}
    </TypographyParagraph>
    <ul v-else class="add-projects__list">
      <li v-for="subscription in subscriptions" :key="subscription.id">
        <Checkbox
          :checked="subscription.in_library || chosen.includes(subscription.id)"
          :disabled="subscription.in_library"
          @update:checked="(checked: boolean) => toggle(subscription.id, checked)"
        >
          <span class="add-projects__title">{{ subscription.title }}</span>
          <span v-if="subscription.in_library" class="add-projects__note">
            {{ t('addProjects.inLibrary') }}
          </span>
          <span v-else-if="subscription.level_name" class="add-projects__note">
            {{ subscription.level_name }}
          </span>
        </Checkbox>
      </li>
    </ul>

    <TypographyTitle :level="5" class="add-projects__by-address">
      {{ t('addProjects.byAddress') }}
    </TypographyTitle>
    <Input
      v-model:value="address"
      :placeholder="t('addProjects.addressPlaceholder')"
      spellcheck="false"
      allow-clear
    />
    <TypographyParagraph type="secondary" class="add-projects__hint">
      {{ t('addProjects.addressHint') }}
    </TypographyParagraph>

    <Alert v-if="submitFailure" type="error" show-icon :message="reason(submitFailure)" />
  </Modal>
</template>

<style scoped>
.add-projects__list {
  max-height: 260px;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  list-style: none;
}

.add-projects__list li {
  padding: 4px 0;
}

.add-projects__title {
  font-weight: 500;
}

.add-projects__note {
  margin-left: 8px;
  opacity: 0.6;
}

.add-projects__by-address {
  margin-top: 20px;
}

.add-projects__hint {
  margin-top: 8px;
}
</style>
