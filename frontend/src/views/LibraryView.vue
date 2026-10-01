<script setup lang="ts">
import { Button, Empty, TypographyParagraph, TypographyTitle } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'

import { useAccountStore } from '@/stores/account'

const { t } = useI18n()
const account = useAccountStore()
</script>

<template>
  <section>
    <TypographyTitle :level="2">{{ t('library.title') }}</TypographyTitle>
    <Empty :description="t('library.empty')">
      <template v-if="!account.info.signed_in">
        <TypographyParagraph type="secondary">{{ t('library.signInHint') }}</TypographyParagraph>
        <Button type="primary" :loading="account.busy" @click="account.login()">
          {{ t('account.signIn') }}
        </Button>
      </template>
    </Empty>
  </section>
</template>
