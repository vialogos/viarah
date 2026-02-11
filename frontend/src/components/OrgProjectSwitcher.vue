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

function onOrgChange(orgId: string) {
  context.setOrgId(orgId);
}

function onProjectChange(projectId: string) {
  context.setProjectId(projectId);
}
</script>

<template>
  <div class="switcher">
    <div v-if="orgOptions.length === 0" class="muted">No org access</div>

    <pf-form-group v-else label="Org" field-id="org-switcher-org" class="field">
      <pf-form-select
        id="org-switcher-org"
        :model-value="context.orgId || ''"
        @update:model-value="onOrgChange(String($event))"
      >
        <pf-form-select-option v-for="org in orgOptions" :key="org.id" :value="org.id">
          {{ org.name }}
        </pf-form-select-option>
      </pf-form-select>
    </pf-form-group>

    <pf-form-group label="Project" field-id="org-switcher-project" class="field">
      <pf-form-select
        id="org-switcher-project"
        :model-value="context.projectId || ''"
        :disabled="!context.orgId || context.loadingProjects"
        @update:model-value="onProjectChange(String($event))"
      >
        <pf-form-select-option value="">(none)</pf-form-select-option>
        <pf-form-select-option v-for="project in context.projects" :key="project.id" :value="project.id">
          {{ project.name }}
        </pf-form-select-option>
      </pf-form-select>
    </pf-form-group>
  </div>
</template>

<style scoped>
.switcher {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
}

.field {
  min-width: 220px;
}
</style>
