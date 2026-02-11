<script setup lang="ts">
type LabelColor = "blue" | "red" | "orange" | "yellow" | "green" | "teal" | "purple";

const props = withDefaults(
  defineProps<{
    color?: LabelColor | null;
    variant?: "outline" | "filled";
    title?: string;
  }>(),
  {
    color: null,
    variant: "outline",
    title: undefined,
  }
);
</script>

<template>
  <pf-label :color="props.color || undefined" :outline="props.variant === 'outline'" :title="props.title">
    <slot />
  </pf-label>
</template>
