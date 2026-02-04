from __future__ import annotations

import json

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import Client, TransactionTestCase, override_settings

from identity.models import Org, OrgMembership
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
            workflow=workflow, name="Done", order=1, is_done=True
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

            event = await communicator.receive_json_from()
            self.assertEqual(event["org_id"], str(org.id))
            self.assertEqual(event["type"], "work_item.updated")
            self.assertEqual(event["data"]["task_id"], str(task.id))
            self.assertEqual(event["data"]["subtask_id"], str(subtask.id))
            self.assertEqual(event["data"]["workflow_stage_id"], str(stage_done.id))
            self.assertEqual(event["data"]["reason"], "workflow_stage_changed")

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

            event = await communicator.receive_json_from()
            self.assertEqual(event["org_id"], str(org.id))
            self.assertEqual(event["type"], "comment.created")
            self.assertEqual(event["data"]["work_item_type"], "task")
            self.assertEqual(event["data"]["work_item_id"], str(task.id))
            self.assertEqual(event["data"]["comment_id"], str(comment_id))

            await communicator.disconnect()

        async_to_sync(run)()

    def _application(self):
        from viarah.asgi import application

        return application
