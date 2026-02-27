<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();

const displayName = ref("");
const savingDisplayName = ref(false);
const displayNameError = ref("");
const displayNameSaved = ref(false);

const currentPassword = ref("");
const newPassword = ref("");
const newPasswordConfirm = ref("");
const changingPassword = ref(false);
const passwordError = ref("");
const passwordSaved = ref(false);

const effectiveEmail = computed(() => session.user?.email ?? "");

watch(
  () => session.user?.display_name,
  (value) => {
    displayName.value = value ?? "";
  },
  { immediate: true }
);

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function saveDisplayName() {
  displayNameError.value = "";
  displayNameSaved.value = false;

  const next = displayName.value.trim();
  if (!next) {
    displayNameError.value = "Display name is required.";
    return;
  }

  savingDisplayName.value = true;
  try {
    await api.patchAuthMe({ display_name: next });
    await session.refresh();
    displayNameSaved.value = true;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    displayNameError.value = err instanceof Error ? err.message : String(err);
  } finally {
    savingDisplayName.value = false;
  }
}

async function changePassword() {
  passwordError.value = "";
  passwordSaved.value = false;

  if (!currentPassword.value) {
    passwordError.value = "Current password is required.";
    return;
  }
  if (!newPassword.value) {
    passwordError.value = "New password is required.";
    return;
  }
  if (newPassword.value !== newPasswordConfirm.value) {
    passwordError.value = "New passwords do not match.";
    return;
  }

  changingPassword.value = true;
  try {
    await api.passwordChange({ current_password: currentPassword.value, new_password: newPassword.value });
    currentPassword.value = "";
    newPassword.value = "";
    newPasswordConfirm.value = "";
    passwordSaved.value = true;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    passwordError.value = err instanceof Error ? err.message : String(err);
  } finally {
    changingPassword.value = false;
  }
}
</script>

<template>
  <div class="page">
    <pf-card class="card">
      <pf-card-title>
        <pf-title h="1" size="2xl">Account settings</pf-title>
      </pf-card-title>

      <pf-card-body>
        <pf-content>
          <p class="muted">Manage your account profile and password.</p>
        </pf-content>

        <pf-description-list class="meta" columns="2Col">
          <pf-description-list-group>
            <pf-description-list-term>Email</pf-description-list-term>
            <pf-description-list-description>
              <span class="muted">{{ effectiveEmail || "—" }}</span>
            </pf-description-list-description>
          </pf-description-list-group>
        </pf-description-list>

        <pf-divider />

        <pf-title h="2" size="xl">Profile</pf-title>
        <pf-alert v-if="displayNameSaved" inline variant="success" title="Saved" />

        <pf-form class="form" @submit.prevent="saveDisplayName">
          <pf-form-group label="Display name" field-id="account-display-name">
            <pf-text-input
              id="account-display-name"
              v-model="displayName"
              type="text"
              autocomplete="name"
              :disabled="savingDisplayName"
              required
            />
          </pf-form-group>

          <pf-button type="submit" :disabled="savingDisplayName">
            {{ savingDisplayName ? "Saving…" : "Save profile" }}
          </pf-button>

          <pf-alert v-if="displayNameError" inline variant="danger" :title="displayNameError" />
        </pf-form>

        <pf-divider />

        <pf-title h="2" size="xl">Password</pf-title>
        <pf-alert v-if="passwordSaved" inline variant="success" title="Password updated" />

        <pf-form class="form" @submit.prevent="changePassword">
          <pf-form-group label="Current password" field-id="account-current-password">
            <pf-text-input
              id="account-current-password"
              v-model="currentPassword"
              type="password"
              autocomplete="current-password"
              :disabled="changingPassword"
              required
            />
          </pf-form-group>

          <pf-form-group label="New password" field-id="account-new-password">
            <pf-text-input
              id="account-new-password"
              v-model="newPassword"
              type="password"
              autocomplete="new-password"
              :disabled="changingPassword"
              required
            />
          </pf-form-group>

          <pf-form-group label="Confirm new password" field-id="account-confirm-password">
            <pf-text-input
              id="account-confirm-password"
              v-model="newPasswordConfirm"
              type="password"
              autocomplete="new-password"
              :disabled="changingPassword"
              required
            />
          </pf-form-group>

          <pf-button type="submit" :disabled="changingPassword">
            {{ changingPassword ? "Saving…" : "Change password" }}
          </pf-button>

          <pf-alert v-if="passwordError" inline variant="danger" :title="passwordError" />
        </pf-form>
      </pf-card-body>
    </pf-card>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  justify-content: center;
}

.card {
  width: 100%;
  max-width: 720px;
}

.meta {
  margin-top: 0.75rem;
}

.form {
  margin-top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
</style>

