<script setup lang="ts">
import { ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import { defaultAuthedPathForMemberships } from "../routerGuards";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const token = ref("");
const password = ref("");
const displayName = ref("");

const submitting = ref(false);
const error = ref("");

function stripTokenQueryParam() {
  if (!("token" in route.query)) {
    return;
  }

  const nextQuery = { ...route.query };
  delete nextQuery.token;
  void router.replace({ query: nextQuery });
}

watch(
  () => route.query.token,
  (value) => {
    const raw = Array.isArray(value) ? value[0] : value;
    if (typeof raw !== "string" || !raw.trim()) {
      return;
    }

    token.value = raw.trim();
    stripTokenQueryParam();
  },
  { immediate: true }
);

async function submit() {
  error.value = "";
  const rawToken = token.value.trim();
  if (!rawToken) {
    error.value = "Token is required.";
    return;
  }

  submitting.value = true;
  try {
    const res = await api.acceptInvite({
      token: rawToken,
      password: password.value,
      display_name: displayName.value.trim() ? displayName.value.trim() : undefined,
    });

    const me = await api.getMe();
    session.applyMe(me);
    context.setOrgId(res.membership.org.id);

    if (res.needs_profile_setup) {
      await router.push({ path: "/profile/setup" });
      return;
    }

    await router.push({ path: defaultAuthedPathForMemberships(session.memberships) });
  } catch (err) {
    if (err instanceof ApiError && err.status === 403) {
      error.value = "Not permitted.";
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="page">
    <pf-card class="card">
      <pf-card-body>
        <pf-title h="1" size="2xl">Accept invite</pf-title>
        <pf-content>
          <p class="muted">
            Enter your invite token and choose a password. If you already have an account, use your existing password.
          </p>
        </pf-content>

        <pf-form class="form" @submit.prevent="submit">
          <pf-form-group label="Token" field-id="invite-accept-token">
            <pf-text-input id="invite-accept-token" v-model="token" type="text" autocomplete="off" required />
          </pf-form-group>

          <pf-form-group label="Password" field-id="invite-accept-password">
            <pf-text-input
              id="invite-accept-password"
              v-model="password"
              type="password"
              autocomplete="new-password"
              required
            />
          </pf-form-group>

          <pf-form-group label="Display name (optional)" field-id="invite-accept-display-name">
            <pf-text-input
              id="invite-accept-display-name"
              v-model="displayName"
              type="text"
              autocomplete="name"
              placeholder="Your name"
            />
          </pf-form-group>

          <pf-button type="submit" :disabled="submitting">{{ submitting ? "Accepting…" : "Accept invite" }}</pf-button>

          <pf-alert v-if="error" inline variant="danger" :title="error" />
        </pf-form>
      </pf-card-body>
    </pf-card>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.25rem;
}

.card {
  width: 100%;
  max-width: 520px;
}

.form {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
</style>
