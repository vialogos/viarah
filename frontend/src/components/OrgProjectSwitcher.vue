<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";
import { isClientOnlyMemberships } from "../routerGuards";
import { shellIconMap } from "../layouts/shellIcons";

const session = useSessionStore();
const context = useContextStore();

const canUseGlobalScopes = computed(() => !isClientOnlyMemberships(session.memberships));
const orgMenuOpen = ref(false);
const projectMenuOpen = ref(false);

const orgOptions = computed(() =>
  session.memberships.map((m) => ({
    id: m.org.id,
    name: m.org.name,
  }))
);

const orgToggleLabel = computed(() => {
  if (context.orgScope === "all") {
    return "All orgs";
  }
  const selected = orgOptions.value.find((org) => org.id === context.orgId);
  if (selected) {
    return selected.name;
  }
  return "Select org";
});

const projectToggleLabel = computed(() => {
  if (context.orgScope === "all" || !context.orgId) {
    return "Project";
  }
  if (context.projectScope === "all") {
    return "All projects";
  }
  if (!context.projectId) {
    return "(none)";
  }
  const selected = context.projects.find((project) => project.id === context.projectId);
  return selected?.name ?? "Project";
});

const projectToggleDisabled = computed(
  () => context.orgScope === "all" || !context.orgId || context.loadingProjects
);

function onOrgChange(orgId: string) {
  if (orgId === "__all__") {
    context.setOrgScopeAll();
    return;
  }
  context.setOrgId(orgId);
}

function onProjectChange(projectId: string) {
  if (projectId === "__all__") {
    context.setProjectScopeAll();
    return;
  }
  context.setProjectId(projectId);
}

watch(projectToggleDisabled, (disabled) => {
  if (disabled) {
    projectMenuOpen.value = false;
  }
});
</script>

<template>
  <div class="switcher">
    <div v-if="orgOptions.length === 0" class="muted">No org access</div>

    <template v-else>
      <pf-dropdown
        :open="orgMenuOpen"
        append-to="body"
        placement="bottom-start"
        @update:open="(open) => (orgMenuOpen = open)"
      >
        <template #toggle>
          <pf-menu-toggle variant="plainText" :expanded="orgMenuOpen" aria-label="Org">
            <template #icon>
              <pf-icon inline>
                <component :is="shellIconMap.organizations" class="switcher-icon" aria-hidden="true" />
              </pf-icon>
            </template>
            <span class="toggle-text">{{ orgToggleLabel }}</span>
          </pf-menu-toggle>
        </template>

        <pf-dropdown-list>
          <pf-dropdown-item
            v-if="canUseGlobalScopes"
            :active="context.orgScope === 'all'"
            @click="
              () => {
                onOrgChange('__all__');
                orgMenuOpen = false;
              }
            "
          >
            All orgs
          </pf-dropdown-item>
          <pf-dropdown-item
            v-for="org in orgOptions"
            :key="org.id"
            :active="context.orgScope === 'single' && context.orgId === org.id"
            @click="
              () => {
                onOrgChange(org.id);
                orgMenuOpen = false;
              }
            "
          >
            {{ org.name }}
          </pf-dropdown-item>
        </pf-dropdown-list>
      </pf-dropdown>

      <pf-dropdown
        :open="projectMenuOpen"
        append-to="body"
        placement="bottom-start"
        @update:open="(open) => (projectMenuOpen = open)"
      >
        <template #toggle>
          <pf-menu-toggle
            variant="plainText"
            :expanded="projectMenuOpen"
            aria-label="Project"
            :disabled="projectToggleDisabled"
          >
            <template #icon>
              <pf-icon inline>
                <component :is="shellIconMap.projects" class="switcher-icon" aria-hidden="true" />
              </pf-icon>
            </template>
            <span class="toggle-text">{{ projectToggleLabel }}</span>
          </pf-menu-toggle>
        </template>

        <pf-dropdown-list>
          <pf-dropdown-item
            :active="context.projectScope === 'single' && !context.projectId"
            @click="
              () => {
                onProjectChange('');
                projectMenuOpen = false;
              }
            "
          >
            (none)
          </pf-dropdown-item>
          <pf-dropdown-item
            v-if="canUseGlobalScopes && context.orgScope === 'single' && context.orgId"
            :active="context.projectScope === 'all'"
            @click="
              () => {
                onProjectChange('__all__');
                projectMenuOpen = false;
              }
            "
          >
            All projects
          </pf-dropdown-item>
          <pf-dropdown-item
            v-for="project in context.projects"
            :key="project.id"
            :active="context.projectScope === 'single' && context.projectId === project.id"
            @click="
              () => {
                onProjectChange(project.id);
                projectMenuOpen = false;
              }
            "
          >
            {{ project.name }}
          </pf-dropdown-item>
        </pf-dropdown-list>
      </pf-dropdown>
    </template>
  </div>
</template>

<style scoped>
.switcher {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.switcher-icon {
  width: 1rem;
  height: 1rem;
  flex-shrink: 0;
}

.toggle-text {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
