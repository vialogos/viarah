<script setup lang="ts">
import { computed } from "vue";

import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

const session = useSessionStore();
const context = useContextStore();

const orgOptions = computed(() =>
  session.memberships.map((m) => ({
    id: m.org.id,
    name: m.org.name,
  }))
);

function onOrgChange(event: Event) {
  const orgId = (event.target as HTMLSelectElement).value;
  context.setOrgId(orgId);
}

function onProjectChange(event: Event) {
  const projectId = (event.target as HTMLSelectElement).value;
  context.setProjectId(projectId);
}
</script>

<template>
  <div class="switcher">
    <div v-if="orgOptions.length === 0" class="muted">No org access</div>

    <label v-else class="field pf-v6-c-form__group">
      <span class="label">Org</span>
      <select class="pf-v6-c-form-control" :value="context.orgId" @change="onOrgChange">
        <option v-for="org in orgOptions" :key="org.id" :value="org.id">
          {{ org.name }}
        </option>
      </select>
    </label>

    <label class="field pf-v6-c-form__group">
      <span class="label">Project</span>
      <select
        class="pf-v6-c-form-control"
        :value="context.projectId"
        :disabled="!context.orgId || context.loadingProjects"
        @change="onProjectChange"
      >
        <option value="">(none)</option>
        <option v-for="project in context.projects" :key="project.id" :value="project.id">
          {{ project.name }}
        </option>
      </select>
    </label>
  </div>
</template>

<style scoped>
.switcher {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 220px;
}

.label {
  font-size: 0.85rem;
  color: var(--muted);
  font-weight: var(--pf-t--global--font--weight--body--bold);
}
</style>
