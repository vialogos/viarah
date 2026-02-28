<script setup lang="ts">
import { computed, ref, watch } from "vue";

const MAX_RESULTS = 200;

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    disabled?: boolean;
    placeholder?: string;
  }>(),
  {
    modelValue: "",
    disabled: false,
    placeholder: "UTC",
  }
);

const emit = defineEmits<{
  (event: "update:modelValue", value: string): void;
}>();

const open = ref(false);
const query = ref("");

function supportedTimezones(): string[] {
  try {
    // Modern runtimes (including most Chromium-based browsers) support `Intl.supportedValuesOf`.
    const supportedValuesOf = (Intl as unknown as { supportedValuesOf?: (key: string) => string[] })
      .supportedValuesOf;
    if (typeof supportedValuesOf === "function") {
      const values = supportedValuesOf("timeZone");
      if (Array.isArray(values) && values.length > 0) {
        return values;
      }
    }
  } catch {
    // Fall through to the fallback list.
  }

  return [
    "UTC",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "Europe/London",
    "Europe/Paris",
    "Asia/Tokyo",
    "Asia/Singapore",
    "Australia/Sydney",
  ];
}

const allTimezones = computed(() => {
  const raw = supportedTimezones().map((value) => String(value || "").trim()).filter(Boolean);
  const unique = Array.from(new Set(raw)).sort((a, b) => a.localeCompare(b));
  const utcIndex = unique.indexOf("UTC");
  if (utcIndex > 0) {
    unique.splice(utcIndex, 1);
    unique.unshift("UTC");
  }
  return unique;
});

const normalizedQuery = computed(() => query.value.trim().toLowerCase());

const filteredTimezones = computed(() => {
  const needle = normalizedQuery.value;
  const current = String(props.modelValue || "").trim();
  const base = allTimezones.value;

  const matches = needle
    ? base.filter((tz) => tz.toLowerCase().includes(needle))
    : base;

  const limited = matches.slice(0, MAX_RESULTS);

  // If the current value isn't a canonical IANA string, keep it visible.
  if (current && !limited.includes(current)) {
    return [current, ...limited];
  }

  return limited;
});

const isTruncated = computed(() => {
  const needle = normalizedQuery.value;
  const baseCount = needle
    ? allTimezones.value.filter((tz) => tz.toLowerCase().includes(needle)).length
    : allTimezones.value.length;
  return baseCount > MAX_RESULTS;
});

const canUseCustom = computed(() => {
  const needle = query.value.trim();
  if (!needle) {
    return false;
  }
  return !allTimezones.value.includes(needle);
});

function onSelected(value: unknown) {
  open.value = false;
  query.value = "";
  if (Array.isArray(value)) {
    emit("update:modelValue", String(value[0] || "").trim());
    return;
  }
  emit("update:modelValue", String(value || "").trim());
}

watch(
  () => open.value,
  (isOpen) => {
    if (!isOpen) {
      query.value = "";
    }
  }
);
</script>

<template>
  <pf-select
    v-model:open="open"
    :disabled="props.disabled"
    :selected="props.modelValue || props.placeholder"
    full-width
    @update:selected="onSelected"
  >
    <template #label>
      <span v-if="props.modelValue">{{ props.modelValue }}</span>
      <span v-else class="muted">{{ props.placeholder }}</span>
    </template>

    <pf-menu-input>
      <div @click.stop>
        <pf-search-input
          v-model="query"
          aria-label="Search timezones"
          placeholder="Search timezones…"
          @clear="query = ''"
        />
      </div>
    </pf-menu-input>

    <pf-divider />

    <pf-menu-list>
      <pf-menu-item v-if="canUseCustom" :value="query.trim()">
        Use: {{ query.trim() }}
      </pf-menu-item>
      <pf-menu-item v-for="tz in filteredTimezones" :key="tz" :value="tz">{{ tz }}</pf-menu-item>
    </pf-menu-list>

    <pf-helper-text v-if="isTruncated" class="small">
      <pf-helper-text-item>Showing first {{ MAX_RESULTS }} results. Search to narrow.</pf-helper-text-item>
    </pf-helper-text>
  </pf-select>
</template>

<style scoped>
.muted {
  color: #6b7280;
}
</style>
