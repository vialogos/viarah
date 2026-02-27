<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();

const email = ref("");
const submitting = ref(false);
const error = ref("");
const sent = ref(false);

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function submit() {
  error.value = "";
  sent.value = false;

  const normalized = email.value.trim().toLowerCase();
  if (!normalized) {
    error.value = "Email is required.";
    return;
  }

  submitting.value = true;
  try {
    await api.passwordResetRequest({ email: normalized });
    sent.value = true;
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
        <pf-title h="1" size="2xl">Reset password</pf-title>
        <pf-content>
          <p class="muted">
            Enter your email address. If an account exists, you’ll receive a password reset link.
          </p>
        </pf-content>

        <pf-alert v-if="sent" inline variant="success" title="Check your email">
          If your email is registered, a reset link will arrive shortly.
        </pf-alert>

        <pf-form class="form" @submit.prevent="submit">
          <pf-form-group label="Email" field-id="password-reset-email">
            <pf-text-input
              id="password-reset-email"
              v-model="email"
              type="email"
              autocomplete="email"
              inputmode="email"
              :disabled="submitting"
              required
            />
          </pf-form-group>

          <div class="actions">
            <pf-button type="submit" :disabled="submitting">
              {{ submitting ? "Sending…" : "Send reset link" }}
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

