<script setup lang="ts">
import { Empty, TypographyTitle } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <section>
    <TypographyTitle :level="2">{{ t('library.title') }}</TypographyTitle>
    <Empty :description="t('library.empty')" />
  </section>
</template>
