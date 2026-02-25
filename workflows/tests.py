import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from audit.models import AuditEvent
from identity.models import Org, OrgMembership
from work_items.models import Epic, Project, Subtask, Task

from .models import Workflow, WorkflowStage


class WorkflowsApiTests(TestCase):
    def _post_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.post(url, data=json.dumps(payload), content_type="application/json")

    def _patch_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.patch(url, data=json.dumps(payload), content_type="application/json")

    def test_workflow_create_requires_exactly_one_done_stage(self) -> None:
        pm = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)
        self.client.force_login(pm)

        resp = self._post_json(
            f"/api/orgs/{org.id}/workflows",
            {
                "name": "W",
                "stages": [
                    {
                        "name": "A",
                        "order": 1,
                        "is_done": False,
                        "category": "backlog",
                        "progress_percent": 0,
                    },
                    {
                        "name": "B",
                        "order": 2,
                        "is_done": False,
                        "category": "in_progress",
                        "progress_percent": 50,
                    },
                ],
            },
        )
        self.assertEqual(resp.status_code, 400)

        resp = self._post_json(
            f"/api/orgs/{org.id}/workflows",
            {
                "name": "W",
                "stages": [
                    {
                        "name": "A",
                        "order": 1,
                        "is_done": True,
                        "category": "done",
                        "progress_percent": 100,
                    },
                    {
                        "name": "B",
                        "order": 2,
                        "is_done": True,
                        "category": "done",
                        "progress_percent": 100,
                    },
                ],
            },
        )
        self.assertEqual(resp.status_code, 400)

        resp = self._post_json(
            f"/api/orgs/{org.id}/workflows",
            {
                "name": "W",
                "stages": [
                    {
                        "name": "A",
                        "order": 1,
                        "is_done": False,
                        "category": "backlog",
                        "progress_percent": 0,
                    },
                    {
                        "name": "B",
                        "order": 2,
                        "is_done": True,
                        "category": "done",
                        "progress_percent": 100,
                    },
                ],
            },
        )
        self.assertEqual(resp.status_code, 200)

    def test_stage_reorder_normalizes_orders(self) -> None:
        pm = get_user_model().objects.create_user(email="pm2@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)
        self.client.force_login(pm)

        workflow = Workflow.objects.create(org=org, name="W", created_by_user=pm)
        a = WorkflowStage.objects.create(
            workflow=workflow,
            name="A",
            order=1,
            is_done=True,
            category="done",
            progress_percent=100,
        )
        b = WorkflowStage.objects.create(workflow=workflow, name="B", order=2)
        c = WorkflowStage.objects.create(workflow=workflow, name="C", order=3)

        resp = self._patch_json(
            f"/api/orgs/{org.id}/workflows/{workflow.id}/stages/{c.id}",
            {"order": 1},
        )
        self.assertEqual(resp.status_code, 200)
        stages = resp.json()["stages"]
        self.assertEqual([s["name"] for s in stages], ["C", "A", "B"])
        self.assertEqual([s["order"] for s in stages], [1, 2, 3])
        self.assertTrue(stages[1]["is_done"])

        a.refresh_from_db()
        b.refresh_from_db()
        c.refresh_from_db()
        self.assertEqual((c.order, a.order, b.order), (1, 2, 3))

    def test_project_workflow_assignment_enforces_org_match(self) -> None:
        pm = get_user_model().objects.create_user(email="pm3@example.com", password="pw")
        org_a = Org.objects.create(name="Org A")
        org_b = Org.objects.create(name="Org B")
        OrgMembership.objects.create(org=org_a, user=pm, role=OrgMembership.Role.PM)

        project = Project.objects.create(org=org_a, name="Project")
        workflow_b = Workflow.objects.create(
            org=org_b, name="Other org workflow", created_by_user=pm
        )

        self.client.force_login(pm)

        resp = self._patch_json(
            f"/api/orgs/{org_a.id}/projects/{project.id}",
            {"workflow_id": str(workflow_b.id)},
        )
        self.assertEqual(resp.status_code, 400)

        workflow_a = Workflow.objects.create(org=org_a, name="Workflow A", created_by_user=pm)
        WorkflowStage.objects.create(workflow=workflow_a, name="Backlog", order=1, is_done=False)
        WorkflowStage.objects.create(
            workflow=workflow_a,
            name="Done",
            order=2,
            is_done=True,
            category="done",
            progress_percent=100,
        )

        resp = self._patch_json(
            f"/api/orgs/{org_a.id}/projects/{project.id}",
            {"workflow_id": str(workflow_a.id)},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["project"]["workflow_id"], str(workflow_a.id))
        self.assertTrue(AuditEvent.objects.filter(event_type="project.workflow_assigned").exists())

    def test_subtask_stage_update_rejects_cross_workflow_stage(self) -> None:
        pm = get_user_model().objects.create_user(email="pm4@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        workflow_a = Workflow.objects.create(org=org, name="Workflow A", created_by_user=pm)
        stage_a_backlog = WorkflowStage.objects.create(
            workflow=workflow_a, name="Backlog", order=1, is_done=False
        )
        WorkflowStage.objects.create(
            workflow=workflow_a,
            name="Done",
            order=2,
            is_done=True,
            category="done",
            progress_percent=100,
        )

        workflow_b = Workflow.objects.create(org=org, name="Workflow B", created_by_user=pm)
        WorkflowStage.objects.create(workflow=workflow_b, name="Backlog", order=1, is_done=False)
        stage_b_done = WorkflowStage.objects.create(
            workflow=workflow_b,
            name="Done",
            order=2,
            is_done=True,
            category="done",
            progress_percent=100,
        )

        project = Project.objects.create(org=org, name="Project")
        epic = Epic.objects.create(project=project, title="Epic")
        task = Task.objects.create(epic=epic, title="Task")
        subtask = Subtask.objects.create(task=task, title="Subtask")

        self.client.force_login(pm)

        resp = self._patch_json(
            f"/api/orgs/{org.id}/projects/{project.id}",
            {"workflow_id": str(workflow_a.id)},
        )
        self.assertEqual(resp.status_code, 200)

        resp = self._patch_json(
            f"/api/orgs/{org.id}/subtasks/{subtask.id}",
            {"workflow_stage_id": str(stage_b_done.id)},
        )
        self.assertEqual(resp.status_code, 400)

        resp = self._patch_json(
            f"/api/orgs/{org.id}/subtasks/{subtask.id}",
            {"workflow_stage_id": str(stage_a_backlog.id)},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["subtask"]["workflow_stage_id"], str(stage_a_backlog.id))
        self.assertTrue(
            AuditEvent.objects.filter(event_type="subtask.workflow_stage_changed").exists()
        )

    def test_task_stage_update_rejects_cross_workflow_and_syncs_status(self) -> None:
        pm = get_user_model().objects.create_user(email="pm-task-stage@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        workflow_a = Workflow.objects.create(org=org, name="Workflow A", created_by_user=pm)
        stage_a_backlog = WorkflowStage.objects.create(
            workflow=workflow_a,
            name="Backlog",
            order=1,
            is_done=False,
            category="backlog",
            progress_percent=0,
        )
        stage_a_wip = WorkflowStage.objects.create(
            workflow=workflow_a,
            name="In progress",
            order=2,
            is_done=False,
            counts_as_wip=True,
            category="in_progress",
            progress_percent=50,
        )
        WorkflowStage.objects.create(
            workflow=workflow_a,
            name="Done",
            order=3,
            is_done=True,
            category="done",
            progress_percent=100,
        )

        workflow_b = Workflow.objects.create(org=org, name="Workflow B", created_by_user=pm)
        stage_b_done = WorkflowStage.objects.create(
            workflow=workflow_b,
            name="Done",
            order=1,
            is_done=True,
            category="done",
            progress_percent=100,
        )

        project = Project.objects.create(org=org, name="Project")
        epic = Epic.objects.create(project=project, title="Epic")
        task = Task.objects.create(epic=epic, title="Task", status="backlog")

        self.client.force_login(pm)

        resp = self._patch_json(
            f"/api/orgs/{org.id}/projects/{project.id}",
            {"workflow_id": str(workflow_a.id)},
        )
        self.assertEqual(resp.status_code, 200)

        resp = self._patch_json(
            f"/api/orgs/{org.id}/tasks/{task.id}",
            {"workflow_stage_id": str(stage_b_done.id)},
        )
        self.assertEqual(resp.status_code, 400)

        resp = self._patch_json(
            f"/api/orgs/{org.id}/tasks/{task.id}",
            {"workflow_stage_id": str(stage_a_wip.id)},
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()["task"]
        self.assertEqual(payload["workflow_stage_id"], str(stage_a_wip.id))
        self.assertEqual(payload["status"], "in_progress")
        self.assertTrue(
            AuditEvent.objects.filter(event_type="task.workflow_stage_changed").exists()
        )

        resp = self._patch_json(
            f"/api/orgs/{org.id}/tasks/{task.id}",
            {"status": "done"},
        )
        self.assertEqual(resp.status_code, 400)

        resp = self._patch_json(
            f"/api/orgs/{org.id}/tasks/{task.id}",
            {"workflow_stage_id": str(stage_a_backlog.id)},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["task"]["status"], "backlog")

    def test_project_workflow_change_is_rejected_when_task_is_staged(self) -> None:
        pm = get_user_model().objects.create_user(email="pm-task-guard@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        workflow_a = Workflow.objects.create(org=org, name="Workflow A", created_by_user=pm)
        stage_a_backlog = WorkflowStage.objects.create(
            workflow=workflow_a,
            name="Backlog",
            order=1,
            is_done=False,
            category="backlog",
            progress_percent=0,
        )
        WorkflowStage.objects.create(
            workflow=workflow_a,
            name="Done",
            order=2,
            is_done=True,
            category="done",
            progress_percent=100,
        )

        workflow_b = Workflow.objects.create(org=org, name="Workflow B", created_by_user=pm)
        WorkflowStage.objects.create(
            workflow=workflow_b,
            name="Done",
            order=1,
            is_done=True,
            category="done",
            progress_percent=100,
        )

        project = Project.objects.create(org=org, name="Project")
        epic = Epic.objects.create(project=project, title="Epic")
        task = Task.objects.create(epic=epic, title="Task", status="backlog")

        self.client.force_login(pm)

        resp = self._patch_json(
            f"/api/orgs/{org.id}/projects/{project.id}",
            {"workflow_id": str(workflow_a.id)},
        )
        self.assertEqual(resp.status_code, 200)

        resp = self._patch_json(
            f"/api/orgs/{org.id}/tasks/{task.id}",
            {"workflow_stage_id": str(stage_a_backlog.id)},
        )
        self.assertEqual(resp.status_code, 200)

        resp = self._patch_json(
            f"/api/orgs/{org.id}/projects/{project.id}",
            {"workflow_id": str(workflow_b.id)},
        )
        self.assertEqual(resp.status_code, 400)

    def test_cannot_delete_stage_referenced_by_subtask(self) -> None:
        pm = get_user_model().objects.create_user(email="pm5@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        workflow = Workflow.objects.create(org=org, name="Workflow", created_by_user=pm)
        stage_backlog = WorkflowStage.objects.create(
            workflow=workflow, name="Backlog", order=1, is_done=False
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
        Subtask.objects.create(task=task, title="Subtask", workflow_stage=stage_backlog)

        self.client.force_login(pm)

        resp = self.client.delete(
            f"/api/orgs/{org.id}/workflows/{workflow.id}/stages/{stage_backlog.id}"
        )
        self.assertEqual(resp.status_code, 400)

    def test_cannot_delete_stage_referenced_by_task(self) -> None:
        pm = get_user_model().objects.create_user(email="pm-task-delete@example.com", password="pw")
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
        Task.objects.create(epic=epic, title="Task", workflow_stage=stage_backlog)

        self.client.force_login(pm)

        resp = self.client.delete(
            f"/api/orgs/{org.id}/workflows/{workflow.id}/stages/{stage_backlog.id}"
        )
        self.assertEqual(resp.status_code, 400)

    def test_cannot_delete_workflow_assigned_to_project(self) -> None:
        pm = get_user_model().objects.create_user(email="pm6@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        workflow = Workflow.objects.create(org=org, name="Workflow", created_by_user=pm)
        WorkflowStage.objects.create(workflow=workflow, name="Backlog", order=1, is_done=False)
        WorkflowStage.objects.create(
            workflow=workflow,
            name="Done",
            order=2,
            is_done=True,
            category="done",
            progress_percent=100,
        )
        Project.objects.create(org=org, name="Project", workflow=workflow)

        self.client.force_login(pm)

        resp = self.client.delete(f"/api/orgs/{org.id}/workflows/{workflow.id}")
        self.assertEqual(resp.status_code, 400)

    def test_cannot_delete_workflow_when_stages_referenced_by_tasks(self) -> None:
        pm = get_user_model().objects.create_user(
            email="pm-task-workflow-delete@example.com", password="pw"
        )
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

        project = Project.objects.create(org=org, name="Project")
        epic = Epic.objects.create(project=project, title="Epic")
        Task.objects.create(epic=epic, title="Task", workflow_stage=stage_backlog)

        self.client.force_login(pm)

        resp = self.client.delete(f"/api/orgs/{org.id}/workflows/{workflow.id}")
        self.assertEqual(resp.status_code, 400)
