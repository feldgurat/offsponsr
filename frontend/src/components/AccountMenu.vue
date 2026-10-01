<script setup lang="ts">
import { Button } from 'ant-design-vue'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { useAccountStore } from '@/stores/account'

import CookieLoginModal from './CookieLoginModal.vue'

const { t } = useI18n()
const account = useAccountStore()
const cookieModalOpen = ref(false)
</script>

<template>
  <div class="account">
    <template v-if="account.info.signed_in">
      <span class="account__email">{{ account.info.email }}</span>
      <Button ghost class="account__out" :disabled="account.busy" @click="account.logout()">
        {{ t('account.signOut') }}
      </Button>
    </template>
    <template v-else>
      <span v-if="account.busy" class="account__hint">{{ t('account.signingIn') }}</span>
      <Button v-else type="link" class="account__cookie" @click="cookieModalOpen = true">
        {{ t('account.withCookie') }}
      </Button>
      <Button type="primary" :loading="account.busy" @click="account.login()">
        {{ t('account.signIn') }}
      </Button>
    </template>

    <CookieLoginModal v-model:open="cookieModalOpen" />
  </div>
</template>

<style scoped>
.account {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 12px;
  margin-left: auto;
}

.account__email,
.account__hint {
  color: rgba(255, 255, 255, 0.85);
}

.account__cookie {
  color: rgba(255, 255, 255, 0.65);
}

/* The header is dark in both themes; the dark theme's own ghost button would vanish on it. */
.account__out:not(:disabled) {
  border-color: rgba(255, 255, 255, 0.45);
  color: rgba(255, 255, 255, 0.85);
}
</style>
