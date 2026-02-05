<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../api";
import type { OrgMembershipWithUser, Template } from "../api/types";
import { useContextStore } from "../stores/context";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const templates = ref<Template[]>([]);
const memberships = ref<OrgMembershipWithUser[]>([]);
const loading = ref(false);
const creating = ref(false);
const error = ref("");

const templateId = ref("");
const variablesText = ref("{\n  \n}");
const selectedSignerMap = ref<Record<string, boolean>>({});

const currentRole = computed(() => {
  if (!context.orgId) {
    return "";
  }
  return session.memberships.find((m) => m.org.id === context.orgId)?.role ?? "";
});

const canManage = computed(() => currentRole.value === "admin" || currentRole.value === "pm");

const selectedSignerIds = computed(() =>
  Object.entries(selectedSignerMap.value)
    .filter(([, selected]) => selected)
    .map(([userId]) => userId)
);

function toggleSigner(userId: string) {
  selectedSignerMap.value = {
    ...selectedSignerMap.value,
    [userId]: !selectedSignerMap.value[userId],
  };
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";

  if (!context.orgId) {
    templates.value = [];
    memberships.value = [];
    return;
  }

  if (!canManage.value) {
    templates.value = [];
    memberships.value = [];
    error.value = "Only PM/admin can create SoWs for this org.";
    return;
  }

  loading.value = true;
  try {
    const [templatesRes, membershipsRes] = await Promise.all([
      api.listTemplates(context.orgId, { type: "sow" }),
      api.listOrgMemberships(context.orgId, { role: "client" }),
    ]);
    templates.value = templatesRes.templates;
    memberships.value = membershipsRes.memberships;

    if (!templateId.value && templates.value.length > 0) {
      templateId.value = templates.value[0]?.id ?? "";
    }
  } catch (err) {
    templates.value = [];
    memberships.value = [];
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

watch(() => context.orgId, () => void refresh(), { immediate: true });

function parseVariables(): Record<string, unknown> {
  const raw = variablesText.value.trim();
  if (!raw) {
    return {};
  }

  const parsed = JSON.parse(raw) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Variables JSON must be an object.");
  }
  return parsed as Record<string, unknown>;
}

async function submit() {
  error.value = "";

  if (!context.orgId) {
    error.value = "Select an org to continue.";
    return;
  }

  if (!context.projectId) {
    error.value = "Select a project to create a SoW.";
    return;
  }

  if (!templateId.value) {
    error.value = "Select a template.";
    return;
  }

  if (selectedSignerIds.value.length < 1) {
    error.value = "Select at least one signer.";
    return;
  }

  let variables: Record<string, unknown> = {};
  try {
    variables = parseVariables();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
    return;
  }

  creating.value = true;
  try {
    const res = await api.createSow(context.orgId, {
      project_id: context.projectId,
      template_id: templateId.value,
      variables,
      signer_user_ids: selectedSignerIds.value,
    });
    await router.push(`/sows/${res.sow.id}`);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    creating.value = false;
  }
}
</script>

<template>
  <div>
    <RouterLink to="/sows">← Back to SoWs</RouterLink>

    <div class="card detail">
      <h1 class="page-title">New SoW</h1>

      <div v-if="!context.orgId" class="muted">Select an org to continue.</div>
      <div v-else-if="loading" class="muted">Loading…</div>
      <div v-else>
        <div v-if="error" class="error">{{ error }}</div>

        <div v-if="!canManage" class="muted">
          Only PM/admin can create SoWs for this org.
        </div>

        <div v-else>
          <label class="field">
            <span class="label">Template</span>
            <select v-model="templateId" :disabled="templates.length === 0">
              <option v-for="tpl in templates" :key="tpl.id" :value="tpl.id">
                {{ tpl.name }}
              </option>
            </select>
          </label>

          <label class="field">
            <span class="label">Variables (JSON object)</span>
            <textarea v-model="variablesText" rows="8" :disabled="creating" />
          </label>

          <div class="field">
            <div class="label">Client signers</div>
            <div v-if="memberships.length === 0" class="muted">No client memberships found.</div>
            <div v-else class="signers">
              <label v-for="m in memberships" :key="m.user.id" class="signer">
                <input
                  type="checkbox"
                  :checked="Boolean(selectedSignerMap[m.user.id])"
                  :disabled="creating"
                  @change="toggleSigner(m.user.id)"
                />
                <span>{{ m.user.display_name || m.user.email }}</span>
                <span class="muted email">{{ m.user.email }}</span>
              </label>
            </div>
          </div>

          <button type="button" :disabled="creating" @click="submit">Create draft</button>
          <p class="muted note">
            After creating the draft, open the SoW detail page to send for signature and manage the PDF.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail {
  margin-top: 1rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-top: 0.75rem;
}

.label {
  font-size: 0.85rem;
  color: var(--muted);
}

textarea {
  border-radius: 10px;
  border: 1px solid var(--border);
  padding: 0.75rem;
  resize: vertical;
}

.signers {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.25rem;
  padding: 0.5rem;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fbfbfd;
}

.signer {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.email {
  margin-left: auto;
  font-size: 0.85rem;
}

.note {
  margin-top: 0.75rem;
}
</style>
