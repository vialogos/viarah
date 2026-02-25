<script setup lang="ts">
/**
 * Thin wrapper around PatternFly `pf-label-group` so label clusters get consistent
 * overflow behavior across the app.
 */
const props = withDefaults(
  defineProps<{
    numLabels?: number;
  }>(),
  {
    numLabels: 4,
  }
);
</script>

<template>
  <pf-label-group :num-labels="props.numLabels">
    <slot />
  </pf-label-group>
</template>
