<script setup lang="ts">
import { ref } from "vue";
import { useRoute } from "vue-router";

import { isShellNavItemActive, type ShellNavGroup, type ShellNavItem } from "./appShellNav";
import SidebarRailToggle from "./SidebarRailToggle.vue";
import { shellIconMap } from "./shellIcons";

const props = withDefaults(
  defineProps<{
    groups: ShellNavGroup[];
    collapsed?: boolean;
  }>(),
  {
    collapsed: false,
  }
);

const emit = defineEmits<{
  (event: "navigate"): void;
}>();

const route = useRoute();
const openGroupId = ref<string | null>(null);

function itemIsActive(item: ShellNavItem): boolean {
  return isShellNavItemActive(item, route.path);
}

function groupIsActive(group: ShellNavGroup): boolean {
  return group.items.some((item) => itemIsActive(item));
}

function setGroupOpen(groupId: string, open: boolean) {
  openGroupId.value = open ? groupId : openGroupId.value === groupId ? null : openGroupId.value;
}

function onRailSelect() {
  openGroupId.value = null;
  emit("navigate");
}
</script>

<template>
  <nav v-if="props.collapsed" class="sidebar-rail" aria-label="Internal navigation">
    <div class="rail-items">
      <pf-dropdown
        v-for="group in props.groups"
        :key="group.id"
        :open="openGroupId === group.id"
        append-to="body"
        placement="right-start"
        @update:open="(open) => setGroupOpen(group.id, open)"
        @select="onRailSelect"
      >
        <template #toggle>
          <SidebarRailToggle :label="group.label" :active="groupIsActive(group)">
            <template #icon>
              <pf-icon inline>
                <component :is="shellIconMap[group.icon]" class="nav-icon" aria-hidden="true" />
              </pf-icon>
            </template>
          </SidebarRailToggle>
        </template>

        <pf-dropdown-list>
          <pf-dropdown-item
            v-for="item in group.items"
            :key="item.id"
            :value="item.id"
            :to="item.to"
            :active="itemIsActive(item)"
          >
            <template #icon>
              <pf-icon inline>
                <component :is="shellIconMap[item.icon]" class="nav-icon" aria-hidden="true" />
              </pf-icon>
            </template>
            {{ item.label }}
          </pf-dropdown-item>
        </pf-dropdown-list>
      </pf-dropdown>
    </div>
  </nav>

  <pf-nav v-else class="sidebar-nav" aria-label="Internal navigation">
    <pf-nav-list>
      <pf-nav-group v-for="group in props.groups" :key="group.id" :title="group.label">
        <pf-nav-item
          v-for="item in group.items"
          :key="item.id"
          :item-id="item.id"
          :to="item.to"
          :active="itemIsActive(item)"
          @click="emit('navigate')"
        >
          <template #icon>
            <pf-icon inline>
              <component :is="shellIconMap[item.icon]" class="nav-icon" aria-hidden="true" />
            </pf-icon>
          </template>
          <span>{{ item.label }}</span>
        </pf-nav-item>
      </pf-nav-group>
    </pf-nav-list>
  </pf-nav>
</template>

<style scoped>
.sidebar-nav {
  width: 100%;
}

.sidebar-rail {
  width: 100%;
}

.rail-items {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  padding: 0.5rem 0;
}

.nav-icon {
  width: 1rem;
  height: 1rem;
}

</style>
