<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { marked } from "marked";
import xss from "xss";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    disabled?: boolean;
    rows?: number;
    placeholder?: string;
    id?: string;
    label?: string;
  }>(),
  {
    modelValue: "",
    disabled: false,
    rows: 6,
    placeholder: "Write in Markdown…",
    id: undefined,
    label: "",
  }
);

const emit = defineEmits<{
  (event: "update:modelValue", value: string): void;
}>();

const mode = ref<"write" | "preview">("write");

watch(
  () => props.disabled,
  (disabled) => {
    if (disabled && mode.value === "preview") {
      mode.value = "write";
    }
  }
);

const rawHtml = computed(() => {
  try {
    return String(marked.parse(props.modelValue || ""));
  } catch {
    return "";
  }
});

const safeHtml = computed(() => xss(rawHtml.value));
</script>

<template>
  <div class="editor">
    <div class="toolbar" aria-label="Markdown editor toolbar">
      <pf-button
        type="button"
        variant="secondary"
        :disabled="props.disabled"
        @click="mode = mode === 'write' ? 'preview' : 'write'"
      >
        {{ mode === "write" ? "Preview" : "Edit" }}
      </pf-button>
      <span class="spacer" />
      <span v-if="props.label" class="muted small">{{ props.label }}</span>
    </div>

    <pf-textarea
      v-if="mode === 'write'"
      :id="props.id"
      :model-value="props.modelValue"
      :rows="props.rows"
      :disabled="props.disabled"
      :placeholder="props.placeholder"
      @update:model-value="emit('update:modelValue', String($event ?? ''))"
    />

    <div v-else class="preview" aria-label="Markdown preview">
      <pf-content>
        <div v-if="props.modelValue.trim()" v-html="safeHtml" />
        <div v-else class="muted">Nothing to preview yet.</div>
      </pf-content>
    </div>

    <pf-helper-text class="small">
      <pf-helper-text-item>Markdown supported. Preview is sanitized.</pf-helper-text-item>
    </pf-helper-text>
  </div>
</template>

<style scoped>
.editor {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.spacer {
  flex: 1;
}

.preview {
  border: 1px solid #d2d2d2;
  border-radius: 6px;
  padding: 0.75rem;
  background: #fff;
}

.muted {
  color: #6b7280;
}

.small {
  font-size: 0.875rem;
}
</style>
