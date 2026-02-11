<script setup lang="ts">
import { useRoute } from "vue-router";

import { isShellNavItemActive, type ShellNavGroup, type ShellNavItem } from "./appShellNav";
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

function itemIsActive(item: ShellNavItem): boolean {
  return isShellNavItemActive(item, route.path);
}
</script>

<template>
  <pf-nav class="sidebar-nav" aria-label="Internal navigation">
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
          <span v-if="!props.collapsed">{{ item.label }}</span>
          <span v-else class="sr-only">{{ item.label }}</span>
        </pf-nav-item>
      </pf-nav-group>
    </pf-nav-list>
  </pf-nav>
</template>

<style scoped>
.sidebar-nav {
  width: 100%;
}

.nav-icon {
  width: 1rem;
  height: 1rem;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
