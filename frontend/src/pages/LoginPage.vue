<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useSessionStore } from "../stores/session";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();

const email = ref("");
const password = ref("");
const formError = ref("");
const submitting = ref(false);
const forgotPasswordOpen = ref(false);

async function submit() {
  formError.value = "";
  submitting.value = true;
  try {
    await session.login(email.value, password.value);
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/dashboard";
    await router.push(redirect);
  } catch (err) {
    formError.value = err instanceof Error ? err.message : String(err);
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="page">
    <pf-card class="card-narrow">
      <pf-card-body>
        <pf-title h="1" size="2xl">ViaRah</pf-title>
        <pf-content>
          <p class="muted">Sign in with your existing backend account.</p>
        </pf-content>

        <pf-form class="form" @submit.prevent="submit">
          <pf-form-group label="Email" field-id="login-email">
            <pf-text-input
              id="login-email"
              v-model="email"
              type="email"
              autocomplete="email"
              inputmode="email"
              required
            />
          </pf-form-group>

          <pf-form-group label="Password" field-id="login-password">
            <pf-text-input
              id="login-password"
              v-model="password"
              type="password"
              autocomplete="current-password"
              required
            />
          </pf-form-group>

          <pf-button type="submit" :disabled="submitting">
            {{ submitting ? "Signing in..." : "Sign in" }}
          </pf-button>

          <pf-button type="button" variant="link" @click="forgotPasswordOpen = true">
            Forgot password?
          </pf-button>

          <pf-alert v-if="formError" inline variant="danger" :title="formError" />
        </pf-form>
        <pf-modal
          :open="forgotPasswordOpen"
          title="Forgot password?"
          @update:open="forgotPasswordOpen = $event"
        >
          <pf-content>
            <p class="muted">Self-service password reset is not available yet.</p>
            <p class="muted">Contact your org administrator or operator to reset your password.</p>
          </pf-content>
          <template #footer>
            <pf-button type="button" @click="forgotPasswordOpen = false">Close</pf-button>
          </template>
        </pf-modal>
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
  max-width: 440px;
}

.form {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
</style>
