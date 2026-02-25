<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    open: boolean;
    title: string;
    body: string;
    confirmLabel?: string;
    cancelLabel?: string;
    confirmVariant?: "primary" | "danger" | "warning";
    loading?: boolean;
  }>(),
  {
    confirmLabel: "Confirm",
    cancelLabel: "Cancel",
    confirmVariant: "primary",
    loading: false,
  }
);

const emit = defineEmits<{
  (event: "update:open", value: boolean): void;
  (event: "confirm"): void;
}>();

function closeModal() {
  emit("update:open", false);
}

function confirmAndClose() {
  emit("confirm");
}
</script>

<template>
  <pf-modal :open="props.open" :title="props.title" @update:open="emit('update:open', $event)">
    <p>{{ props.body }}</p>
    <template #footer>
      <pf-button
        :variant="props.confirmVariant"
        :disabled="props.loading"
        @click="confirmAndClose"
      >
        {{ props.loading ? "Working…" : props.confirmLabel }}
      </pf-button>
      <pf-button variant="link" :disabled="props.loading" @click="closeModal">
        {{ props.cancelLabel }}
      </pf-button>
    </template>
  </pf-modal>
</template>
