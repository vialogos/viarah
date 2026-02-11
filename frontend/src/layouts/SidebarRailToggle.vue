<script setup lang="ts">
import { useAttrs } from "vue";

defineOptions({ inheritAttrs: false });

/**
 * Icon-only menu toggle used in the collapsed desktop sidebar rail.
 * Wraps `pf-menu-toggle` with a tooltip and active-state styling.
 */
const props = withDefaults(
  defineProps<{
    label: string;
    active?: boolean;
    expanded?: boolean;
  }>(),
  {
    active: false,
    expanded: false,
  }
);

const emit = defineEmits<{
  (event: "update:expanded", value: boolean): void;
}>();

const attrs = useAttrs();
</script>

<template>
  <pf-tooltip :content="props.label" position="right">
    <pf-menu-toggle
      v-bind="attrs"
      variant="plain"
      :expanded="props.expanded"
      :class="['rail-toggle', { 'rail-toggle--active': props.active }]"
      :aria-label="props.label"
      @update:expanded="(value) => emit('update:expanded', value)"
    >
      <template #icon>
        <slot name="icon" />
      </template>
    </pf-menu-toggle>
  </pf-tooltip>
</template>

<style scoped>
.rail-toggle--active {
  color: var(--pf-t--global--text--color--brand--default);
}
</style>
