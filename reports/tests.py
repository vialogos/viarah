import json
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase

from identity.models import Org, OrgMembership
from reports.pdf_rendering import sanitize_error_message, sanitize_url_for_log
from work_items.models import Epic, Project, Task, WorkItemStatus


class ReportsApiTests(TestCase):
    def _post_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.post(url, data=json.dumps(payload), content_type="application/json")

    def test_report_runs_preserve_template_version_history(self) -> None:
        pm = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        project = Project.objects.create(org=org, name="Project")
        epic = Epic.objects.create(project=project, title="Epic")
        Task.objects.create(epic=epic, title="Task 1", status=WorkItemStatus.BACKLOG)
        Task.objects.create(epic=epic, title="Task 2", status=WorkItemStatus.DONE)

        self.client.force_login(pm)

        template_resp = self._post_json(
            f"/api/orgs/{org.id}/templates",
            {
                "type": "report",
                "name": "Weekly Status",
                "body": (
                    "# Weekly Status v1\n\n"
                    "{% for task in tasks %}"
                    "- {{ task.title }} ({{ task.status }})\n"
                    "{% endfor %}"
                ),
            },
        )
        self.assertEqual(template_resp.status_code, 200)
        template_id = template_resp.json()["template"]["id"]
        v1_id = template_resp.json()["template"]["current_version_id"]

        run1 = self._post_json(
            f"/api/orgs/{org.id}/report-runs",
            {
                "project_id": str(project.id),
                "template_id": template_id,
                "scope": {},
            },
        )
        self.assertEqual(run1.status_code, 200)
        run1_payload = run1.json()["report_run"]
        run1_id = run1_payload["id"]
        self.assertEqual(run1_payload["template_version_id"], v1_id)
        self.assertIn("Weekly Status v1", run1_payload["output_markdown"])

        version_resp = self._post_json(
            f"/api/orgs/{org.id}/templates/{template_id}/versions",
            {"body": "# Weekly Status v2"},
        )
        self.assertEqual(version_resp.status_code, 200)
        v2_id = version_resp.json()["template"]["current_version_id"]
        self.assertNotEqual(v1_id, v2_id)

        run2 = self._post_json(
            f"/api/orgs/{org.id}/report-runs",
            {
                "project_id": str(project.id),
                "template_id": template_id,
                "scope": {},
            },
        )
        self.assertEqual(run2.status_code, 200)
        run2_payload = run2.json()["report_run"]
        self.assertEqual(run2_payload["template_version_id"], v2_id)
        self.assertIn("Weekly Status v2", run2_payload["output_markdown"])

        run1_again = self.client.get(f"/api/orgs/{org.id}/report-runs/{run1_id}")
        self.assertEqual(run1_again.status_code, 200)
        self.assertIn("Weekly Status v1", run1_again.json()["report_run"]["output_markdown"])
        self.assertEqual(run1_again.json()["report_run"]["template_version_id"], v1_id)

        run_list = self.client.get(f"/api/orgs/{org.id}/report-runs?project_id={project.id}")
        self.assertEqual(run_list.status_code, 200)
        self.assertEqual(len(run_list.json()["report_runs"]), 2)

    def test_report_web_view_is_sanitized_and_client_cannot_run_reports(self) -> None:
        pm = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        client_user = get_user_model().objects.create_user(
            email="client@example.com", password="pw"
        )
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)
        OrgMembership.objects.create(org=org, user=client_user, role=OrgMembership.Role.CLIENT)

        project = Project.objects.create(org=org, name="Project")
        epic = Epic.objects.create(project=project, title="Epic")
        Task.objects.create(epic=epic, title="Task 1", status=WorkItemStatus.BACKLOG)

        self.client.force_login(pm)

        template_resp = self._post_json(
            f"/api/orgs/{org.id}/templates",
            {
                "type": "report",
                "name": "Unsafe",
                "body": "<script>alert(1)</script>\\n\\n# Title",
            },
        )
        self.assertEqual(template_resp.status_code, 200)
        template_id = template_resp.json()["template"]["id"]

        run = self._post_json(
            f"/api/orgs/{org.id}/report-runs",
            {
                "project_id": str(project.id),
                "template_id": template_id,
                "scope": {},
            },
        )
        self.assertEqual(run.status_code, 200)
        run_payload = run.json()["report_run"]
        self.assertNotIn("<script", run_payload["output_html"].lower())

        web_view_url = run_payload["web_view_url"]
        web_view_path = urlparse(web_view_url).path
        web_view_resp = self.client.get(web_view_path)
        self.assertEqual(web_view_resp.status_code, 200)
        self.assertIn("text/html", web_view_resp["Content-Type"])
        self.assertNotIn(b"<script", web_view_resp.content.lower())

        client_c = self.client_class()
        client_c.force_login(client_user)
        forbidden = self._post_json(
            f"/api/orgs/{org.id}/report-runs",
            {
                "project_id": str(project.id),
                "template_id": template_id,
                "scope": {},
            },
            client=client_c,
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_regenerate_uses_current_template_version_by_default(self) -> None:
        pm = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        project = Project.objects.create(org=org, name="Project")

        self.client.force_login(pm)

        template_resp = self._post_json(
            f"/api/orgs/{org.id}/templates",
            {"type": "report", "name": "Weekly Status", "body": "# v1"},
        )
        self.assertEqual(template_resp.status_code, 200)
        template_id = template_resp.json()["template"]["id"]

        run1 = self._post_json(
            f"/api/orgs/{org.id}/report-runs",
            {
                "project_id": str(project.id),
                "template_id": template_id,
                "scope": {},
            },
        )
        self.assertEqual(run1.status_code, 200)
        run1_payload = run1.json()["report_run"]

        version_resp = self._post_json(
            f"/api/orgs/{org.id}/templates/{template_id}/versions",
            {"body": "# v2"},
        )
        self.assertEqual(version_resp.status_code, 200)

        regen = self._post_json(
            f"/api/orgs/{org.id}/report-runs/{run1_payload['id']}/regenerate",
            {},
        )
        self.assertEqual(regen.status_code, 200)
        regen_payload = regen.json()["report_run"]
        self.assertNotEqual(regen_payload["id"], run1_payload["id"])
        self.assertIn("# v2", regen_payload["output_markdown"])

    def test_report_run_pdf_endpoints_are_pm_only_and_enqueue_render(self) -> None:
        pm = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        client_user = get_user_model().objects.create_user(
            email="client@example.com", password="pw"
        )
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)
        OrgMembership.objects.create(org=org, user=client_user, role=OrgMembership.Role.CLIENT)

        project = Project.objects.create(org=org, name="Project")
        epic = Epic.objects.create(project=project, title="Epic")
        Task.objects.create(epic=epic, title="Task 1", status=WorkItemStatus.BACKLOG)

        self.client.force_login(pm)
        template_resp = self._post_json(
            f"/api/orgs/{org.id}/templates",
            {"type": "report", "name": "Weekly Status", "body": "# Title"},
        )
        self.assertEqual(template_resp.status_code, 200)
        template_id = template_resp.json()["template"]["id"]

        run = self._post_json(
            f"/api/orgs/{org.id}/report-runs",
            {
                "project_id": str(project.id),
                "template_id": template_id,
                "scope": {},
            },
        )
        self.assertEqual(run.status_code, 200)
        report_run_id = run.json()["report_run"]["id"]

        client_c = self.client_class()
        client_c.force_login(client_user)
        forbidden = client_c.post(f"/api/orgs/{org.id}/report-runs/{report_run_id}/pdf")
        self.assertEqual(forbidden.status_code, 403)

        with patch(
            "reports.views.render_report_run_pdf.delay",
            return_value=SimpleNamespace(id="celery-task-id"),
        ) as delay_mock:
            ok = self.client.post(f"/api/orgs/{org.id}/report-runs/{report_run_id}/pdf")
        self.assertEqual(ok.status_code, 202)
        delay_mock.assert_called_once()
        self.assertIn("render_log", ok.json())
        self.assertEqual(ok.json()["render_log"]["status"], "queued")

        logs_forbidden = client_c.get(f"/api/orgs/{org.id}/report-runs/{report_run_id}/render-logs")
        self.assertEqual(logs_forbidden.status_code, 403)

        logs_ok = self.client.get(f"/api/orgs/{org.id}/report-runs/{report_run_id}/render-logs")
        self.assertEqual(logs_ok.status_code, 200)
        self.assertEqual(len(logs_ok.json()["render_logs"]), 1)

        pdf_not_ready = self.client.get(f"/api/orgs/{org.id}/report-runs/{report_run_id}/pdf")
        self.assertEqual(pdf_not_ready.status_code, 409)

    def test_render_log_sanitization_strips_url_query_and_fragments(self) -> None:
        raw = "https://example.com/logo.png?token=abc123#frag"
        self.assertEqual(sanitize_url_for_log(raw), "https://example.com/logo.png")

        msg = (
            "failed to load https://example.com/img.png?secret=1#x "
            "Authorization: Bearer abc.def.ghi"
        )
        cleaned = sanitize_error_message(msg)
        self.assertNotIn("?secret=", cleaned)
        self.assertNotIn("#x", cleaned)
        self.assertNotIn("abc.def.ghi", cleaned)
