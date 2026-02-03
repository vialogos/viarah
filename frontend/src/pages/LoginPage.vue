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

async function submit() {
  formError.value = "";
  submitting.value = true;
  try {
    await session.login(email.value, password.value);
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/work";
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
    <div class="card card-narrow">
      <h1 class="page-title">ViaRah</h1>
      <p class="muted">Sign in with your existing backend account.</p>

      <form class="form" @submit.prevent="submit">
        <label class="field">
          <span class="label">Email</span>
          <input v-model="email" autocomplete="email" inputmode="email" required />
        </label>

        <label class="field">
          <span class="label">Password</span>
          <input v-model="password" type="password" autocomplete="current-password" required />
        </label>

        <button type="submit" :disabled="submitting">
          {{ submitting ? "Signing in..." : "Sign in" }}
        </button>

        <p v-if="formError" class="error">{{ formError }}</p>
      </form>
    </div>
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

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.label {
  font-size: 0.85rem;
  color: var(--muted);
}
</style>
