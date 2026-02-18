import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from identity.models import Org, OrgMembership
from workflows.models import Workflow, WorkflowStage

from .models import Epic, Project, Subtask, Task, WorkItemStatus


class WorkItemsApiTests(TestCase):
    def _post_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.post(url, data=json.dumps(payload), content_type="application/json")

    def _patch_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.patch(url, data=json.dumps(payload), content_type="application/json")

    def test_client_role_can_read_projects_with_safe_fields(self) -> None:
        user = get_user_model().objects.create_user(email="client@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.CLIENT)
        project = Project.objects.create(org=org, name="Project", description="internal")

        self.client.force_login(user)

        response = self.client.get(f"/api/orgs/{org.id}/projects")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["projects"]), 1)
        project_payload = payload["projects"][0]
        self.assertEqual(project_payload["id"], str(project.id))
        self.assertEqual(project_payload["org_id"], str(org.id))
        self.assertEqual(project_payload["name"], "Project")
        self.assertIn("updated_at", project_payload)
        self.assertNotIn("workflow_id", project_payload)
        self.assertNotIn("description", project_payload)
        self.assertNotIn("created_at", project_payload)

        response = self.client.get(f"/api/orgs/{org.id}/projects/{project.id}")
        self.assertEqual(response.status_code, 200)
        project_payload = response.json()["project"]
        self.assertEqual(project_payload["id"], str(project.id))
        self.assertEqual(project_payload["org_id"], str(org.id))
        self.assertEqual(project_payload["name"], "Project")
        self.assertIn("updated_at", project_payload)
        self.assertNotIn("workflow_id", project_payload)
        self.assertNotIn("description", project_payload)
        self.assertNotIn("created_at", project_payload)

        response = self._post_json(f"/api/orgs/{org.id}/projects", {"name": "P"})
        self.assertEqual(response.status_code, 403)

    def test_non_membership_is_403_and_cross_org_object_access_is_404(self) -> None:
        user = get_user_model().objects.create_user(email="user@example.com", password="pw")
        org_a = Org.objects.create(name="Org A")
        org_b = Org.objects.create(name="Org B")
        OrgMembership.objects.create(org=org_a, user=user, role=OrgMembership.Role.MEMBER)

        project_b = Project.objects.create(org=org_b, name="Project B")

        self.client.force_login(user)

        response = self.client.get(f"/api/orgs/{org_b.id}/projects")
        self.assertEqual(response.status_code, 403)

        response = self.client.get(f"/api/orgs/{org_a.id}/projects/{project_b.id}")
        self.assertEqual(response.status_code, 404)

    def test_crud_and_list_filters(self) -> None:
        user = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.PM)

        self.client.force_login(user)

        project_resp = self._post_json(
            f"/api/orgs/{org.id}/projects", {"name": "Project 1", "description": "D"}
        )
        self.assertEqual(project_resp.status_code, 200)
        project_id = project_resp.json()["project"]["id"]

        list_projects = self.client.get(f"/api/orgs/{org.id}/projects")
        self.assertEqual(list_projects.status_code, 200)
        self.assertEqual(len(list_projects.json()["projects"]), 1)

        patch_project = self._patch_json(
            f"/api/orgs/{org.id}/projects/{project_id}", {"name": "Project 1b"}
        )
        self.assertEqual(patch_project.status_code, 200)
        self.assertEqual(patch_project.json()["project"]["name"], "Project 1b")

        epic_resp = self._post_json(
            f"/api/orgs/{org.id}/projects/{project_id}/epics",
            {"title": "Epic 1", "description": "E", "status": WorkItemStatus.BACKLOG},
        )
        self.assertEqual(epic_resp.status_code, 200)
        epic_id = epic_resp.json()["epic"]["id"]

        list_epics = self.client.get(f"/api/orgs/{org.id}/projects/{project_id}/epics")
        self.assertEqual(list_epics.status_code, 200)
        self.assertEqual(len(list_epics.json()["epics"]), 1)

        epic_detail = self.client.get(f"/api/orgs/{org.id}/epics/{epic_id}")
        self.assertEqual(epic_detail.status_code, 200)

        patch_epic = self._patch_json(
            f"/api/orgs/{org.id}/epics/{epic_id}", {"title": "Epic 1b", "status": None}
        )
        self.assertEqual(patch_epic.status_code, 200)
        self.assertEqual(patch_epic.json()["epic"]["title"], "Epic 1b")
        self.assertIsNone(patch_epic.json()["epic"]["status"])

        task1_resp = self._post_json(
            f"/api/orgs/{org.id}/epics/{epic_id}/tasks",
            {
                "title": "Task 1",
                "description": "T1",
                "start_date": "2026-02-01",
                "end_date": "2026-02-03",
            },
        )
        self.assertEqual(task1_resp.status_code, 200)
        task1_id = task1_resp.json()["task"]["id"]
        self.assertEqual(task1_resp.json()["task"]["status"], WorkItemStatus.BACKLOG)
        self.assertEqual(task1_resp.json()["task"]["start_date"], "2026-02-01")
        self.assertEqual(task1_resp.json()["task"]["end_date"], "2026-02-03")

        task2_resp = self._post_json(
            f"/api/orgs/{org.id}/epics/{epic_id}/tasks",
            {"title": "Task 2", "description": "T2", "status": WorkItemStatus.QA},
        )
        self.assertEqual(task2_resp.status_code, 200)

        list_tasks = self.client.get(f"/api/orgs/{org.id}/projects/{project_id}/tasks")
        self.assertEqual(list_tasks.status_code, 200)
        self.assertEqual(len(list_tasks.json()["tasks"]), 2)

        filter_tasks_qa = self.client.get(
            f"/api/orgs/{org.id}/projects/{project_id}/tasks?status=qa"
        )
        self.assertEqual(filter_tasks_qa.status_code, 200)
        self.assertEqual(len(filter_tasks_qa.json()["tasks"]), 1)

        task_detail = self.client.get(f"/api/orgs/{org.id}/tasks/{task1_id}")
        self.assertEqual(task_detail.status_code, 200)

        patch_task_end_date = self._patch_json(
            f"/api/orgs/{org.id}/tasks/{task1_id}", {"end_date": "2026-02-04"}
        )
        self.assertEqual(patch_task_end_date.status_code, 200)
        self.assertEqual(patch_task_end_date.json()["task"]["start_date"], "2026-02-01")
        self.assertEqual(patch_task_end_date.json()["task"]["end_date"], "2026-02-04")

        patch_task_clear_start_date = self._patch_json(
            f"/api/orgs/{org.id}/tasks/{task1_id}", {"start_date": None}
        )
        self.assertEqual(patch_task_clear_start_date.status_code, 200)
        self.assertIsNone(patch_task_clear_start_date.json()["task"]["start_date"])
        self.assertEqual(patch_task_clear_start_date.json()["task"]["end_date"], "2026-02-04")

        patch_task_status = self._patch_json(
            f"/api/orgs/{org.id}/tasks/{task1_id}", {"status": WorkItemStatus.DONE}
        )
        self.assertEqual(patch_task_status.status_code, 200)
        self.assertEqual(patch_task_status.json()["task"]["status"], WorkItemStatus.DONE)

        task_id = patch_task_status.json()["task"]["id"]

        subtask1_resp = self._post_json(
            f"/api/orgs/{org.id}/tasks/{task_id}/subtasks",
            {"title": "Subtask 1", "start_date": "2026-02-02", "end_date": "2026-02-03"},
        )
        self.assertEqual(subtask1_resp.status_code, 200)
        subtask1_id = subtask1_resp.json()["subtask"]["id"]
        self.assertEqual(subtask1_resp.json()["subtask"]["start_date"], "2026-02-02")
        self.assertEqual(subtask1_resp.json()["subtask"]["end_date"], "2026-02-03")

        self._post_json(
            f"/api/orgs/{org.id}/tasks/{task_id}/subtasks",
            {"title": "Subtask 2", "status": WorkItemStatus.QA},
        )

        list_subtasks = self.client.get(f"/api/orgs/{org.id}/tasks/{task_id}/subtasks")
        self.assertEqual(list_subtasks.status_code, 200)
        self.assertEqual(len(list_subtasks.json()["subtasks"]), 2)

        filter_subtasks_qa = self.client.get(
            f"/api/orgs/{org.id}/tasks/{task_id}/subtasks?status=qa"
        )
        self.assertEqual(filter_subtasks_qa.status_code, 200)
        self.assertEqual(len(filter_subtasks_qa.json()["subtasks"]), 1)

        delete_subtask = self.client.delete(f"/api/orgs/{org.id}/subtasks/{subtask1_id}")
        self.assertEqual(delete_subtask.status_code, 204)

        get_deleted_subtask = self.client.get(f"/api/orgs/{org.id}/subtasks/{subtask1_id}")
        self.assertEqual(get_deleted_subtask.status_code, 404)

        delete_task = self.client.delete(f"/api/orgs/{org.id}/tasks/{task1_id}")
        self.assertEqual(delete_task.status_code, 204)

        self.assertFalse(Task.objects.filter(id=task1_id).exists())

    def test_cross_org_chain_checks_for_nested_resources(self) -> None:
        user = get_user_model().objects.create_user(email="member@example.com", password="pw")
        org_a = Org.objects.create(name="Org A")
        org_b = Org.objects.create(name="Org B")
        OrgMembership.objects.create(org=org_a, user=user, role=OrgMembership.Role.MEMBER)

        project_b = Project.objects.create(org=org_b, name="Project B")
        epic_b = Epic.objects.create(
            project=project_b, title="Epic B", status=WorkItemStatus.BACKLOG
        )
        task_b = Task.objects.create(epic=epic_b, title="Task B", status=WorkItemStatus.BACKLOG)

        self.client.force_login(user)

        response = self.client.get(f"/api/orgs/{org_a.id}/epics/{epic_b.id}")
        self.assertEqual(response.status_code, 404)

        response = self.client.get(f"/api/orgs/{org_a.id}/tasks/{task_b.id}")
        self.assertEqual(response.status_code, 404)

    def test_project_tasks_list_includes_last_updated_at_and_uses_filtered_task_set(self) -> None:
        pm = get_user_model().objects.create_user(
            email="pm-last-updated@example.com", password="pw"
        )
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        self.client.force_login(pm)

        project_resp = self._post_json(f"/api/orgs/{org.id}/projects", {"name": "Project"})
        self.assertEqual(project_resp.status_code, 200)
        project_id = project_resp.json()["project"]["id"]

        epic_resp = self._post_json(
            f"/api/orgs/{org.id}/projects/{project_id}/epics",
            {"title": "Epic"},
        )
        self.assertEqual(epic_resp.status_code, 200)
        epic_id = epic_resp.json()["epic"]["id"]

        task1_resp = self._post_json(
            f"/api/orgs/{org.id}/epics/{epic_id}/tasks",
            {"title": "Task 1"},
        )
        self.assertEqual(task1_resp.status_code, 200)
        task1_id = task1_resp.json()["task"]["id"]

        task2_resp = self._post_json(
            f"/api/orgs/{org.id}/epics/{epic_id}/tasks",
            {"title": "Task 2", "status": WorkItemStatus.QA},
        )
        self.assertEqual(task2_resp.status_code, 200)
        task2_id = task2_resp.json()["task"]["id"]

        t1 = timezone.now().replace(microsecond=0)
        t2 = t1 + timedelta(hours=1)
        Task.objects.filter(id=task1_id).update(updated_at=t1)
        Task.objects.filter(id=task2_id).update(updated_at=t2)

        list_tasks = self.client.get(f"/api/orgs/{org.id}/projects/{project_id}/tasks")
        self.assertEqual(list_tasks.status_code, 200)
        self.assertEqual(list_tasks.json()["last_updated_at"], t2.isoformat())
        self.assertEqual(len(list_tasks.json()["tasks"]), 2)

        list_backlog = self.client.get(
            f"/api/orgs/{org.id}/projects/{project_id}/tasks?status=backlog"
        )
        self.assertEqual(list_backlog.status_code, 200)
        self.assertEqual(list_backlog.json()["last_updated_at"], t1.isoformat())
        self.assertEqual(len(list_backlog.json()["tasks"]), 1)

        list_qa = self.client.get(f"/api/orgs/{org.id}/projects/{project_id}/tasks?status=qa")
        self.assertEqual(list_qa.status_code, 200)
        self.assertEqual(list_qa.json()["last_updated_at"], t2.isoformat())
        self.assertEqual(len(list_qa.json()["tasks"]), 1)

    def test_project_tasks_list_last_updated_at_is_null_when_empty(self) -> None:
        pm = get_user_model().objects.create_user(
            email="pm-empty-updated@example.com", password="pw"
        )
        client_user = get_user_model().objects.create_user(
            email="client-empty-updated@example.com", password="pw"
        )
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)
        OrgMembership.objects.create(org=org, user=client_user, role=OrgMembership.Role.CLIENT)

        project = Project.objects.create(org=org, name="Project")

        client = self.client_class()
        client.force_login(client_user)

        resp = client.get(f"/api/orgs/{org.id}/projects/{project.id}/tasks")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["tasks"], [])
        self.assertIsNone(resp.json()["last_updated_at"])

    def test_client_safe_policy_for_tasks_and_subtasks(self) -> None:
        pm = get_user_model().objects.create_user(email="pm2@example.com", password="pw")
        client_user = get_user_model().objects.create_user(
            email="client2@example.com", password="pw"
        )
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)
        OrgMembership.objects.create(org=org, user=client_user, role=OrgMembership.Role.CLIENT)

        self.client.force_login(pm)

        project_resp = self._post_json(f"/api/orgs/{org.id}/projects", {"name": "Project"})
        self.assertEqual(project_resp.status_code, 200)
        project_id = project_resp.json()["project"]["id"]

        epic_resp = self._post_json(
            f"/api/orgs/{org.id}/projects/{project_id}/epics",
            {"title": "Epic", "start_date": "2026-02-01"},
        )
        self.assertEqual(epic_resp.status_code, 400)

        epic_resp = self._post_json(
            f"/api/orgs/{org.id}/projects/{project_id}/epics", {"title": "Epic"}
        )
        self.assertEqual(epic_resp.status_code, 200)
        epic_id = epic_resp.json()["epic"]["id"]

        bad_task = self._post_json(
            f"/api/orgs/{org.id}/epics/{epic_id}/tasks",
            {"title": "Bad", "start_date": "2026-02-03", "end_date": "2026-02-01"},
        )
        self.assertEqual(bad_task.status_code, 400)

        bad_task = self._post_json(
            f"/api/orgs/{org.id}/epics/{epic_id}/tasks",
            {"title": "Bad", "start_date": "2026/02/01"},
        )
        self.assertEqual(bad_task.status_code, 400)

        task_resp = self._post_json(
            f"/api/orgs/{org.id}/epics/{epic_id}/tasks",
            {
                "title": "Internal task",
                "description": "internal",
                "start_date": "2026-02-01",
                "end_date": "2026-02-03",
            },
        )
        self.assertEqual(task_resp.status_code, 200)
        internal_task_id = task_resp.json()["task"]["id"]

        safe_task_resp = self._post_json(
            f"/api/orgs/{org.id}/epics/{epic_id}/tasks",
            {
                "title": "Client task",
                "description": "internal",
                "start_date": "2026-02-01",
                "end_date": "2026-02-03",
            },
        )
        self.assertEqual(safe_task_resp.status_code, 200)
        safe_task_id = safe_task_resp.json()["task"]["id"]

        patch_client_safe = self._patch_json(
            f"/api/orgs/{org.id}/tasks/{safe_task_id}", {"client_safe": True}
        )
        self.assertEqual(patch_client_safe.status_code, 200)
        self.assertTrue(patch_client_safe.json()["task"]["client_safe"])

        t_safe = timezone.now().replace(microsecond=0)
        t_internal = t_safe + timedelta(hours=1)
        Task.objects.filter(id=safe_task_id).update(updated_at=t_safe)
        Task.objects.filter(id=internal_task_id).update(updated_at=t_internal)

        subtask_resp = self._post_json(
            f"/api/orgs/{org.id}/tasks/{safe_task_id}/subtasks",
            {"title": "Subtask", "description": "internal", "start_date": "2026-02-02"},
        )
        self.assertEqual(subtask_resp.status_code, 200)
        subtask_id = subtask_resp.json()["subtask"]["id"]

        client = self.client_class()
        client.force_login(client_user)

        list_projects = client.get(f"/api/orgs/{org.id}/projects")
        self.assertEqual(list_projects.status_code, 200)
        project_payload = list_projects.json()["projects"][0]
        self.assertEqual(project_payload["id"], project_id)
        self.assertIn("updated_at", project_payload)
        self.assertNotIn("workflow_id", project_payload)
        self.assertNotIn("description", project_payload)
        self.assertNotIn("created_at", project_payload)

        list_tasks = client.get(f"/api/orgs/{org.id}/projects/{project_id}/tasks")
        self.assertEqual(list_tasks.status_code, 200)
        self.assertEqual(list_tasks.json()["last_updated_at"], t_safe.isoformat())
        self.assertIsNotNone(parse_datetime(list_tasks.json()["last_updated_at"]))
        tasks = list_tasks.json()["tasks"]
        self.assertEqual(len(tasks), 1)
        task = tasks[0]
        self.assertEqual(task["id"], safe_task_id)
        self.assertEqual(task["start_date"], "2026-02-01")
        self.assertEqual(task["end_date"], "2026-02-03")
        self.assertEqual(task["progress"], 0.0)
        self.assertEqual(task["progress_why"]["reason"], "project_missing_workflow")
        self.assertEqual(task["custom_field_values"], [])
        self.assertNotIn("description", task)
        self.assertNotIn("created_at", task)
        self.assertIn("updated_at", task)

        task_detail = client.get(f"/api/orgs/{org.id}/tasks/{safe_task_id}")
        self.assertEqual(task_detail.status_code, 200)
        self.assertEqual(task_detail.json()["task"]["start_date"], "2026-02-01")
        self.assertEqual(task_detail.json()["task"]["progress"], 0.0)
        self.assertEqual(
            task_detail.json()["task"]["progress_why"]["reason"], "project_missing_workflow"
        )
        self.assertEqual(task_detail.json()["task"]["custom_field_values"], [])
        self.assertNotIn("description", task_detail.json()["task"])

        internal_task_detail = client.get(f"/api/orgs/{org.id}/tasks/{internal_task_id}")
        self.assertEqual(internal_task_detail.status_code, 404)

        patch_task = self._patch_json(
            f"/api/orgs/{org.id}/tasks/{safe_task_id}", {"title": "x"}, client=client
        )
        self.assertEqual(patch_task.status_code, 403)

        delete_subtask = client.delete(f"/api/orgs/{org.id}/subtasks/{subtask_id}")
        self.assertEqual(delete_subtask.status_code, 403)

        list_subtasks = client.get(f"/api/orgs/{org.id}/tasks/{safe_task_id}/subtasks")
        self.assertEqual(list_subtasks.status_code, 403)


