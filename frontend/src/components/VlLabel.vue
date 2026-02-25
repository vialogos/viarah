<script setup lang="ts">
import type { VlLabelColor } from "../utils/labels";

const props = withDefaults(
  defineProps<{
    color?: VlLabelColor | null;
    variant?: "outline" | "filled";
    title?: string;
  }>(),
  {
    color: null,
    variant: "filled",
    title: undefined,
  }
);
</script>

<template>
  <pf-label :color="props.color || undefined" :outline="props.variant === 'outline'" :title="props.title">
    <slot />
  </pf-label>
</template>
