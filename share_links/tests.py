import json
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase

from audit.models import AuditEvent
from identity.models import Org, OrgMembership
from work_items.models import Epic, Project, Subtask, Task, WorkItemStatus


class ShareLinksApiTests(TestCase):
    def _post_json(self, url: str, payload: dict, *, client=None, **extra):
        active_client = client or self.client
        return active_client.post(
            url, data=json.dumps(payload), content_type="application/json", **extra
        )

    def test_publish_public_view_logs_and_revoke(self) -> None:
        pm = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        project = Project.objects.create(org=org, name="Project")
        epic = Epic.objects.create(project=project, title="Epic")

        safe_task = Task.objects.create(
            epic=epic,
            title="Safe task",
            description="SAFE_TASK_DESCRIPTION",
            status=WorkItemStatus.BACKLOG,
            client_safe=True,
        )
        Task.objects.create(
            epic=epic,
            title="Internal task",
            description="INTERNAL_TASK_DESCRIPTION",
            status=WorkItemStatus.BACKLOG,
            client_safe=False,
        )
        Subtask.objects.create(
            task=safe_task,
            title="Safe subtask",
            description="SAFE_SUBTASK_DESCRIPTION",
            status=WorkItemStatus.BACKLOG,
        )

        self.client.force_login(pm)

        template_resp = self._post_json(
            f"/api/orgs/{org.id}/templates",
            {
                "type": "report",
                "name": "Public share test",
                "body": (
                    "# Report\\n\\n"
                    "{% for task in tasks %}"
                    "- {{ task.title }} | {{ task.description }}\\n"
                    "{% endfor %}\\n"
                    "{% for subtask in subtasks %}"
                    "- {{ subtask.title }} | {{ subtask.description }}\\n"
                    "{% endfor %}"
                ),
            },
        )
        self.assertEqual(template_resp.status_code, 200)
        template_id = template_resp.json()["template"]["id"]

        run_resp = self._post_json(
            f"/api/orgs/{org.id}/report-runs",
            {
                "project_id": str(project.id),
                "template_id": template_id,
                "scope": {},
            },
        )
        self.assertEqual(run_resp.status_code, 200)
        report_run_id = run_resp.json()["report_run"]["id"]
        internal_md = run_resp.json()["report_run"]["output_markdown"]
        self.assertIn("SAFE_TASK_DESCRIPTION", internal_md)
        self.assertIn("INTERNAL_TASK_DESCRIPTION", internal_md)
        self.assertIn("SAFE_SUBTASK_DESCRIPTION", internal_md)

        publish_resp = self._post_json(
            f"/api/orgs/{org.id}/report-runs/{report_run_id}/publish",
            {},
        )
        self.assertEqual(publish_resp.status_code, 200)
        publish_payload = publish_resp.json()
        share_link_id = publish_payload["share_link"]["id"]
        share_url = publish_payload["share_url"]
        share_path = urlparse(share_url).path

        anon = self.client_class()
        public_resp = anon.get(
            share_path,
            HTTP_USER_AGENT="TestUA",
            REMOTE_ADDR="1.2.3.4",
        )
        self.assertEqual(public_resp.status_code, 200)
        self.assertIn("text/html", public_resp["Content-Type"])
        content = public_resp.content.decode("utf-8")
        self.assertIn("Safe task", content)
        self.assertNotIn("Internal task", content)
        self.assertNotIn("SAFE_TASK_DESCRIPTION", content)
        self.assertNotIn("INTERNAL_TASK_DESCRIPTION", content)
        self.assertNotIn("SAFE_SUBTASK_DESCRIPTION", content)

        logs_resp = self.client.get(f"/api/orgs/{org.id}/share-links/{share_link_id}/access-logs")
        self.assertEqual(logs_resp.status_code, 200)
        logs_payload = logs_resp.json()
        self.assertGreaterEqual(len(logs_payload["access_logs"]), 1)
        self.assertEqual(logs_payload["access_logs"][0]["ip_address"], "1.2.3.4")
        self.assertEqual(logs_payload["access_logs"][0]["user_agent"], "TestUA")

        publish_event = AuditEvent.objects.filter(
            org=org, event_type="report_share_link.published"
        ).first()
        self.assertIsNotNone(publish_event)

        revoke_resp = self._post_json(
            f"/api/orgs/{org.id}/share-links/{share_link_id}/revoke",
            {},
        )
        self.assertEqual(revoke_resp.status_code, 200)

        revoked_event = AuditEvent.objects.filter(
            org=org, event_type="report_share_link.revoked"
        ).first()
        self.assertIsNotNone(revoked_event)

        after_revoke = anon.get(share_path)
        self.assertEqual(after_revoke.status_code, 404)

    def test_api_key_scope_enforced_for_publish(self) -> None:
        pm = get_user_model().objects.create_user(email="pm2@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        project = Project.objects.create(org=org, name="Project")
        epic = Epic.objects.create(project=project, title="Epic")
        Task.objects.create(
            epic=epic,
            title="Safe task",
            description="SAFE_TASK_DESCRIPTION",
            status=WorkItemStatus.BACKLOG,
            client_safe=True,
        )

        self.client.force_login(pm)

        template_resp = self._post_json(
            f"/api/orgs/{org.id}/templates",
            {
                "type": "report",
                "name": "API key publish test",
                "body": "# Report",
            },
        )
        self.assertEqual(template_resp.status_code, 200)
        template_id = template_resp.json()["template"]["id"]

        run_resp = self._post_json(
            f"/api/orgs/{org.id}/report-runs",
            {"project_id": str(project.id), "template_id": template_id, "scope": {}},
        )
        self.assertEqual(run_resp.status_code, 200)
        report_run_id = run_resp.json()["report_run"]["id"]

        read_key = self._post_json(
            "/api/api-keys",
            {"org_id": str(org.id), "name": "Read key", "scopes": ["read"]},
        )
        self.assertEqual(read_key.status_code, 200)
        read_token = read_key.json()["token"]

        publish_forbidden = self._post_json(
            f"/api/orgs/{org.id}/report-runs/{report_run_id}/publish",
            {},
            HTTP_AUTHORIZATION=f"Bearer {read_token}",
        )
        self.assertEqual(publish_forbidden.status_code, 403)

        write_key = self._post_json(
            "/api/api-keys",
            {"org_id": str(org.id), "name": "Write key", "scopes": ["write"]},
        )
        self.assertEqual(write_key.status_code, 200)
        write_token = write_key.json()["token"]

        publish_ok = self._post_json(
            f"/api/orgs/{org.id}/report-runs/{report_run_id}/publish",
            {},
            HTTP_AUTHORIZATION=f"Bearer {write_token}",
        )
        self.assertEqual(publish_ok.status_code, 200)
        share_link_id = publish_ok.json()["share_link"]["id"]

        list_resp = self.client.get(
            f"/api/orgs/{org.id}/share-links?report_run_id={report_run_id}",
            HTTP_AUTHORIZATION=f"Bearer {read_token}",
        )
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(len(list_resp.json()["share_links"]), 1)
        self.assertEqual(list_resp.json()["share_links"][0]["id"], share_link_id)
