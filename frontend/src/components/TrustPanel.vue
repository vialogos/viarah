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
  <pf-card class="trust">
    <pf-card-body>
      <pf-expandable-section
        :toggle-text-collapsed="props.title"
        :toggle-text-expanded="props.title"
      >
        <pf-description-list columns="2Col">
          <pf-description-list-group v-if="props.progress != null">
            <pf-description-list-term>Progress</pf-description-list-term>
            <pf-description-list-description>{{ formatPercent(props.progress) }}</pf-description-list-description>
          </pf-description-list-group>
          <pf-description-list-group v-if="props.updatedAt">
            <pf-description-list-term>Last updated</pf-description-list-term>
            <pf-description-list-description>{{ formatTimestamp(props.updatedAt) }}</pf-description-list-description>
          </pf-description-list-group>

          <pf-description-list-group v-for="item in summaryItems" :key="item.key">
            <pf-description-list-term>{{ item.label }}</pf-description-list-term>
            <pf-description-list-description>
              <span class="mono">{{ item.value }}</span>
            </pf-description-list-description>
          </pf-description-list-group>
        </pf-description-list>

        <pf-expandable-section
          class="advanced"
          toggle-text-collapsed="Advanced (raw JSON)"
          toggle-text-expanded="Hide raw JSON"
        >
          <pre class="json mono">{{ prettyJson }}</pre>
        </pf-expandable-section>
      </pf-expandable-section>
    </pf-card-body>
  </pf-card>
</template>

<style scoped>
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
