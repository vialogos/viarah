<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, ApiError } from "../../api";
import type {
  Person,
  PersonAvailabilityException,
  PersonAvailabilityExceptionKind,
  PersonAvailabilityResponse,
  PersonAvailabilityWeeklyWindow,
} from "../../api/types";
import { useContextStore } from "../../stores/context";
import { useSessionStore } from "../../stores/session";
import { formatTimestampInTimeZone } from "../../utils/format";
import VlConfirmModal from "../VlConfirmModal.vue";
import VlLabel from "../VlLabel.vue";

const props = defineProps<{
  person: Person | null;
  canManage: boolean;
}>();

const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const context = useContextStore();

const tzName = computed(() => (props.person?.timezone || "UTC").trim() || "UTC");

const loading = ref(false);
const error = ref("");
const schedule = ref<PersonAvailabilityResponse | null>(null);

const createWindowError = ref("");
const creatingWindow = ref(false);
const newWeekday = ref("1");
const newStartTime = ref("09:00");
const newEndTime = ref("17:00");

const editWindowId = ref<string>("");
const editWeekday = ref("1");
const editStartTime = ref("");
const editEndTime = ref("");
const savingWindow = ref(false);

const deleteWeeklyWindowModalOpen = ref(false);
const pendingDeleteWeeklyWindow = ref<PersonAvailabilityWeeklyWindow | null>(null);
const deletingWeeklyWindow = ref(false);

const createExceptionError = ref("");
const creatingException = ref(false);
const newExceptionKind = ref<PersonAvailabilityExceptionKind>("time_off");
const newExceptionStartsAt = ref("");
const newExceptionEndsAt = ref("");
const newExceptionTitle = ref("");
const newExceptionNotes = ref("");

const deleteExceptionModalOpen = ref(false);
const pendingDeleteException = ref<PersonAvailabilityException | null>(null);
const deletingException = ref(false);

function weekdayLabel(weekday: number): string {
  const labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  return labels[weekday] ?? String(weekday);
}

function weekdayDisplayOptions() {
  return [
    { value: "0", label: "Monday" },
    { value: "1", label: "Tuesday" },
    { value: "2", label: "Wednesday" },
    { value: "3", label: "Thursday" },
    { value: "4", label: "Friday" },
    { value: "5", label: "Saturday" },
    { value: "6", label: "Sunday" },
  ];
}

async function handleUnauthorized() {
  session.clearLocal("unauthorized");
  await router.push({ path: "/login", query: { redirect: route.fullPath } });
}

async function refresh() {
  error.value = "";
  createWindowError.value = "";
  createExceptionError.value = "";

  if (!context.orgId || !props.person) {
    schedule.value = null;
    return;
  }

  loading.value = true;
  try {
    const payload = await api.getPersonAvailability(context.orgId, props.person.id);
    schedule.value = payload;
  } catch (err) {
    schedule.value = null;
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

watch(() => [context.orgId, props.person?.id], () => void refresh(), { immediate: true });

const weeklyWindows = computed(() => schedule.value?.weekly_windows ?? []);
const exceptions = computed(() => schedule.value?.exceptions ?? []);

const weeklyWindowsByWeekday = computed(() => {
  const map: Record<number, PersonAvailabilityWeeklyWindow[]> = {};
  for (const window of weeklyWindows.value) {
    const weekday = Number(window.weekday);
    if (!Number.isFinite(weekday)) {
      continue;
    }
    if (!map[weekday]) {
      map[weekday] = [];
    }
    map[weekday].push(window);
  }
  for (const key of Object.keys(map)) {
    const day = Number(key);
    const windows = map[day] ?? [];
    map[day] = windows.slice().sort((a, b) => a.start_time.localeCompare(b.start_time));
  }
  return map;
});

const weeklyGrid = computed(() => {
  return [0, 1, 2, 3, 4, 5, 6].map((weekday) => {
    const windows = weeklyWindowsByWeekday.value[weekday] ?? [];
    const label = weekdayLabel(weekday);
    return { weekday, label, windows };
  });
});

function beginEditWindow(window: PersonAvailabilityWeeklyWindow) {
  editWindowId.value = window.id;
  editWeekday.value = String(window.weekday);
  editStartTime.value = window.start_time;
  editEndTime.value = window.end_time;
}

function cancelEditWindow() {
  editWindowId.value = "";
  editStartTime.value = "";
  editEndTime.value = "";
}

async function saveEditWindow() {
  createWindowError.value = "";
  if (!context.orgId || !props.person) {
    return;
  }
  if (!editWindowId.value) {
    return;
  }

  savingWindow.value = true;
  try {
    await api.patchPersonWeeklyWindow(context.orgId, props.person.id, editWindowId.value, {
      weekday: Number(editWeekday.value),
      start_time: editStartTime.value,
      end_time: editEndTime.value,
    });

    cancelEditWindow();
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      createWindowError.value = "Not permitted.";
      return;
    }
    createWindowError.value = err instanceof Error ? err.message : String(err);
  } finally {
    savingWindow.value = false;
  }
}

async function createWindow() {
  createWindowError.value = "";
  if (!context.orgId || !props.person) {
    createWindowError.value = "Select an org first.";
    return;
  }

  const weekday = Number(newWeekday.value);
  if (!Number.isFinite(weekday) || weekday < 0 || weekday > 6) {
    createWindowError.value = "Select a weekday.";
    return;
  }

  if (!newStartTime.value.trim() || !newEndTime.value.trim()) {
    createWindowError.value = "Start and end time are required.";
    return;
  }

  creatingWindow.value = true;
  try {
    await api.createPersonWeeklyWindow(context.orgId, props.person.id, {
      weekday,
      start_time: newStartTime.value.trim(),
      end_time: newEndTime.value.trim(),
    });
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      createWindowError.value = "Not permitted.";
      return;
    }
    createWindowError.value = err instanceof Error ? err.message : String(err);
  } finally {
    creatingWindow.value = false;
  }
}