class WorkItemsProgressApiTests(TestCase):
    def _patch_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.patch(url, data=json.dumps(payload), content_type="application/json")

    def test_progress_fields_and_rollups(self) -> None:
        pm = get_user_model().objects.create_user(email="pm-progress@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        workflow = Workflow.objects.create(org=org, name="W", created_by_user=pm)
        stage_backlog = WorkflowStage.objects.create(
            workflow=workflow,
            name="Backlog",
            order=1,
            is_done=False,
            category="backlog",
            progress_percent=0,
        )
        stage_in_progress = WorkflowStage.objects.create(
            workflow=workflow,
            name="In Progress",
            order=2,
            is_done=False,
            counts_as_wip=True,
            category="in_progress",
            progress_percent=33,
        )
        stage_qa = WorkflowStage.objects.create(
            workflow=workflow, name="QA", order=3, is_done=False, category="qa", progress_percent=67
        )
        stage_done = WorkflowStage.objects.create(
            workflow=workflow,
            name="Done",
            order=4,
            is_done=True,
            category="done",
            progress_percent=100,
        )

        project = Project.objects.create(org=org, name="Project", workflow=workflow)
        epic = Epic.objects.create(project=project, title="Epic")
        task = Task.objects.create(epic=epic, title="Task")

        subtask_backlog = Subtask.objects.create(
            task=task, title="S1", workflow_stage=stage_backlog
        )
        Subtask.objects.create(task=task, title="S2", workflow_stage=stage_in_progress)
        Subtask.objects.create(task=task, title="S3", workflow_stage=stage_qa)
        Subtask.objects.create(task=task, title="S4", workflow_stage=stage_done)

        self.client.force_login(pm)

        subtasks_resp = self.client.get(f"/api/orgs/{org.id}/tasks/{task.id}/subtasks")
        self.assertEqual(subtasks_resp.status_code, 200)
        by_title = {s["title"]: s for s in subtasks_resp.json()["subtasks"]}
        self.assertAlmostEqual(by_title["S1"]["progress"], 0.0)
        self.assertAlmostEqual(by_title["S2"]["progress"], 0.33)
        self.assertAlmostEqual(by_title["S3"]["progress"], 0.67)
        self.assertAlmostEqual(by_title["S4"]["progress"], 1.0)
        self.assertEqual(by_title["S2"]["progress_why"]["policy"], "stage_progress_percent")
        self.assertEqual(by_title["S2"]["progress_why"]["stage_order"], 2)
        self.assertEqual(by_title["S2"]["progress_why"]["done_stage_order"], 4)
        self.assertEqual(by_title["S2"]["progress_why"]["stage_count"], 4)

        subtask_detail = self.client.get(f"/api/orgs/{org.id}/subtasks/{subtask_backlog.id}")
        self.assertEqual(subtask_detail.status_code, 200)
        self.assertEqual(
            subtask_detail.json()["subtask"]["progress_why"],
            by_title["S1"]["progress_why"],
        )

        task_detail = self.client.get(f"/api/orgs/{org.id}/tasks/{task.id}")
        self.assertEqual(task_detail.status_code, 200)
        self.assertAlmostEqual(task_detail.json()["task"]["progress"], 0.5)
        task_why = task_detail.json()["task"]["progress_why"]
        self.assertEqual(task_why["policy"], "average_of_subtask_progress")
        self.assertEqual(task_why["effective_policy"], "subtasks_rollup")
        self.assertEqual(task_why["subtask_count"], 4)
        self.assertAlmostEqual(task_why["subtask_progress_sum"], 2.0)

        task_list = self.client.get(f"/api/orgs/{org.id}/projects/{project.id}/tasks")
        self.assertEqual(task_list.status_code, 200)
        list_task = next(t for t in task_list.json()["tasks"] if t["id"] == str(task.id))
        self.assertEqual(list_task["progress_why"], task_detail.json()["task"]["progress_why"])

        stage_update = self._patch_json(
            f"/api/orgs/{org.id}/subtasks/{subtask_backlog.id}",
            {"workflow_stage_id": str(stage_done.id)},
        )
        self.assertEqual(stage_update.status_code, 200)
        self.assertAlmostEqual(stage_update.json()["subtask"]["progress"], 1.0)

        task_detail = self.client.get(f"/api/orgs/{org.id}/tasks/{task.id}")
        self.assertEqual(task_detail.status_code, 200)
        self.assertAlmostEqual(task_detail.json()["task"]["progress"], 0.75)

        empty_task = Task.objects.create(epic=epic, title="Empty")
        empty_task_detail = self.client.get(f"/api/orgs/{org.id}/tasks/{empty_task.id}")
        self.assertEqual(empty_task_detail.status_code, 200)
        self.assertEqual(empty_task_detail.json()["task"]["progress"], 0.0)
        self.assertEqual(empty_task_detail.json()["task"]["progress_why"]["reason"], "no_subtasks")

    def test_workflow_stage_policy_progress_works_for_tasks_with_no_subtasks(self) -> None:
        pm = get_user_model().objects.create_user(
            email="pm-stage-policy@example.com", password="pw"
        )
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        workflow = Workflow.objects.create(org=org, name="W", created_by_user=pm)
        WorkflowStage.objects.create(
            workflow=workflow,
            name="Backlog",
            order=1,
            is_done=False,
            category="backlog",
            progress_percent=0,
        )
        stage_in_progress = WorkflowStage.objects.create(
            workflow=workflow,
            name="In Progress",
            order=2,
            is_done=False,
            category="in_progress",
            progress_percent=50,
        )
        WorkflowStage.objects.create(
            workflow=workflow,
            name="Done",
            order=3,
            is_done=True,
            category="done",
            progress_percent=100,
        )

        project = Project.objects.create(
            org=org, name="Project", workflow=workflow, progress_policy="workflow_stage"
        )
        epic = Epic.objects.create(project=project, title="Epic", progress_policy="workflow_stage")
        task = Task.objects.create(
            epic=epic,
            title="Task",
            workflow_stage=stage_in_progress,
            status=stage_in_progress.category,
        )

        self.client.force_login(pm)

        task_detail = self.client.get(f"/api/orgs/{org.id}/tasks/{task.id}")
        self.assertEqual(task_detail.status_code, 200)
        self.assertAlmostEqual(task_detail.json()["task"]["progress"], 0.5)
        why = task_detail.json()["task"]["progress_why"]
        self.assertEqual(why["effective_policy"], "workflow_stage")
        self.assertEqual(why["policy"], "workflow_stage")

        epic_detail = self.client.get(f"/api/orgs/{org.id}/epics/{epic.id}")
        self.assertEqual(epic_detail.status_code, 200)
        self.assertAlmostEqual(epic_detail.json()["epic"]["progress"], 0.5)
        epic_why = epic_detail.json()["epic"]["progress_why"]
        self.assertEqual(epic_why["effective_policy"], "workflow_stage")
        self.assertEqual(epic_why["policy"], "average_of_task_progress")

        epic_detail = self.client.get(f"/api/orgs/{org.id}/epics/{epic.id}")
        self.assertEqual(epic_detail.status_code, 200)
        self.assertAlmostEqual(epic_detail.json()["epic"]["progress"], 0.5)
        self.assertEqual(epic_detail.json()["epic"]["progress_why"]["task_count"], 1)

        epic_list = self.client.get(f"/api/orgs/{org.id}/projects/{project.id}/epics")
        self.assertEqual(epic_list.status_code, 200)
        list_epic = next(e for e in epic_list.json()["epics"] if e["id"] == str(epic.id))
        self.assertEqual(list_epic["progress_why"], epic_detail.json()["epic"]["progress_why"])

    def test_progress_handles_workflow_missing_done_stage(self) -> None:
        pm = get_user_model().objects.create_user(email="pm-misconfig@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        workflow = Workflow.objects.create(org=org, name="Misconfigured", created_by_user=pm)
        stage_backlog = WorkflowStage.objects.create(workflow=workflow, name="Backlog", order=1)
        WorkflowStage.objects.create(workflow=workflow, name="Doing", order=2)

        project = Project.objects.create(org=org, name="Project", workflow=workflow)
        epic = Epic.objects.create(project=project, title="Epic")
        task = Task.objects.create(epic=epic, title="Task")
        subtask = Subtask.objects.create(task=task, title="S", workflow_stage=stage_backlog)

        self.client.force_login(pm)

        resp = self.client.get(f"/api/orgs/{org.id}/subtasks/{subtask.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["subtask"]["progress"], 0.0)
        self.assertEqual(
            resp.json()["subtask"]["progress_why"]["reason"],
            "workflow_missing_done_stage",
        )
