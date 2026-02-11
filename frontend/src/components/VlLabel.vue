<script setup lang="ts">
import { computed } from "vue";

type LabelColor =
  | "blue"
  | "red"
  | "orange"
  | "orangered"
  | "yellow"
  | "green"
  | "teal"
  | "purple"
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "custom";

const props = withDefaults(
  defineProps<{
    color?: LabelColor | null;
    variant?: "outline" | "filled";
    compact?: boolean;
    title?: string;
  }>(),
  {
    color: null,
    variant: "outline",
    compact: true,
    title: undefined,
  }
);

const classes = computed(() => [
  "pf-v6-c-label",
  props.variant === "outline" ? "pf-m-outline" : "pf-m-filled",
  props.compact ? "pf-m-compact" : null,
  props.color ? `pf-m-${props.color}` : null,
]);
</script>

<template>
  <span :class="classes" :title="props.title">
    <span class="pf-v6-c-label__content">
      <span class="pf-v6-c-label__text">
        <slot />
      </span>
    </span>
  </span>
</template>