function requestDeleteWeeklyWindow(window: PersonAvailabilityWeeklyWindow) {
  pendingDeleteWeeklyWindow.value = window;
  deleteWeeklyWindowModalOpen.value = true;
}

async function deleteWeeklyWindow() {
  createWindowError.value = "";

  if (!context.orgId || !props.person) {
    createWindowError.value = "Select an org first.";
    return;
  }

  const window = pendingDeleteWeeklyWindow.value;
  if (!window) {
    createWindowError.value = "No weekly window selected.";
    return;
  }

  deletingWeeklyWindow.value = true;
  try {
    await api.deletePersonWeeklyWindow(context.orgId, props.person.id, window.id);
    deleteWeeklyWindowModalOpen.value = false;
    pendingDeleteWeeklyWindow.value = null;
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      createWindowError.value = "Not permitted.";
      return;
    }
    createWindowError.value = err instanceof Error ? err.message : String(err);
  } finally {
    deletingWeeklyWindow.value = false;
  }
}

function datetimeLocalToIso(value: string): string {
  const raw = (value || "").trim();
  if (!raw) {
    return "";
  }
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  return parsed.toISOString();
}

async function createException() {
  createExceptionError.value = "";
  if (!context.orgId || !props.person) {
    createExceptionError.value = "Select an org first.";
    return;
  }

  const startsAtIso = datetimeLocalToIso(newExceptionStartsAt.value);
  const endsAtIso = datetimeLocalToIso(newExceptionEndsAt.value);
  if (!startsAtIso) {
    createExceptionError.value = "Start time is required.";
    return;
  }
  if (!endsAtIso) {
    createExceptionError.value = "End time is required.";
    return;
  }

  creatingException.value = true;
  try {
    await api.createPersonAvailabilityException(context.orgId, props.person.id, {
      kind: newExceptionKind.value,
      starts_at: startsAtIso,
      ends_at: endsAtIso,
      title: newExceptionTitle.value.trim() ? newExceptionTitle.value.trim() : undefined,
      notes: newExceptionNotes.value.trim() ? newExceptionNotes.value.trim() : undefined,
    });

    newExceptionTitle.value = "";
    newExceptionNotes.value = "";
    newExceptionStartsAt.value = "";
    newExceptionEndsAt.value = "";

    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      createExceptionError.value = "Not permitted.";
      return;
    }
    createExceptionError.value = err instanceof Error ? err.message : String(err);
  } finally {
    creatingException.value = false;
  }
}

function requestDeleteException(exc: PersonAvailabilityException) {
  pendingDeleteException.value = exc;
  deleteExceptionModalOpen.value = true;
}

