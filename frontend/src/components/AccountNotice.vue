<script setup lang="ts">
import { Alert } from 'ant-design-vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useAccountStore } from '@/stores/account'

const { t, te } = useI18n()
const account = useAccountStore()

/** A failed sign-in, unless the cookie dialog is already showing it. */
const failure = computed(() => {
  const code = account.failure
  if (code === null || code === 'invalid_cookie') {
    return null
  }
  const key = `account.errors.${code}`
  return t(te(key) ? key : 'account.errors.unknown')
})
</script>

<template>
  <Alert
    v-if="failure"
    class="account-notice"
    type="error"
    show-icon
    closable
    :message="failure"
    @close="account.dismissFailure()"
  />
  <Alert
    v-else-if="account.info.expired"
    class="account-notice"
    type="warning"
    show-icon
    :message="t('account.expired')"
  />
</template>

<style scoped>
.account-notice {
  margin-bottom: 16px;
}
</style>
