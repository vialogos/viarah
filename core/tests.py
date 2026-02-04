import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from api_keys.services import create_api_key
from identity.models import Org, OrgMembership


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
            org=org, name="Smoke key", scopes=["read", "write"], created_by_user=pm
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
            org=org, name="Read only", scopes=["read"], created_by_user=pm
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