async function deleteException() {
  createExceptionError.value = "";
  if (!context.orgId || !props.person) {
    createExceptionError.value = "Select an org first.";
    return;
  }

  const exc = pendingDeleteException.value;
  if (!exc) {
    createExceptionError.value = "No exception selected.";
    return;
  }

  deletingException.value = true;
  try {
    await api.deletePersonAvailabilityException(context.orgId, props.person.id, exc.id);
    deleteExceptionModalOpen.value = false;
    pendingDeleteException.value = null;
    await refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await handleUnauthorized();
      return;
    }
    if (err instanceof ApiError && err.status === 403) {
      createExceptionError.value = "Not permitted.";
      return;
    }
    createExceptionError.value = err instanceof Error ? err.message : String(err);
  } finally {
    deletingException.value = false;
  }
}

const minutesAvailable = computed(() => schedule.value?.summary?.minutes_available ?? 0);
const hoursAvailableLabel = computed(() => {
  const minutes = minutesAvailable.value;
  const hours = Math.round((minutes / 60) * 10) / 10;
  return `${hours}h`;
});
</script>

<template>
  <div class="tab-stack">
    <pf-alert v-if="error" inline variant="danger" :title="error" />

    <pf-card>
      <pf-card-title>
        <div class="header">
          <div>
            <pf-title h="3" size="lg">Availability schedule</pf-title>
            <pf-content>
              <p class="muted">
                Weekly windows + exceptions/time off, interpreted in <strong>{{ tzName }}</strong>.
              </p>
            </pf-content>
          </div>
          <pf-button variant="secondary" :disabled="loading" @click="refresh">Refresh</pf-button>
        </div>
      </pf-card-title>

      <pf-card-body>
        <div v-if="loading" class="inline-loading">
          <pf-spinner size="sm" aria-label="Loading availability" />
          <span class="muted">Loading schedule…</span>
        </div>

        <pf-empty-state v-else-if="!schedule">
          <pf-empty-state-header title="No schedule loaded" heading-level="h3" />
          <pf-empty-state-body>
            Select a person to view and edit their availability schedule.
          </pf-empty-state-body>
        </pf-empty-state>

        <div v-else class="stack">
          <pf-card class="summary-card">
            <pf-card-title>Summary (next 14 days)</pf-card-title>
            <pf-card-body>
              <div class="summary-grid">
                <div>
                  <div class="muted small">Has availability</div>
                  <div class="summary-value">{{ schedule.summary.has_availability ? "Yes" : "No" }}</div>
                </div>
                <div>
                  <div class="muted small">Next available</div>
                  <div class="summary-value">
                    {{
                      schedule.summary.next_available_at
                        ? formatTimestampInTimeZone(schedule.summary.next_available_at, tzName)
                        : "—"
                    }}
                  </div>
                </div>
                <div>
                  <div class="muted small">Total available</div>
                  <div class="summary-value">{{ hoursAvailableLabel }}</div>
                </div>
              </div>
            </pf-card-body>
          </pf-card>

          <pf-card>
            <pf-card-title>Week at a glance</pf-card-title>
            <pf-card-body>
              <pf-table aria-label="Weekly schedule">
                <pf-thead>
                  <pf-tr>
                    <pf-th v-for="col in weeklyGrid" :key="col.weekday">{{ col.label }}</pf-th>
                  </pf-tr>
                </pf-thead>
                <pf-tbody>
                  <pf-tr>
                    <pf-td v-for="col in weeklyGrid" :key="col.weekday" :data-label="col.label">
                      <div class="cell-stack">
                        <span v-if="!col.windows.length" class="muted">—</span>
                        <VlLabel v-for="win in col.windows" :key="win.id" color="blue" variant="outline">
                          {{ win.start_time }}–{{ win.end_time }}
                        </VlLabel>
                      </div>
                    </pf-td>
                  </pf-tr>
                </pf-tbody>
              </pf-table>
            </pf-card-body>
          </pf-card>

          <pf-card>
            <pf-card-title>Create weekly window</pf-card-title>
            <pf-card-body>
              <pf-alert v-if="createWindowError" inline variant="danger" :title="createWindowError" />

              <pf-form class="form-grid" @submit.prevent="createWindow">
                <pf-form-group label="Weekday" field-id="availability-weekday">
                  <pf-form-select id="availability-weekday" v-model="newWeekday">
                    <pf-form-select-option v-for="opt in weekdayDisplayOptions()" :key="opt.value" :value="opt.value">
                      {{ opt.label }}
                    </pf-form-select-option>
                  </pf-form-select>
                </pf-form-group>

                <pf-form-group label="Start" field-id="availability-start">
                  <pf-text-input id="availability-start" v-model="newStartTime" type="time" />
                </pf-form-group>

                <pf-form-group label="End" field-id="availability-end">
                  <pf-text-input id="availability-end" v-model="newEndTime" type="time" />
                </pf-form-group>

                <div class="actions">
                  <pf-button type="submit" :disabled="creatingWindow || !props.canManage">
                    {{ creatingWindow ? "Creating…" : "Add window" }}
                  </pf-button>
                </div>
              </pf-form>

              <pf-helper-text>
                <pf-helper-text-item>
                  Times are interpreted in the person’s timezone. Create multiple windows per day if needed.
                </pf-helper-text-item>
              </pf-helper-text>
            </pf-card-body>
          </pf-card>

          <pf-card>
            <pf-card-title>Weekly windows</pf-card-title>
            <pf-card-body>
              <pf-empty-state v-if="!weeklyWindows.length">
                <pf-empty-state-header title="No weekly windows" heading-level="h3" />
                <pf-empty-state-body>
                  Add weekly windows to model typical working hours.
                </pf-empty-state-body>
              </pf-empty-state>

              <pf-table v-else aria-label="Weekly windows">
                <pf-thead>
                  <pf-tr>
                    <pf-th>Weekday</pf-th>
                    <pf-th>Start</pf-th>
                    <pf-th>End</pf-th>
                    <pf-th align-right>Actions</pf-th>
                  </pf-tr>
                </pf-thead>
                <pf-tbody>
                  <pf-tr v-for="win in weeklyWindows" :key="win.id">
                    <pf-td data-label="Weekday">{{ weekdayLabel(Number(win.weekday)) }}</pf-td>
                    <pf-td data-label="Start">{{ win.start_time }}</pf-td>
                    <pf-td data-label="End">{{ win.end_time }}</pf-td>
                    <pf-td data-label="Actions" align-right>
                      <pf-button variant="secondary" small :disabled="!props.canManage" @click="beginEditWindow(win)">
                        Edit
                      </pf-button>
                      <pf-button variant="danger" small :disabled="!props.canManage" @click="requestDeleteWeeklyWindow(win)">
                        Delete
                      </pf-button>
                    </pf-td>
                  </pf-tr>
                </pf-tbody>
              </pf-table>

              <pf-card v-if="editWindowId" class="edit-card">
                <pf-card-title>Edit window</pf-card-title>
                <pf-card-body>
                  <pf-form class="form-grid" @submit.prevent="saveEditWindow">
                    <pf-form-group label="Weekday" field-id="availability-edit-weekday">
                      <pf-form-select id="availability-edit-weekday" v-model="editWeekday">
                        <pf-form-select-option v-for="opt in weekdayDisplayOptions()" :key="opt.value" :value="opt.value">
                          {{ opt.label }}
                        </pf-form-select-option>
                      </pf-form-select>
                    </pf-form-group>

                    <pf-form-group label="Start" field-id="availability-edit-start">
                      <pf-text-input id="availability-edit-start" v-model="editStartTime" type="time" />
                    </pf-form-group>

                    <pf-form-group label="End" field-id="availability-edit-end">
                      <pf-text-input id="availability-edit-end" v-model="editEndTime" type="time" />
                    </pf-form-group>

                    <div class="actions">
                      <pf-button type="submit" :disabled="savingWindow || !props.canManage">
                        {{ savingWindow ? "Saving…" : "Save" }}
                      </pf-button>
                      <pf-button type="button" variant="link" :disabled="savingWindow" @click="cancelEditWindow">
                        Cancel
                      </pf-button>
                    </div>
                  </pf-form>
                </pf-card-body>
              </pf-card>
            </pf-card-body>
          </pf-card>

          <pf-card>
            <pf-card-title>Create exception / time off</pf-card-title>
            <pf-card-body>
              <pf-alert v-if="createExceptionError" inline variant="danger" :title="createExceptionError" />

              <pf-form class="exception-form" @submit.prevent="createException">
                <pf-form-group label="Kind" field-id="exception-kind">
                  <pf-form-select id="exception-kind" v-model="newExceptionKind">
                    <pf-form-select-option value="time_off">Time off</pf-form-select-option>
                    <pf-form-select-option value="available">Extra availability</pf-form-select-option>
                  </pf-form-select>
                </pf-form-group>

                <div class="exception-grid">
                  <pf-form-group label="Start" field-id="exception-start">
                    <pf-text-input id="exception-start" v-model="newExceptionStartsAt" type="datetime-local" />
                  </pf-form-group>

                  <pf-form-group label="End" field-id="exception-end">
                    <pf-text-input id="exception-end" v-model="newExceptionEndsAt" type="datetime-local" />
                  </pf-form-group>
                </div>

                <pf-form-group label="Title" field-id="exception-title">
                  <pf-text-input id="exception-title" v-model="newExceptionTitle" type="text" placeholder="e.g., Vacation" />
                </pf-form-group>

                <pf-form-group label="Notes" field-id="exception-notes">
                  <pf-textarea id="exception-notes" v-model="newExceptionNotes" rows="2" />
                </pf-form-group>

                <pf-button type="submit" :disabled="creatingException || !props.canManage">
                  {{ creatingException ? "Creating…" : "Add exception" }}
                </pf-button>

                <pf-helper-text>
                  <pf-helper-text-item>
                    Exceptions are absolute date/time ranges; they’ll display in {{ tzName }}.
                  </pf-helper-text-item>
                </pf-helper-text>
              </pf-form>
            </pf-card-body>
          </pf-card>

          <pf-card>
            <pf-card-title>Exceptions</pf-card-title>
            <pf-card-body>
              <pf-empty-state v-if="!exceptions.length">
                <pf-empty-state-header title="No exceptions" heading-level="h3" />
                <pf-empty-state-body>
                  Add time off or extra availability for specific dates.
                </pf-empty-state-body>
              </pf-empty-state>

              <pf-table v-else aria-label="Availability exceptions">
                <pf-thead>
                  <pf-tr>
                    <pf-th>Kind</pf-th>
                    <pf-th>Start</pf-th>
                    <pf-th>End</pf-th>
                    <pf-th>Title</pf-th>
                    <pf-th>Notes</pf-th>
                    <pf-th align-right>Actions</pf-th>
                  </pf-tr>
                </pf-thead>
                <pf-tbody>
                  <pf-tr v-for="exc in exceptions" :key="exc.id">
                    <pf-td data-label="Kind">
                      {{ exc.kind === "time_off" ? "Time off" : "Available" }}
                    </pf-td>
                    <pf-td data-label="Start">{{ formatTimestampInTimeZone(exc.starts_at, tzName) }}</pf-td>
                    <pf-td data-label="End">{{ formatTimestampInTimeZone(exc.ends_at, tzName) }}</pf-td>
                    <pf-td data-label="Title">{{ exc.title || "—" }}</pf-td>
                    <pf-td data-label="Notes">{{ exc.notes || "—" }}</pf-td>
                    <pf-td data-label="Actions" align-right>
                      <pf-button variant="danger" small :disabled="!props.canManage" @click="requestDeleteException(exc)">
                        Delete
                      </pf-button>
                    </pf-td>
                  </pf-tr>
                </pf-tbody>
              </pf-table>
            </pf-card-body>
          </pf-card>

          <pf-alert
            v-if="props.person && !props.person.user"
            inline
            variant="info"
            title="Invite acceptance required for member self-serve"
          >
            Candidates can have schedules for planning, but only active members can self-manage availability.
          </pf-alert>
        </div>
      </pf-card-body>
    </pf-card>

    <VlConfirmModal
      v-model:open="deleteWeeklyWindowModalOpen"
      title="Delete weekly window?"
      body="This removes the recurring weekly window from the schedule."
      confirm-label="Delete"
      confirm-variant="danger"
      :loading="deletingWeeklyWindow"
      @confirm="deleteWeeklyWindow"
    />

    <VlConfirmModal
      v-model:open="deleteExceptionModalOpen"
      title="Delete exception?"
      body="This removes the exception/time off entry."
      confirm-label="Delete"
      confirm-variant="danger"
      :loading="deletingException"
      @confirm="deleteException"
    />
  </div>
</template>

<style scoped>
.tab-stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.inline-loading {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}

.stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
}

.summary-value {
  font-weight: 600;
}

.small {
  font-size: 0.875rem;
}

.muted {
  color: var(--pf-t--global--text--color--subtle);
}

.cell-stack {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
  align-items: end;
}

.actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.edit-card {
  margin-top: 0.75rem;
}

.exception-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.exception-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

@media (max-width: 900px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .exception-grid {
    grid-template-columns: 1fr;
  }
}
</style>
