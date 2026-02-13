import json
import os
import stat
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from api_keys.models import ApiKey
from api_keys.services import create_api_key
from identity.models import Org, OrgMembership
from work_items.models import Project


class HealthzTests(TestCase):
    def test_healthz_is_200_when_db_is_reachable(self) -> None:
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")


class ApiCompletenessSmokeTests(TestCase):
    def _post_json(self, url: str, payload: dict, *, token: str):
        return self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def _patch_json(self, url: str, payload: dict, *, token: str):
        return self.client.patch(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def test_api_only_smoke_v1(self) -> None:
        # Bootstrap is DB-only by design; business-flow calls must use API-key auth.
        pm = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        _api_key, minted = create_api_key(
            org=org, owner_user=pm, name="Smoke key", scopes=["read", "write"], created_by_user=pm
        )
        token = minted.token

        workflow_resp = self._post_json(
            f"/api/orgs/{org.id}/workflows",
            {
                "name": "Workflow",
                "stages": [
                    {"name": "Backlog", "order": 1, "is_done": False},
                    {"name": "Done", "order": 2, "is_done": True},
                ],
            },
            token=token,
        )
        self.assertEqual(workflow_resp.status_code, 200)
        workflow_id = workflow_resp.json()["workflow"]["id"]

        project_resp = self._post_json(
            f"/api/orgs/{org.id}/projects",
            {"name": "Project", "description": "D"},
            token=token,
        )
        self.assertEqual(project_resp.status_code, 200)
        project_id = project_resp.json()["project"]["id"]

        assign_resp = self._patch_json(
            f"/api/orgs/{org.id}/projects/{project_id}",
            {"workflow_id": workflow_id},
            token=token,
        )
        self.assertEqual(assign_resp.status_code, 200)

        epic_resp = self._post_json(
            f"/api/orgs/{org.id}/projects/{project_id}/epics",
            {"title": "Epic"},
            token=token,
        )
        self.assertEqual(epic_resp.status_code, 200)
        epic_id = epic_resp.json()["epic"]["id"]

        task_resp = self._post_json(
            f"/api/orgs/{org.id}/epics/{epic_id}/tasks",
            {"title": "Task"},
            token=token,
        )
        self.assertEqual(task_resp.status_code, 200)
        task_id = task_resp.json()["task"]["id"]

        subtask_resp = self._post_json(
            f"/api/orgs/{org.id}/tasks/{task_id}/subtasks",
            {"title": "Subtask"},
            token=token,
        )
        self.assertEqual(subtask_resp.status_code, 200)

        template_resp = self._post_json(
            f"/api/orgs/{org.id}/templates",
            {"type": "report", "name": "Smoke", "body": "# Report"},
            token=token,
        )
        self.assertEqual(template_resp.status_code, 200)
        template_id = template_resp.json()["template"]["id"]

        report_resp = self._post_json(
            f"/api/orgs/{org.id}/report-runs",
            {"project_id": project_id, "template_id": template_id, "scope": {}},
            token=token,
        )
        self.assertEqual(report_resp.status_code, 200)
        report_run_id = report_resp.json()["report_run"]["id"]

        publish_resp = self._post_json(
            f"/api/orgs/{org.id}/report-runs/{report_run_id}/publish",
            {},
            token=token,
        )
        self.assertEqual(publish_resp.status_code, 200)

        events_resp = self.client.get(
            f"/api/orgs/{org.id}/projects/{project_id}/notification-events?limit=10",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(events_resp.status_code, 200)
        events_payload = events_resp.json()
        self.assertGreaterEqual(len(events_payload["events"]), 1)
        self.assertTrue(
            any(e.get("event_type") == "report.published" for e in events_payload["events"])
        )
        # Client-safe response contract: IDs + event_type + timestamp only.
        for row in events_payload["events"]:
            self.assertEqual(set(row.keys()), {"id", "event_type", "created_at"})

        # Negative: read-scope API key cannot call write endpoints.
        _read_key, read_minted = create_api_key(
            org=org, owner_user=pm, name="Read only", scopes=["read"], created_by_user=pm
        )
        forbidden = self._post_json(
            f"/api/orgs/{org.id}/projects",
            {"name": "Should fail"},
            token=read_minted.token,
        )
        self.assertEqual(forbidden.status_code, 403)

        # Negative: cross-org access is forbidden.
        other_org = Org.objects.create(name="Other Org")
        cross_org = self.client.get(
            f"/api/orgs/{other_org.id}/projects",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(cross_org.status_code, 403)


class BootstrapV1CommandTests(TestCase):
    def _run_bootstrap(self, **kwargs):
        stdout = StringIO()
        call_command(
            "bootstrap_v1",
            org_name="Org",
            pm_email="pm@example.com",
            pm_password="pw",
            project_name="Project",
            api_key_name="Bootstrap key",
            stdout=stdout,
            **kwargs,
        )
        raw = stdout.getvalue().strip()
        return raw, json.loads(raw)

    def test_bootstrap_v1_creates_and_is_idempotent(self) -> None:
        raw1, payload1 = self._run_bootstrap()
        self.assertNotIn("vrak_", raw1)
        self.assertEqual(payload1["org"]["action"], "created")
        self.assertEqual(payload1["pm_user"]["action"], "created")
        self.assertEqual(payload1["membership"]["action"], "created")
        self.assertEqual(payload1["project"]["action"], "created")
        self.assertEqual(payload1["api_key"]["action"], "created")
        self.assertNotIn("token", payload1["api_key"])
        self.assertIsNone(payload1["api_key"]["token_written_to"])

        self.assertEqual(Org.objects.count(), 1)
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(OrgMembership.objects.count(), 1)
        self.assertEqual(Project.objects.count(), 1)
        self.assertEqual(ApiKey.objects.count(), 1)

        raw2, payload2 = self._run_bootstrap()
        self.assertNotIn("vrak_", raw2)
        self.assertEqual(payload2["org"]["action"], "reused")
        self.assertEqual(payload2["pm_user"]["action"], "reused")
        self.assertIn(payload2["membership"]["action"], {"reused", "updated"})
        self.assertEqual(payload2["project"]["action"], "reused")
        self.assertEqual(payload2["api_key"]["action"], "reused")
        self.assertNotIn("token", payload2["api_key"])
        self.assertIsNone(payload2["api_key"]["token_written_to"])

        self.assertEqual(Org.objects.count(), 1)
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(OrgMembership.objects.count(), 1)
        self.assertEqual(Project.objects.count(), 1)
        self.assertEqual(ApiKey.objects.count(), 1)

    def test_bootstrap_v1_reveal_emits_token_once(self) -> None:
        raw1, payload1 = self._run_bootstrap(reveal=True)
        self.assertIn("vrak_", raw1)
        self.assertTrue(payload1["api_key"]["token"].startswith("vrak_"))

        raw2, payload2 = self._run_bootstrap(reveal=True)
        self.assertNotIn("vrak_", raw2)
        self.assertNotIn("token", payload2["api_key"])
        self.assertTrue(
            any("token not available for reused keys" in w for w in payload2.get("warnings", []))
        )

    def test_bootstrap_v1_write_token_file_writes_0600_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            token_path = os.path.join(tmp_dir, "token.json")
            raw, payload = self._run_bootstrap(write_token_file=token_path)

            self.assertNotIn("vrak_", raw)
            self.assertEqual(payload["api_key"]["token_written_to"], token_path)

            st = os.stat(token_path)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)

            with open(token_path, encoding="utf-8") as handle:
                token_payload = json.load(handle)

            self.assertTrue(token_payload["token"].startswith("vrak_"))
            self.assertEqual(token_payload["org_id"], payload["org"]["id"])
            self.assertEqual(token_payload["project_id"], payload["api_key"]["project_id"])
            self.assertEqual(token_payload["key_prefix"], payload["api_key"]["prefix"])

    def test_bootstrap_v1_write_token_file_existing_path_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            token_path = os.path.join(tmp_dir, "token.json")
            with open(token_path, "w", encoding="utf-8") as handle:
                handle.write("existing")

            stdout = StringIO()
            with self.assertRaises(CommandError):
                call_command(
                    "bootstrap_v1",
                    org_name="Org",
                    pm_email="pm@example.com",
                    pm_password="pw",
                    project_name="Project",
                    api_key_name="Bootstrap key",
                    write_token_file=token_path,
                    stdout=stdout,
                )

            self.assertEqual(Org.objects.count(), 0)
            self.assertEqual(get_user_model().objects.count(), 0)
            self.assertEqual(OrgMembership.objects.count(), 0)
            self.assertEqual(Project.objects.count(), 0)
            self.assertEqual(ApiKey.objects.count(), 0)
