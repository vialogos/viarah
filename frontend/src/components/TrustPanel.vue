<script setup lang="ts">
import { computed } from "vue";

import type { ProgressWhy } from "../api/types";
import { formatPercent, formatTimestamp } from "../utils/format";

const props = defineProps<{
  title: string;
  progressWhy: ProgressWhy;
  progress?: number | null;
  updatedAt?: string | null;
}>();

function formatWhyValue(value: unknown): string {
  if (value == null) {
    return "—";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

const summaryItems = computed(() => {
  const why = props.progressWhy ?? {};

  const preferredKeys: Array<{ key: string; label: string }> = [
    { key: "policy", label: "Policy" },
    { key: "reason", label: "Reason" },
    { key: "workflow_id", label: "Workflow" },
    { key: "workflow_stage_id", label: "Workflow stage" },
    { key: "task_count", label: "Tasks" },
    { key: "subtask_count", label: "Subtasks" },
    { key: "stage_count", label: "Stage count" },
    { key: "done_stage_order", label: "Done stage order" },
    { key: "stage_order", label: "Stage order" },
    { key: "subtask_counts_by_stage_order", label: "Subtasks by stage" },
  ];

  return preferredKeys
    .filter(({ key }) => Object.prototype.hasOwnProperty.call(why, key))
    .map(({ key, label }) => ({
      key,
      label,
      value: formatWhyValue(why[key]),
    }));
});

const prettyJson = computed(() => {
  try {
    return JSON.stringify(props.progressWhy ?? {}, null, 2);
  } catch {
    return "{}";
  }
});
</script>

<template>
  <details class="trust">
    <summary class="trust-summary">{{ title }}</summary>
    <div class="trust-body">
      <div class="grid">
        <div v-if="progress != null" class="kv">
          <div class="muted">Progress</div>
          <div>{{ formatPercent(progress) }}</div>
        </div>
        <div v-if="updatedAt" class="kv">
          <div class="muted">Last updated</div>
          <div>{{ formatTimestamp(updatedAt) }}</div>
        </div>

        <div v-for="item in summaryItems" :key="item.key" class="kv">
          <div class="muted">{{ item.label }}</div>
          <div class="mono">{{ item.value }}</div>
        </div>
      </div>

      <details class="advanced">
        <summary class="trust-summary">Advanced (raw JSON)</summary>
        <pre class="json mono">{{ prettyJson }}</pre>
      </details>
    </div>
  </details>
</template>

<style scoped>
.trust {
  margin-top: 1rem;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--panel);
}

.trust-summary {
  cursor: pointer;
  padding: 0.75rem 1rem;
  font-weight: 600;
}

.trust-body {
  padding: 0 1rem 1rem 1rem;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.75rem;
}

.kv {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0.75rem;
  background: #fbfbfd;
}

.advanced {
  margin-top: 0.75rem;
}

.json {
  margin: 0.75rem 0 0 0;
  padding: 0.75rem;
  background: #0b1020;
  color: #e5e7eb;
  border-radius: 12px;
  overflow: auto;
  font-size: 0.85rem;
  line-height: 1.4;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
    monospace;
}
</style>
