<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { api } from "../api";
import type { CustomFieldDefinition, CustomFieldType, SavedView, Task } from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

const context = useContextStore();
const session = useSessionStore();

const tasks = ref<Task[]>([]);
const savedViews = ref<SavedView[]>([]);
const customFields = ref<CustomFieldDefinition[]>([]);
const loading = ref(false);
const loadingSavedViews = ref(false);
const loadingCustomFields = ref(false);
const error = ref("");

const STATUS_OPTIONS = [
  { value: "backlog", label: "Backlog" },
  { value: "in_progress", label: "In progress" },
  { value: "qa", label: "QA" },
  { value: "done", label: "Done" },
] as const;

const activeRole = computed(
  () => session.memberships.find((m) => m.org.id === context.orgId)?.role ?? ""
);
const canManageCustomization = computed(() => ["admin", "pm"].includes(activeRole.value));

const selectedSavedViewId = ref("");
const selectedStatuses = ref<string[]>([]);
const search = ref("");
const sortField = ref<"created_at" | "updated_at" | "title">("created_at");
const sortDirection = ref<"asc" | "desc">("asc");
const groupBy = ref<"none" | "status">("none");

const newCustomFieldName = ref("");
const newCustomFieldType = ref<CustomFieldType>("text");
const newCustomFieldOptions = ref("");
const newCustomFieldClientSafe = ref(false);
const creatingCustomField = ref(false);

function buildSavedViewPayload() {
  return {
    filters: { status: selectedStatuses.value, search: search.value },
    sort: { field: sortField.value, direction: sortDirection.value },
    group_by: groupBy.value,
  };
}

function applySavedView(view: SavedView) {
  selectedStatuses.value = [...(view.filters?.status ?? [])];
  search.value = view.filters?.search ?? "";
  sortField.value = view.sort?.field ?? "created_at";
  sortDirection.value = view.sort?.direction ?? "asc";
  groupBy.value = view.group_by ?? "none";
}

