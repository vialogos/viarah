from __future__ import annotations

import json
from unittest import mock

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import Client, TransactionTestCase, override_settings

from identity.models import Org, OrgMembership
from integrations.models import OrgGitLabIntegration
from work_items.models import Epic, Project, Subtask, Task
from workflows.models import Workflow, WorkflowStage


@override_settings(
    ALLOWED_HOSTS=["localhost", "testserver"],
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
)
class RealtimeWebsocketTests(TransactionTestCase):
    def _make_client_for(self, user) -> Client:
        client = Client()
        client.force_login(user)
        return client

    def _headers_for_client(self, client: Client):
        session_cookie = client.cookies.get("sessionid")
        if session_cookie is None:
            raise AssertionError("expected sessionid cookie to be set")

        cookie = f"sessionid={session_cookie.value}"
        return [
            (b"origin", b"http://localhost"),
            (b"cookie", cookie.encode("utf-8")),
        ]

    async def _recv_event_of_type(
        self,
        communicator: WebsocketCommunicator,
        *,
        expected_type: str,
        max_events: int = 5,
    ) -> dict:
        for _ in range(max_events):
            event = await communicator.receive_json_from()
            if event.get("type") == expected_type:
                return event
        raise AssertionError(f"did not receive expected event type: {expected_type}")

    def test_websocket_requires_authenticated_org_member(self) -> None:
        org = Org.objects.create(name="Org")

        pm = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)
        client = self._make_client_for(pm)

        client_user = get_user_model().objects.create_user(
            email="client@example.com", password="pw"
        )
        OrgMembership.objects.create(org=org, user=client_user, role=OrgMembership.Role.CLIENT)
        client_client = self._make_client_for(client_user)

        async def run() -> None:
            communicator = WebsocketCommunicator(
                self._application(),
                f"/ws/orgs/{org.id}/events",
                headers=[(b"origin", b"http://localhost")],
            )
            connected, _ = await communicator.connect()
            self.assertFalse(connected)
            communicator.stop(exceptions=False)

            communicator = WebsocketCommunicator(
                self._application(),
                f"/ws/orgs/{org.id}/events",
                headers=self._headers_for_client(client),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.disconnect()

            communicator = WebsocketCommunicator(
                self._application(),
                f"/ws/orgs/{org.id}/events",
                headers=self._headers_for_client(client_client),
            )
            connected, _ = await communicator.connect()
            self.assertFalse(connected)
            communicator.stop(exceptions=False)

        async_to_sync(run)()

    def test_stage_update_emits_work_item_updated_event(self) -> None:
        pm = get_user_model().objects.create_user(email="pm2@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        workflow = Workflow.objects.create(org=org, name="Workflow", created_by_user=pm)
        stage_done = WorkflowStage.objects.create(
            workflow=workflow,
            name="Done",
            order=1,
            is_done=True,
            category="done",
            progress_percent=100,
        )
        project = Project.objects.create(org=org, name="Project", workflow=workflow)
        epic = Epic.objects.create(project=project, title="Epic")
        task = Task.objects.create(epic=epic, title="Task")
        subtask = Subtask.objects.create(task=task, title="Subtask")

        client = self._make_client_for(pm)

        async def run() -> None:
            communicator = WebsocketCommunicator(
                self._application(),
                f"/ws/orgs/{org.id}/events",
                headers=self._headers_for_client(client),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            resp = await database_sync_to_async(client.patch)(
                f"/api/orgs/{org.id}/subtasks/{subtask.id}",
                data=json.dumps({"workflow_stage_id": str(stage_done.id)}),
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 200)

            event = await self._recv_event_of_type(communicator, expected_type="work_item.updated")
            self.assertEqual(event["org_id"], str(org.id))
            self.assertEqual(event["type"], "work_item.updated")
            self.assertEqual(event["data"]["task_id"], str(task.id))
            self.assertEqual(event["data"]["subtask_id"], str(subtask.id))
            self.assertEqual(event["data"]["workflow_stage_id"], str(stage_done.id))
            self.assertEqual(event["data"]["reason"], "workflow_stage_changed")

            await communicator.disconnect()

        async_to_sync(run)()

    def test_task_stage_update_emits_work_item_updated_event(self) -> None:
        pm = get_user_model().objects.create_user(email="pm-task-stage@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        workflow = Workflow.objects.create(org=org, name="Workflow", created_by_user=pm)
        stage_backlog = WorkflowStage.objects.create(
            workflow=workflow,
            name="Backlog",
            order=1,
            is_done=False,
            category="backlog",
            progress_percent=0,
        )
        WorkflowStage.objects.create(
            workflow=workflow,
            name="Done",
            order=2,
            is_done=True,
            category="done",
            progress_percent=100,
        )
        project = Project.objects.create(org=org, name="Project", workflow=workflow)
        epic = Epic.objects.create(project=project, title="Epic")
        task = Task.objects.create(epic=epic, title="Task")

        client = self._make_client_for(pm)

        async def run() -> None:
            communicator = WebsocketCommunicator(
                self._application(),
                f"/ws/orgs/{org.id}/events",
                headers=self._headers_for_client(client),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            resp = await database_sync_to_async(client.patch)(
                f"/api/orgs/{org.id}/tasks/{task.id}",
                data=json.dumps({"workflow_stage_id": str(stage_backlog.id)}),
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 200)

            event = await self._recv_event_of_type(communicator, expected_type="work_item.updated")
            self.assertEqual(event["org_id"], str(org.id))
            self.assertEqual(event["type"], "work_item.updated")
            self.assertEqual(event["data"]["task_id"], str(task.id))
            self.assertEqual(event["data"]["workflow_stage_id"], str(stage_backlog.id))
            self.assertEqual(event["data"]["reason"], "workflow_stage_changed")
            self.assertNotIn("subtask_id", event["data"])

            await communicator.disconnect()

        async_to_sync(run)()

    def test_comment_create_emits_comment_created_event(self) -> None:
        pm = get_user_model().objects.create_user(email="pm3@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        workflow = Workflow.objects.create(org=org, name="Workflow", created_by_user=pm)
        project = Project.objects.create(org=org, name="Project", workflow=workflow)
        epic = Epic.objects.create(project=project, title="Epic")
        task = Task.objects.create(epic=epic, title="Task")

        client = self._make_client_for(pm)

        async def run() -> None:
            communicator = WebsocketCommunicator(
                self._application(),
                f"/ws/orgs/{org.id}/events",
                headers=self._headers_for_client(client),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            resp = await database_sync_to_async(client.post)(
                f"/api/orgs/{org.id}/tasks/{task.id}/comments",
                data=json.dumps({"body_markdown": "hello"}),
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 201)
            comment_id = resp.json()["comment"]["id"]

            event = await self._recv_event_of_type(communicator, expected_type="comment.created")
            self.assertEqual(event["org_id"], str(org.id))
            self.assertEqual(event["type"], "comment.created")
            self.assertEqual(event["data"]["work_item_type"], "task")
            self.assertEqual(event["data"]["work_item_id"], str(task.id))
            self.assertEqual(event["data"]["comment_id"], str(comment_id))

            await communicator.disconnect()

        async_to_sync(run)()

    def test_report_run_pdf_request_emits_pdf_render_log_updated_event(self) -> None:
        from types import SimpleNamespace

        pm = get_user_model().objects.create_user(email="pm-report@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        project = Project.objects.create(org=org, name="Project")
        epic = Epic.objects.create(project=project, title="Epic")
        Task.objects.create(epic=epic, title="Task 1")

        client = self._make_client_for(pm)

        async def run() -> None:
            communicator = WebsocketCommunicator(
                self._application(),
                f"/ws/orgs/{org.id}/events",
                headers=self._headers_for_client(client),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            template_resp = await database_sync_to_async(client.post)(
                f"/api/orgs/{org.id}/templates",
                data=json.dumps({"type": "report", "name": "Weekly Status", "body": "# Title"}),
                content_type="application/json",
            )
            self.assertEqual(template_resp.status_code, 200)
            template_id = template_resp.json()["template"]["id"]

            run_resp = await database_sync_to_async(client.post)(
                f"/api/orgs/{org.id}/report-runs",
                data=json.dumps(
                    {
                        "project_id": str(project.id),
                        "template_id": template_id,
                        "scope": {},
                    }
                ),
                content_type="application/json",
            )
            self.assertEqual(run_resp.status_code, 200)
            report_run_id = run_resp.json()["report_run"]["id"]

            with mock.patch(
                "reports.views.render_report_run_pdf.delay",
                return_value=SimpleNamespace(id="celery-task-id"),
            ):
                pdf_resp = await database_sync_to_async(client.post)(
                    f"/api/orgs/{org.id}/report-runs/{report_run_id}/pdf"
                )
            self.assertEqual(pdf_resp.status_code, 202)

            event = await self._recv_event_of_type(
                communicator,
                expected_type="report_run.pdf_render_log.updated",
            )
            self.assertEqual(event["org_id"], str(org.id))
            self.assertEqual(event["type"], "report_run.pdf_render_log.updated")
            self.assertEqual(event["data"]["report_run_id"], report_run_id)

            await communicator.disconnect()

        async_to_sync(run)()

    def test_gitlab_link_create_emits_gitlab_link_updated_event(self) -> None:
        pm = get_user_model().objects.create_user(email="pm-gitlab-link@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        workflow = Workflow.objects.create(org=org, name="Workflow", created_by_user=pm)
        project = Project.objects.create(org=org, name="Project", workflow=workflow)
        epic = Epic.objects.create(project=project, title="Epic")
        task = Task.objects.create(epic=epic, title="Task")

        OrgGitLabIntegration.objects.create(org=org, base_url="https://gitlab.com")
        client = self._make_client_for(pm)

        async def run() -> None:
            communicator = WebsocketCommunicator(
                self._application(),
                f"/ws/orgs/{org.id}/events",
                headers=self._headers_for_client(client),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            with mock.patch("integrations.views.refresh_gitlab_link_metadata.delay") as delay:
                resp = await database_sync_to_async(client.post)(
                    f"/api/orgs/{org.id}/tasks/{task.id}/gitlab-links",
                    data=json.dumps({"url": "https://gitlab.com/group/proj/-/issues/12"}),
                    content_type="application/json",
                )
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(delay.called)

            payload = resp.json()["link"]
            event = await self._recv_event_of_type(
                communicator,
                expected_type="gitlab_link.updated",
            )
            self.assertEqual(event["org_id"], str(org.id))
            self.assertEqual(event["type"], "gitlab_link.updated")
            self.assertEqual(event["data"]["task_id"], str(task.id))
            self.assertEqual(event["data"]["link_id"], str(payload["id"]))
            self.assertEqual(event["data"]["reason"], "created")

            await communicator.disconnect()

        async_to_sync(run)()

    def _application(self):
        from viarah.asgi import application

        return application
