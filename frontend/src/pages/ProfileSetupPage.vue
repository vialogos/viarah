<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import { defaultAuthedPathForMemberships } from "../routerGuards";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const loading = ref(false);
const saving = ref(false);
const error = ref("");

const orgName = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.orgs.find((org) => org.id === context.orgId)?.name ?? "";
});

const timezone = ref("UTC");
const skills = ref<string[]>([]);
const skillInput = ref("");

function normalizeSkills(values: string[]): string[] {
  const out: string[] = [];
  for (const raw of values) {
    const trimmed = String(raw || "").trim();
    if (!trimmed) {
      continue;
    }
    if (!out.includes(trimmed)) {
      out.push(trimmed);
    }
  }
  return out;
}

function addSkill() {
  const raw = skillInput.value;
  if (!raw.trim()) {
    return;
  }
  const parts = raw
    .split(/[,\n]/g)
    .map((value) => value.trim())
    .filter(Boolean);
  skills.value = normalizeSkills([...skills.value, ...parts]);
  skillInput.value = "";
}

function removeSkill(value: string) {
  skills.value = skills.value.filter((s) => s !== value);
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";
  if (!context.orgId) {
    return;
  }

  loading.value = true;
  try {
    const res = await api.getMyPerson(context.orgId);
    timezone.value = (res.person.timezone || "UTC").trim() || "UTC";
    skills.value = Array.isArray(res.person.skills) ? [...res.person.skills] : [];
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      error.value = "Not permitted.";
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

watch(() => context.orgId, () => void refresh(), { immediate: true });

async function saveAndContinue() {
  error.value = "";
  if (!context.orgId) {
    error.value = "Select an org first.";
    return;
  }

  saving.value = true;
  try {
    await api.updateMyPerson(context.orgId, {
      timezone: timezone.value.trim() || "UTC",
      skills: normalizeSkills(skills.value),
    });
    await router.push({ path: defaultAuthedPathForMemberships(session.memberships) });
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      error.value = "Not permitted.";
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <pf-card>
    <pf-card-title>
      <pf-title h="1" size="2xl">Profile setup</pf-title>
    </pf-card-title>

    <pf-card-body>
      <pf-content>
        <p class="muted">
          Complete your profile so staffing, search, and availability planning work well.
          <span v-if="orgName">Org: <strong>{{ orgName }}</strong></span>
        </p>
      </pf-content>

      <pf-empty-state v-if="!context.orgId">
        <pf-empty-state-header title="Select an org" heading-level="h2" />
        <pf-empty-state-body>Select an org to complete your profile.</pf-empty-state-body>
      </pf-empty-state>

      <div v-else-if="loading" class="loading-row">
        <pf-spinner size="md" aria-label="Loading profile" />
      </div>

      <pf-alert v-else-if="error" inline variant="danger" :title="error" />

      <pf-form v-else class="form" @submit.prevent="saveAndContinue">
        <pf-form-group label="Timezone" field-id="profile-timezone">
          <pf-text-input id="profile-timezone" v-model="timezone" type="text" placeholder="e.g., America/New_York" />
        </pf-form-group>

        <pf-form-group label="Add skill" field-id="profile-skill-add">
          <pf-input-group>
            <pf-text-input
              id="profile-skill-add"
              v-model="skillInput"
              type="text"
              placeholder="e.g., Django, Vue, UX"
              @keydown.enter.prevent="addSkill"
            />
            <pf-button type="button" variant="secondary" :disabled="!skillInput.trim()" @click="addSkill">
              Add
            </pf-button>
          </pf-input-group>
          <pf-helper-text>
            <pf-helper-text-item>Comma or newline separated. Duplicate skills are ignored.</pf-helper-text-item>
          </pf-helper-text>
        </pf-form-group>

        <pf-form-group label="Current skills">
          <pf-label-group v-if="skills.length" :num-labels="12">
            <pf-label
              v-for="skill in skills"
              :key="skill"
              color="blue"
              variant="outline"
              close-btn-aria-label="Remove skill"
              :on-close="() => removeSkill(skill)"
            >
              {{ skill }}
            </pf-label>
          </pf-label-group>
          <pf-empty-state v-else variant="small">
            <pf-empty-state-header title="No skills yet" heading-level="h3" />
            <pf-empty-state-body>Add at least one skill so staffing/search works well.</pf-empty-state-body>
          </pf-empty-state>
        </pf-form-group>

        <div class="actions">
          <pf-button type="submit" :disabled="saving">
            {{ saving ? "Saving…" : "Save and continue" }}
          </pf-button>
          <pf-button type="button" variant="link" :disabled="saving" @click="router.push({ path: '/dashboard' })">
            Skip for now
          </pf-button>
        </div>
      </pf-form>
    </pf-card-body>
  </pf-card>
</template>

<style scoped>
.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
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
}
</style>
