<script setup lang="ts">
import { onMounted, watch } from "vue";
import { useRouter } from "vue-router";

import OrgProjectSwitcher from "../components/OrgProjectSwitcher.vue";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const session = useSessionStore();
const context = useContextStore();

async function logout() {
  await session.logout();
  await router.push("/login");
}

onMounted(() => {
  context.syncFromMemberships(session.memberships);
});

watch(
  () => context.orgId,
  async (nextOrgId, prevOrgId) => {
    if (nextOrgId && nextOrgId !== prevOrgId) {
      await context.refreshProjects();
    }
  },
  { immediate: true }
);
</script>

<template>
  <div class="layout">
    <header class="topbar">
      <div class="brand">ViaRah</div>
      <div class="spacer" />
      <div v-if="session.user" class="user muted" :title="session.user.email">
        {{ session.user.display_name || session.user.email }}
      </div>
      <OrgProjectSwitcher />
      <button type="button" @click="logout">Logout</button>
    </header>

    <main class="container">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--panel);
  border-bottom: 1px solid var(--border);
  padding: 0.75rem 1rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.brand {
  font-weight: 700;
}

.spacer {
  flex: 1;
}

.user {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
