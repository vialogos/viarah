<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { api } from "../api";
import type { CustomFieldDefinition, Task } from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

const props = defineProps<{ taskId: string }>();
const context = useContextStore();
const session = useSessionStore();

const task = ref<Task | null>(null);
const customFields = ref<CustomFieldDefinition[]>([]);
const customFieldDraft = ref<Record<string, unknown>>({});
const initialCustomFieldValues = ref<Record<string, unknown | null>>({});
const loadingCustomFields = ref(false);
const savingCustomFields = ref(false);
const customFieldError = ref("");
const loading = ref(false);
const error = ref("");

const activeRole = computed(
  () => session.memberships.find((m) => m.org.id === context.orgId)?.role ?? ""
);
const canEditCustomFields = computed(() => ["admin", "pm"].includes(activeRole.value));

async function refresh() {
  error.value = "";

  if (!context.orgId) {
    task.value = null;
    return;
  }

  loading.value = true;
  try {
    const res = await api.getTask(context.orgId, props.taskId);
    task.value = res.task;
  } catch (err) {
    task.value = null;
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function refreshCustomFields() {
  customFieldError.value = "";

  if (!context.orgId || !context.projectId) {
    customFields.value = [];
    return;
  }

  loadingCustomFields.value = true;
  try {
    const res = await api.listCustomFields(context.orgId, context.projectId);
    customFields.value = res.custom_fields;
  } catch (err) {
    customFields.value = [];
    customFieldError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingCustomFields.value = false;
  }
}

function formatCustomFieldValue(field: CustomFieldDefinition, value: unknown): string {
  if (value == null) {
    return "";
  }
  if (field.field_type === "multi_select") {
    return Array.isArray(value) ? value.join(", ") : String(value);
  }
  return String(value);
}

function initCustomFieldDraft() {
  if (!task.value) {
    customFieldDraft.value = {};
    initialCustomFieldValues.value = {};
    return;
  }

  const valueMap = new Map(task.value.custom_field_values.map((v) => [v.field_id, v.value]));
  const nextDraft: Record<string, unknown> = {};
  const nextInitial: Record<string, unknown | null> = {};

  for (const field of customFields.value) {
    const current = valueMap.get(field.id);
    if (current == null) {
      if (field.field_type === "multi_select") {
        nextDraft[field.id] = [];
      } else {
        nextDraft[field.id] = "";
      }
      nextInitial[field.id] = null;
    } else {
      nextDraft[field.id] = current;
      nextInitial[field.id] = current as unknown;
    }
  }

  customFieldDraft.value = nextDraft;
  initialCustomFieldValues.value = nextInitial;
}

function valuesEqual(a: unknown | null, b: unknown | null): boolean {
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b)) {
      return false;
    }
    return JSON.stringify(a) === JSON.stringify(b);
  }
  return a === b;
}

function normalizeDraftValue(field: CustomFieldDefinition, raw: unknown): unknown | null {
  if (field.field_type === "multi_select") {
    const values = Array.isArray(raw) ? raw.filter((v) => typeof v === "string") : [];
    return values.length ? values : null;
  }

  if (field.field_type === "number") {
    if (raw == null || raw === "") {
      return null;
    }
    const n = typeof raw === "number" ? raw : Number(raw);
    if (Number.isNaN(n)) {
      throw new Error(`"${field.name}" must be a number`);
    }
    return n;
  }

  const text = String(raw ?? "").trim();
  return text ? text : null;
}

async function saveCustomFieldValues() {
  if (!context.orgId || !task.value) {
    return;
  }

  savingCustomFields.value = true;
  customFieldError.value = "";
  try {
    const values: Record<string, unknown | null> = {};
    for (const field of customFields.value) {
      const nextNormalized = normalizeDraftValue(field, customFieldDraft.value[field.id]);
      const prior = initialCustomFieldValues.value[field.id] ?? null;
      if (valuesEqual(nextNormalized, prior)) {
        continue;
      }
      values[field.id] = nextNormalized;
    }

    if (!Object.keys(values).length) {
      return;
    }

    await api.patchTaskCustomFieldValues(context.orgId, task.value.id, values);
    await refresh();
  } catch (err) {
    customFieldError.value = err instanceof Error ? err.message : String(err);
  } finally {
    savingCustomFields.value = false;
  }
}

watch(() => [context.orgId, props.taskId], () => void refresh(), { immediate: true });

watch(() => [context.orgId, context.projectId], () => void refreshCustomFields(), { immediate: true });

watch(
  () => [task.value, customFields.value],
  () => {
    initCustomFieldDraft();
  }
);
</script>

<template>
  <div>
    <RouterLink to="/work">← Back to Work</RouterLink>

    <div class="card detail">
      <div v-if="!context.orgId" class="muted">Select an org to view work.</div>
      <div v-else-if="loading" class="muted">Loading…</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else-if="!task" class="muted">Not found.</div>
      <div v-else>
        <h1 class="page-title">{{ task.title }}</h1>
        <p class="muted">{{ task.status }}</p>
        <p v-if="task.description">{{ task.description }}</p>

        <div class="meta">
          <div><span class="muted">Progress</span> {{ Math.round(task.progress * 100) }}%</div>
          <div><span class="muted">Task ID</span> {{ task.id }}</div>
        </div>

        <div class="custom-fields">
          <h2 class="section-title">Custom fields</h2>
          <div v-if="loadingCustomFields" class="muted">Loading custom fields…</div>
          <div v-else-if="customFieldError" class="error">{{ customFieldError }}</div>
          <div v-else-if="customFields.length === 0" class="muted">No custom fields yet.</div>
          <div v-else class="field-grid">
            <div v-for="field in customFields" :key="field.id" class="field-row">
              <div class="field-label">{{ field.name }}</div>
              <div v-if="canEditCustomFields" class="field-input">
                <input
                  v-if="field.field_type === 'text'"
                  v-model="customFieldDraft[field.id]"
                  type="text"
                />
                <input
                  v-else-if="field.field_type === 'number'"
                  v-model="customFieldDraft[field.id]"
                  type="number"
                  step="any"
                />
                <input
                  v-else-if="field.field_type === 'date'"
                  v-model="customFieldDraft[field.id]"
                  type="date"
                />
                <select v-else-if="field.field_type === 'select'" v-model="customFieldDraft[field.id]">
                  <option value="">(none)</option>
                  <option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
                </select>
                <select
                  v-else-if="field.field_type === 'multi_select'"
                  v-model="customFieldDraft[field.id]"
                  multiple
                >
                  <option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
                </select>
              </div>
              <div v-else class="muted">
                {{
                  formatCustomFieldValue(
                    field,
                    task.custom_field_values.find((v) => v.field_id === field.id)?.value
                  ) || "—"
                }}
              </div>
            </div>

            <button
              v-if="canEditCustomFields"
              type="button"
              class="save"
              :disabled="savingCustomFields"
              @click="saveCustomFieldValues"
            >
              Save custom fields
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail {
  margin-top: 1rem;
}

.meta {
  margin-top: 1rem;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem;
}

.custom-fields {
  margin-top: 1.5rem;
  border-top: 1px solid var(--border);
  padding-top: 1rem;
}

.section-title {
  margin: 0.5rem 0;
  font-size: 1rem;
}

.field-grid {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.field-row {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 0.75rem;
  align-items: center;
}

.field-label {
  font-weight: 600;
}

.field-input input,
.field-input select {
  width: 100%;
}

.save {
  align-self: start;
}
</style>
