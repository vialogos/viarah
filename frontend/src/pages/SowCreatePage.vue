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

function toggleSigner(userId: string, selected?: boolean) {
  const nextSelected = selected ?? !selectedSignerMap.value[userId];
  selectedSignerMap.value = {
    ...selectedSignerMap.value,
    [userId]: nextSelected,
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
  <div class="stack">
    <pf-button variant="link" to="/sows">Back to SoWs</pf-button>

    <pf-card class="detail">
      <pf-card-title>
        <pf-title h="1" size="2xl">New SoW</pf-title>
      </pf-card-title>

      <pf-card-body>
        <pf-empty-state v-if="!context.orgId">
          <pf-empty-state-header title="Select an org" heading-level="h2" />
          <pf-empty-state-body>Select an org to continue.</pf-empty-state-body>
        </pf-empty-state>

        <div v-else-if="loading" class="loading-row">
          <pf-spinner size="md" aria-label="Loading SoW create form" />
        </div>

        <pf-empty-state v-else-if="!canManage">
          <pf-empty-state-header title="Not permitted" heading-level="h2" />
          <pf-empty-state-body>Only PM/admin can create SoWs for this org.</pf-empty-state-body>
        </pf-empty-state>

        <div v-else>
          <pf-alert v-if="error" inline variant="danger" :title="error" />

          <pf-form class="form" @submit.prevent="submit">
            <pf-form-group label="Template" field-id="sow-create-template">
              <pf-form-select
                id="sow-create-template"
                v-model="templateId"
                :disabled="templates.length === 0 || creating"
              >
                <pf-form-select-option v-for="tpl in templates" :key="tpl.id" :value="tpl.id">
                  {{ tpl.name }}
                </pf-form-select-option>
              </pf-form-select>
            </pf-form-group>

            <pf-form-group label="Variables (JSON object)" field-id="sow-create-variables">
              <pf-textarea id="sow-create-variables" v-model="variablesText" rows="8" :disabled="creating" />
            </pf-form-group>

            <pf-form-group label="Client signers">
              <pf-empty-state v-if="memberships.length === 0" variant="small">
                <pf-empty-state-header title="No client memberships found" heading-level="h3" />
                <pf-empty-state-body>No client signers are available for this org.</pf-empty-state-body>
              </pf-empty-state>
              <pf-data-list v-else compact aria-label="Client signers">
                <pf-data-list-item v-for="m in memberships" :key="m.user.id">
                  <pf-data-list-cell>
                    <pf-checkbox
                      :id="`sow-create-signer-${m.user.id}`"
                      :label="m.user.display_name || m.user.email"
                      :model-value="Boolean(selectedSignerMap[m.user.id])"
                      :disabled="creating"
                      @update:model-value="toggleSigner(m.user.id, Boolean($event))"
                    />
                  </pf-data-list-cell>
                  <pf-data-list-cell align-right>
                    <span class="muted email">{{ m.user.email }}</span>
                  </pf-data-list-cell>
                </pf-data-list-item>
              </pf-data-list>
            </pf-form-group>

            <pf-button type="submit" variant="primary" :disabled="creating">
              {{ creating ? "Creating…" : "Create draft" }}
            </pf-button>
          </pf-form>

          <pf-helper-text class="note">
            <pf-helper-text-item>
              After creating the draft, open the SoW detail page to send for signature and manage the PDF.
            </pf-helper-text-item>
          </pf-helper-text>
        </div>
      </pf-card-body>
    </pf-card>
  </div>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.detail {
  margin-top: 0.25rem;
}

.loading-row {
  display: flex;
  justify-content: center;
  padding: 0.75rem 0;
}

.form {
  margin-top: 1rem;
}

.email {
  margin-left: auto;
  font-size: 0.85rem;
}

.note {
  margin-top: 0.75rem;
}
</style>
