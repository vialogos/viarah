<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();

const uid = computed(() => (typeof route.query.uid === "string" ? route.query.uid.trim() : ""));
const token = computed(() => (typeof route.query.token === "string" ? route.query.token.trim() : ""));

const password = ref("");
const passwordConfirm = ref("");
const submitting = ref(false);
const error = ref("");
const done = ref(false);

const canSubmit = computed(() => Boolean(uid.value && token.value));

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function submit() {
  error.value = "";
  done.value = false;

  if (!uid.value || !token.value) {
    error.value = "Reset link is missing required parameters.";
    return;
  }

  if (!password.value) {
    error.value = "Password is required.";
    return;
  }
  if (password.value !== passwordConfirm.value) {
    error.value = "Passwords do not match.";
    return;
  }

  submitting.value = true;
  try {
    await api.passwordResetConfirm({ uid: uid.value, token: token.value, password: password.value });
    done.value = true;
    password.value = "";
    passwordConfirm.value = "";
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
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
    <pf-card class="card-narrow">
      <pf-card-body>
        <pf-title h="1" size="2xl">Set a new password</pf-title>

        <pf-alert v-if="done" inline variant="success" title="Password updated">
          You can now sign in with your new password.
        </pf-alert>

        <pf-alert v-else-if="!canSubmit" inline variant="warning" title="Invalid reset link">
          Open the password reset link from your email again, or request a new one.
        </pf-alert>

        <pf-form class="form" @submit.prevent="submit">
          <pf-form-group label="New password" field-id="password-reset-new-password">
            <pf-text-input
              id="password-reset-new-password"
              v-model="password"
              type="password"
              autocomplete="new-password"
              :disabled="submitting || !canSubmit"
              required
            />
          </pf-form-group>

          <pf-form-group label="Confirm new password" field-id="password-reset-confirm-password">
            <pf-text-input
              id="password-reset-confirm-password"
              v-model="passwordConfirm"
              type="password"
              autocomplete="new-password"
              :disabled="submitting || !canSubmit"
              required
            />
          </pf-form-group>

          <div class="actions">
            <pf-button type="submit" :disabled="submitting || !canSubmit">
              {{ submitting ? "Saving…" : "Save password" }}
            </pf-button>
            <pf-button type="button" variant="link" :disabled="submitting" @click="router.push('/password-reset')">
              Request a new link
            </pf-button>
            <pf-button type="button" variant="link" :disabled="submitting" @click="router.push('/login')">
              Back to login
            </pf-button>
          </div>

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

.card-narrow {
  width: 100%;
  max-width: 480px;
}

.form {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}
</style>

