<script setup lang="ts">
import { Alert, Modal, Textarea, TypographyParagraph } from 'ant-design-vue'
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useAccountStore } from '@/stores/account'

const open = defineModel<boolean>('open', { required: true })

const { t, te, tm, rt } = useI18n()
const account = useAccountStore()
const cookie = ref('')

watch(open, (isOpen) => {
  if (isOpen) {
    cookie.value = ''
    account.dismissFailure()
  }
})

function failureText(code: string): string {
  const key = `account.errors.${code}`
  return t(te(key) ? key : 'account.errors.unknown')
}

async function submit(): Promise<void> {
  if ((await account.loginWithCookie(cookie.value)) && account.info.signed_in) {
    open.value = false
  }
}
</script>

<template>
  <Modal
    v-model:open="open"
    :title="t('account.cookieModal.title')"
    :ok-text="t('account.signIn')"
    :ok-button-props="{ disabled: !cookie.trim() }"
    :confirm-loading="account.busy"
    @ok="submit"
  >
    <TypographyParagraph>{{ t('account.cookieModal.intro') }}</TypographyParagraph>
    <ol class="cookie-login__steps">
      <li v-for="(step, index) in tm('account.cookieModal.steps')" :key="index">{{ rt(step) }}</li>
    </ol>
    <Textarea
      v-model:value="cookie"
      :rows="5"
      :placeholder="t('account.cookieModal.placeholder')"
      spellcheck="false"
    />
    <TypographyParagraph type="secondary" class="cookie-login__warning">
      {{ t('account.cookieModal.warning') }}
    </TypographyParagraph>
    <Alert v-if="account.failure" type="error" show-icon :message="failureText(account.failure)" />
  </Modal>
</template>

<style scoped>
.cookie-login__steps {
  padding-left: 20px;
}

.cookie-login__warning {
  margin-top: 8px;
}
</style>