async function refresh() {
  error.value = "";

  if (!context.orgId || !context.projectId) {
    tasks.value = [];
    return;
  }

  loading.value = true;
  try {
    const res = await api.listTasks(context.orgId, context.projectId);
    tasks.value = res.tasks;
  } catch (err) {
    tasks.value = [];
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function refreshSavedViews() {
  if (!context.orgId || !context.projectId) {
    savedViews.value = [];
    selectedSavedViewId.value = "";
    return;
  }

  loadingSavedViews.value = true;
  try {
    const res = await api.listSavedViews(context.orgId, context.projectId);
    savedViews.value = res.saved_views;

    if (
      selectedSavedViewId.value &&
      !savedViews.value.some((v) => v.id === selectedSavedViewId.value)
    ) {
      selectedSavedViewId.value = "";
    }
  } catch (err) {
    savedViews.value = [];
    selectedSavedViewId.value = "";
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingSavedViews.value = false;
  }
}

async function refreshCustomFields() {
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
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingCustomFields.value = false;
  }
}

async function refreshAll() {
  await Promise.all([refresh(), refreshSavedViews(), refreshCustomFields()]);
}

watch(
  () => [context.orgId, context.projectId],
  () => {
    selectedSavedViewId.value = "";
    selectedStatuses.value = [];
    search.value = "";
    sortField.value = "created_at";
    sortDirection.value = "asc";
    groupBy.value = "none";
    void refreshAll();
  },
  { immediate: true }
);

watch(selectedSavedViewId, (next) => {
  if (!next) {
    return;
  }

  const view = savedViews.value.find((v) => v.id === next);
  if (!view) {
    return;
  }

  applySavedView(view);
});

const filteredTasks = computed(() => {
  const needle = search.value.trim().toLowerCase();
  const allowedStatuses = new Set(selectedStatuses.value);

  const items = tasks.value.filter((task) => {
    if (allowedStatuses.size && !allowedStatuses.has(task.status)) {
      return false;
    }
    if (needle && !task.title.toLowerCase().includes(needle)) {
      return false;
    }
    return true;
  });

  const dir = sortDirection.value === "asc" ? 1 : -1;
  items.sort((a, b) => {
    if (sortField.value === "title") {
      return a.title.localeCompare(b.title) * dir;
    }
    const aVal = Date.parse(a[sortField.value]);
    const bVal = Date.parse(b[sortField.value]);
    return (aVal - bVal) * dir;
  });

  return items;
});

const taskGroups = computed(() => {
  if (groupBy.value === "none") {
    return [{ key: "all", label: "", tasks: filteredTasks.value }];
  }

  const groups: Array<{ key: string; label: string; tasks: Task[] }> = [];
  for (const option of STATUS_OPTIONS) {
    const groupTasks = filteredTasks.value.filter((task) => task.status === option.value);
    if (!groupTasks.length) {
      continue;
    }
    groups.push({ key: option.value, label: option.label, tasks: groupTasks });
  }
  return groups;
});

function formatCustomFieldValue(field: CustomFieldDefinition, value: unknown): string {
  if (value == null) {
    return "";
  }

  if (field.field_type === "multi_select") {
    return Array.isArray(value) ? value.join(", ") : String(value);
  }

  return String(value);
}

function displayFieldsForTask(task: Task): Array<{ id: string; label: string }> {
  const map = new Map(task.custom_field_values.map((v) => [v.field_id, v.value]));
  const items: Array<{ id: string; label: string }> = [];
  for (const field of customFields.value) {
    const value = map.get(field.id);
    if (value == null) {
      continue;
    }
    items.push({ id: field.id, label: `${field.name}: ${formatCustomFieldValue(field, value)}` });
  }
  return items;
}

async function createSavedView() {
  if (!context.orgId || !context.projectId) {
    return;
  }

  const name = window.prompt("Saved view name");
  if (!name || !name.trim()) {
    return;
  }

  error.value = "";
  try {
    const res = await api.createSavedView(context.orgId, context.projectId, {
      name: name.trim(),
      ...buildSavedViewPayload(),
    });
    await refreshSavedViews();
    selectedSavedViewId.value = res.saved_view.id;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function updateSavedView() {
  if (!context.orgId || !selectedSavedViewId.value) {
    return;
  }

  error.value = "";
  try {
    await api.updateSavedView(context.orgId, selectedSavedViewId.value, buildSavedViewPayload());
    await refreshSavedViews();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function deleteSavedView() {
  if (!context.orgId || !selectedSavedViewId.value) {
    return;
  }

  if (!window.confirm("Delete this saved view?")) {
    return;
  }

  error.value = "";
  try {
    await api.deleteSavedView(context.orgId, selectedSavedViewId.value);
    selectedSavedViewId.value = "";
    await refreshSavedViews();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

function parseCustomFieldOptions(raw: string): string[] {
  const parts = raw
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);
  return Array.from(new Set(parts));
}

async function createCustomField() {
  if (!context.orgId || !context.projectId) {
    return;
  }

  const name = newCustomFieldName.value.trim();
  if (!name) {
    error.value = "custom field name is required";
    return;
  }

  const payload: {
    name: string;
    field_type: CustomFieldType;
    options?: string[];
    client_safe?: boolean;
  } = {
    name,
    field_type: newCustomFieldType.value,
    client_safe: newCustomFieldClientSafe.value,
  };
  if (newCustomFieldType.value === "select" || newCustomFieldType.value === "multi_select") {
    payload.options = parseCustomFieldOptions(newCustomFieldOptions.value);
  }

  creatingCustomField.value = true;
  error.value = "";
  try {
    await api.createCustomField(context.orgId, context.projectId, payload);
    newCustomFieldName.value = "";
    newCustomFieldOptions.value = "";
    newCustomFieldType.value = "text";
    newCustomFieldClientSafe.value = false;
    await refreshCustomFields();
    await refresh();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    creatingCustomField.value = false;
  }
}

async function archiveCustomField(field: CustomFieldDefinition) {
  if (!context.orgId) {
    return;
  }

  if (!window.confirm(`Archive custom field "${field.name}"?`)) {
    return;
  }

  error.value = "";
  try {
    await api.deleteCustomField(context.orgId, field.id);
    await refreshCustomFields();
    await refresh();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function toggleClientSafe(field: CustomFieldDefinition) {
  if (!context.orgId) {
    return;
  }

  error.value = "";
  try {
    await api.updateCustomField(context.orgId, field.id, { client_safe: field.client_safe });
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}
</script>

<template>
  <div>
    <h1 class="page-title">Work</h1>
    <p class="muted">Tasks scoped to the selected org + project.</p>

    <p v-if="!context.orgId" class="card">Select an org to continue.</p>
    <p v-else-if="!context.projectId" class="card">Select a project to continue.</p>

    <div v-else>
      <div class="card">
        <div class="toolbar">
          <div class="toolbar-row">
            <label class="toolbar-label">
              Saved view
              <select v-model="selectedSavedViewId">
                <option value="">(none)</option>
                <option v-for="view in savedViews" :key="view.id" :value="view.id">
                  {{ view.name }}
                </option>
              </select>
            </label>

            <span v-if="loadingSavedViews" class="muted">Loading views…</span>

            <div v-if="canManageCustomization" class="toolbar-actions">
              <button type="button" @click="createSavedView">Save new</button>
              <button type="button" :disabled="!selectedSavedViewId" @click="updateSavedView">
                Update
              </button>
              <button type="button" :disabled="!selectedSavedViewId" @click="deleteSavedView">
                Delete
              </button>
            </div>
          </div>

          <div class="toolbar-row">
            <label class="toolbar-label">
              Search
              <input v-model="search" type="search" placeholder="Filter by title…" />
            </label>

            <fieldset class="status-filters">
              <legend class="muted">Status</legend>
              <label v-for="option in STATUS_OPTIONS" :key="option.value" class="status-filter">
                <input v-model="selectedStatuses" type="checkbox" :value="option.value" />
                {{ option.label }}
              </label>
            </fieldset>

            <label class="toolbar-label">
              Sort
              <select v-model="sortField">
                <option value="created_at">Created</option>
                <option value="updated_at">Updated</option>
                <option value="title">Title</option>
              </select>
            </label>

            <label class="toolbar-label">
              Direction
              <select v-model="sortDirection">
                <option value="asc">Asc</option>
                <option value="desc">Desc</option>
              </select>
            </label>

            <label class="toolbar-label">
              Group
              <select v-model="groupBy">
                <option value="none">None</option>
                <option value="status">Status</option>
              </select>
            </label>
          </div>
        </div>

        <div v-if="loading" class="muted">Loading…</div>
        <div v-else-if="error" class="error">{{ error }}</div>
        <div v-else-if="filteredTasks.length === 0" class="muted">No tasks yet.</div>
        <div v-else class="groups">
          <div v-for="group in taskGroups" :key="group.key" class="group">
            <h2 v-if="group.label" class="group-title">{{ group.label }}</h2>
            <ul class="list">
              <li v-for="task in group.tasks" :key="task.id" class="item">
                <div class="item-main">
                  <RouterLink :to="`/work/${task.id}`">{{ task.title }}</RouterLink>
                  <div v-if="displayFieldsForTask(task).length" class="custom-values">
                    <span
                      v-for="item in displayFieldsForTask(task)"
                      :key="item.id"
                      class="pill"
                    >
                      {{ item.label }}
                    </span>
                  </div>
                </div>
                <span class="muted status">{{ task.status }}</span>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <div class="card">
        <h2 class="section-title">Custom fields</h2>
        <p class="muted">Project-scoped fields used on tasks and subtasks.</p>

        <div v-if="loadingCustomFields" class="muted">Loading custom fields…</div>
        <div v-else-if="customFields.length === 0" class="muted">No custom fields yet.</div>
        <ul v-else class="custom-fields">
          <li v-for="field in customFields" :key="field.id" class="custom-field">
            <div class="custom-field-main">
              <div class="custom-field-name">{{ field.name }}</div>
              <div class="muted custom-field-type">{{ field.field_type }}</div>
            </div>
            <label v-if="canManageCustomization" class="custom-field-safe">
              <input
                v-model="field.client_safe"
                type="checkbox"
                @change="toggleClientSafe(field)"
              />
              Client safe
            </label>
            <button
              v-if="canManageCustomization"
              type="button"
              class="danger"
              @click="archiveCustomField(field)"
            >
              Archive
            </button>
          </li>
        </ul>

        <form v-if="canManageCustomization" class="new-field" @submit.prevent="createCustomField">
          <h3 class="section-title">Add field</h3>
          <div class="new-field-row">
            <label class="toolbar-label">
              Name
              <input v-model="newCustomFieldName" type="text" placeholder="e.g., Priority" />
            </label>

            <label class="toolbar-label">
              Type
              <select v-model="newCustomFieldType">
                <option value="text">Text</option>
                <option value="number">Number</option>
                <option value="date">Date</option>
                <option value="select">Select</option>
                <option value="multi_select">Multi-select</option>
              </select>
            </label>

            <label class="toolbar-label">
              Options
              <input
                v-model="newCustomFieldOptions"
                :disabled="newCustomFieldType !== 'select' && newCustomFieldType !== 'multi_select'"
                type="text"
                placeholder="Comma-separated (select types only)"
              />
            </label>

            <label class="toolbar-label">
              Client safe
              <input v-model="newCustomFieldClientSafe" type="checkbox" />
            </label>

            <button type="submit" :disabled="creatingCustomField">Create</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 1rem;
}

.toolbar-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}

.toolbar-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
}

.toolbar-actions {
  display: flex;
  gap: 0.5rem;
}

.status-filters {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 0.75rem;
}

.status-filter {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.9rem;
}

.groups {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.group-title {
  margin: 0.5rem 0;
  font-size: 1rem;
}

.list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border);
}

.item-main {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.custom-values {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.pill {
  display: inline-flex;
  align-items: center;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  border: 1px solid var(--border);
  font-size: 0.85rem;
  color: var(--muted);
}

.item:last-child {
  border-bottom: none;
}

.status {
  font-size: 0.85rem;
}

.section-title {
  margin: 0.5rem 0;
  font-size: 1rem;
}

.custom-fields {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.custom-field {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border);
}

.custom-field:last-child {
  border-bottom: none;
}

.custom-field-main {
  display: flex;
  flex-direction: column;
}

.custom-field-name {
  font-weight: 600;
}

.custom-field-type {
  font-size: 0.85rem;
}

.custom-field-safe {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.9rem;
}

.new-field {
  margin-top: 1rem;
  border-top: 1px solid var(--border);
  padding-top: 1rem;
}

.new-field-row {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 0.75rem;
}

.danger {
  border-color: #b42318;
  color: #b42318;
}
</style>
