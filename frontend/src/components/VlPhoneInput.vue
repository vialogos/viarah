<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { parsePhoneNumberFromString } from "libphonenumber-js";

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    disabled?: boolean;
    placeholder?: string;
    id?: string;
  }>(),
  {
    modelValue: "",
    disabled: false,
    placeholder: "+1 555 555 5555",
    id: undefined,
  }
);

const emit = defineEmits<{
	(event: "update:modelValue", value: string): void;
}>();

const displayValue = ref<string>(props.modelValue ?? "");
const error = ref("");

watch(
  () => props.modelValue,
  (value) => {
    const normalized = value ?? "";
    if (normalized !== displayValue.value) {
      displayValue.value = normalized;
    }
  }
);

const helperText = computed(() => {
  if (error.value) {
    return { variant: "error" as const, text: error.value };
  }
  return {
    variant: "default" as const,
    text: "Use international format when possible (e.g. +44 …).",
  };
});

function onBlur() {
  error.value = "";
  const raw = String(displayValue.value || "").trim();
  if (!raw) {
    emit("update:modelValue", "");
    return;
  }

  const parsed = parsePhoneNumberFromString(raw);
  if (!parsed) {
    emit("update:modelValue", raw);
    return;
  }

  if (!parsed.isValid()) {
    error.value = "Phone number looks invalid.";
    emit("update:modelValue", raw);
    return;
  }

  const formatted = parsed.formatInternational();
  displayValue.value = formatted;
  emit("update:modelValue", formatted);
}
</script>

<template>
  <div class="stack">
    <pf-text-input
      :id="props.id"
      v-model="displayValue"
      type="tel"
      autocomplete="tel"
      :disabled="props.disabled"
      :placeholder="props.placeholder"
      @blur="onBlur"
    />
    <pf-helper-text class="small">
      <pf-helper-text-item :variant="helperText.variant">{{ helperText.text }}</pf-helper-text-item>
    </pf-helper-text>
  </div>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
</style>
