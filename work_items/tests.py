import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from identity.models import Org, OrgMembership

from .models import Epic, Project, Task, WorkItemStatus


class WorkItemsApiTests(TestCase):
    def _post_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.post(url, data=json.dumps(payload), content_type="application/json")

    def _patch_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.patch(url, data=json.dumps(payload), content_type="application/json")

    def test_client_role_is_default_deny(self) -> None:
        user = get_user_model().objects.create_user(email="client@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.CLIENT)

        self.client.force_login(user)

        response = self.client.get(f"/api/orgs/{org.id}/projects")
        self.assertEqual(response.status_code, 403)

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

    def test_scheduling_fields_validation_and_client_safe_reads(self) -> None:
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
                "title": "Task",
                "description": "internal",
                "start_date": "2026-02-01",
                "end_date": "2026-02-03",
            },
        )
        self.assertEqual(task_resp.status_code, 200)
        task_id = task_resp.json()["task"]["id"]

        subtask_resp = self._post_json(
            f"/api/orgs/{org.id}/tasks/{task_id}/subtasks",
            {"title": "Subtask", "description": "internal", "start_date": "2026-02-02"},
        )
        self.assertEqual(subtask_resp.status_code, 200)
        subtask_id = subtask_resp.json()["subtask"]["id"]

        client = self.client_class()
        client.force_login(client_user)

        list_tasks = client.get(f"/api/orgs/{org.id}/projects/{project_id}/tasks")
        self.assertEqual(list_tasks.status_code, 200)
        task = list_tasks.json()["tasks"][0]
        self.assertEqual(task["id"], task_id)
        self.assertEqual(task["start_date"], "2026-02-01")
        self.assertEqual(task["end_date"], "2026-02-03")
        self.assertNotIn("description", task)
        self.assertNotIn("created_at", task)
        self.assertNotIn("updated_at", task)

        task_detail = client.get(f"/api/orgs/{org.id}/tasks/{task_id}")
        self.assertEqual(task_detail.status_code, 200)
        self.assertEqual(task_detail.json()["task"]["start_date"], "2026-02-01")
        self.assertNotIn("description", task_detail.json()["task"])

        patch_task = self._patch_json(
            f"/api/orgs/{org.id}/tasks/{task_id}", {"title": "x"}, client=client
        )
        self.assertEqual(patch_task.status_code, 403)

        delete_subtask = client.delete(f"/api/orgs/{org.id}/subtasks/{subtask_id}")
        self.assertEqual(delete_subtask.status_code, 403)

        list_subtasks = client.get(f"/api/orgs/{org.id}/tasks/{task_id}/subtasks")
        self.assertEqual(list_subtasks.status_code, 200)
        subtask = list_subtasks.json()["subtasks"][0]
        self.assertEqual(subtask["id"], subtask_id)
        self.assertEqual(subtask["start_date"], "2026-02-02")
        self.assertIsNone(subtask["end_date"])
        self.assertNotIn("description", subtask)
