import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from identity.models import Org, OrgMembership
from work_items.models import Epic, Project, ProjectMembership, Task, WorkItemStatus

from .models import SavedView


class CustomizationApiTests(TestCase):
    def _post_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.post(url, data=json.dumps(payload), content_type="application/json")

    def _patch_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.patch(url, data=json.dumps(payload), content_type="application/json")

    def test_saved_views_crud_and_owner_scoping(self) -> None:
        pm = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)

        project = Project.objects.create(org=org, name="Project")

        self.client.force_login(pm)

        create = self._post_json(
            f"/api/orgs/{org.id}/projects/{project.id}/saved-views",
            {
                "name": "WIP",
                "filters": {"status": [WorkItemStatus.IN_PROGRESS], "search": ""},
                "sort": {"field": "created_at", "direction": "asc"},
                "group_by": "none",
            },
        )
        self.assertEqual(create.status_code, 200)
        saved_view = create.json()["saved_view"]
        self.assertEqual(saved_view["name"], "WIP")
        self.assertFalse(saved_view["client_safe"])

        list_views = self.client.get(f"/api/orgs/{org.id}/projects/{project.id}/saved-views")
        self.assertEqual(list_views.status_code, 200)
        self.assertEqual(len(list_views.json()["saved_views"]), 1)

        patch = self._patch_json(
            f"/api/orgs/{org.id}/saved-views/{saved_view['id']}",
            {"name": "WIP 2", "group_by": "status"},
        )
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.json()["saved_view"]["name"], "WIP 2")
        self.assertEqual(patch.json()["saved_view"]["group_by"], "status")

        delete = self.client.delete(f"/api/orgs/{org.id}/saved-views/{saved_view['id']}")
        self.assertEqual(delete.status_code, 204)

        list_after = self.client.get(f"/api/orgs/{org.id}/projects/{project.id}/saved-views")
        self.assertEqual(list_after.status_code, 200)
        self.assertEqual(list_after.json()["saved_views"], [])

    def test_saved_views_member_is_read_only(self) -> None:
        member = get_user_model().objects.create_user(email="member@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=member, role=OrgMembership.Role.MEMBER)
        project = Project.objects.create(org=org, name="Project")
        ProjectMembership.objects.create(project=project, user=member)

        self.client.force_login(member)

        create = self._post_json(
            f"/api/orgs/{org.id}/projects/{project.id}/saved-views",
            {"name": "x"},
        )
        self.assertEqual(create.status_code, 403)

        list_views = self.client.get(f"/api/orgs/{org.id}/projects/{project.id}/saved-views")
        self.assertEqual(list_views.status_code, 200)
        self.assertEqual(list_views.json()["saved_views"], [])

    def test_custom_fields_crud_and_validation(self) -> None:
        pm = get_user_model().objects.create_user(email="pm2@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)
        project = Project.objects.create(org=org, name="Project")

        self.client.force_login(pm)

        bad = self._post_json(
            f"/api/orgs/{org.id}/projects/{project.id}/custom-fields",
            {"name": "Priority", "field_type": "select", "options": []},
        )
        self.assertEqual(bad.status_code, 400)

        created = self._post_json(
            f"/api/orgs/{org.id}/projects/{project.id}/custom-fields",
            {
                "name": "Priority",
                "field_type": "select",
                "options": ["Low", "Med", "High"],
            },
        )
        self.assertEqual(created.status_code, 200)
        field = created.json()["custom_field"]
        self.assertEqual(field["field_type"], "select")
        self.assertFalse(field["client_safe"])

        patched = self._patch_json(
            f"/api/orgs/{org.id}/custom-fields/{field['id']}", {"client_safe": True}
        )
        self.assertEqual(patched.status_code, 200)
        self.assertTrue(patched.json()["custom_field"]["client_safe"])

        deleted = self.client.delete(f"/api/orgs/{org.id}/custom-fields/{field['id']}")
        self.assertEqual(deleted.status_code, 204)

        list_fields = self.client.get(f"/api/orgs/{org.id}/projects/{project.id}/custom-fields")
        self.assertEqual(list_fields.status_code, 200)
        self.assertEqual(list_fields.json()["custom_fields"], [])

    def test_custom_field_value_validation_rejects_invalid_select_option(self) -> None:
        pm = get_user_model().objects.create_user(email="pm-values@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)
        project = Project.objects.create(org=org, name="Project")
        epic = Epic.objects.create(project=project, title="Epic")
        task = Task.objects.create(
            epic=epic, title="Task", status=WorkItemStatus.BACKLOG, client_safe=True
        )

        self.client.force_login(pm)

        created = self._post_json(
            f"/api/orgs/{org.id}/projects/{project.id}/custom-fields",
            {
                "name": "Priority",
                "field_type": "select",
                "options": ["Low", "Med", "High"],
            },
        )
        self.assertEqual(created.status_code, 200)
        field_id = created.json()["custom_field"]["id"]

        bad = self._patch_json(
            f"/api/orgs/{org.id}/tasks/{task.id}/custom-field-values",
            {"values": {field_id: "Urgent"}},
        )
        self.assertEqual(bad.status_code, 400)

    def test_client_safe_filtering_for_definitions_values_and_saved_views(self) -> None:
        pm = get_user_model().objects.create_user(email="pm3@example.com", password="pw")
        client_user = get_user_model().objects.create_user(
            email="client@example.com", password="pw"
        )
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=pm, role=OrgMembership.Role.PM)
        OrgMembership.objects.create(org=org, user=client_user, role=OrgMembership.Role.CLIENT)
        project = Project.objects.create(org=org, name="Project")
        ProjectMembership.objects.create(project=project, user=client_user)
        epic = Epic.objects.create(project=project, title="Epic")
        task = Task.objects.create(
            epic=epic, title="Task", status=WorkItemStatus.BACKLOG, client_safe=True
        )

        self.client.force_login(pm)

        field_private = self._post_json(
            f"/api/orgs/{org.id}/projects/{project.id}/custom-fields",
            {
                "name": "Internal",
                "field_type": "text",
            },
        ).json()["custom_field"]
        field_safe = self._post_json(
            f"/api/orgs/{org.id}/projects/{project.id}/custom-fields",
            {
                "name": "Client",
                "field_type": "text",
            },
        ).json()["custom_field"]
        self._patch_json(
            f"/api/orgs/{org.id}/custom-fields/{field_safe['id']}", {"client_safe": True}
        )

        set_values = self._patch_json(
            f"/api/orgs/{org.id}/tasks/{task.id}/custom-field-values",
            {"values": {field_private["id"]: "secret", field_safe["id"]: "ok"}},
        )
        self.assertEqual(set_values.status_code, 200)

        client = self.client_class()
        client.force_login(client_user)

        list_fields = client.get(f"/api/orgs/{org.id}/projects/{project.id}/custom-fields")
        self.assertEqual(list_fields.status_code, 200)
        self.assertEqual(len(list_fields.json()["custom_fields"]), 1)
        self.assertEqual(list_fields.json()["custom_fields"][0]["name"], "Client")

        task_detail = client.get(f"/api/orgs/{org.id}/tasks/{task.id}")
        self.assertEqual(task_detail.status_code, 200)
        values = task_detail.json()["task"].get("custom_field_values")
        self.assertIsInstance(values, list)
        self.assertEqual(values, [{"field_id": field_safe["id"], "value": "ok"}])

        SavedView.objects.create(
            org=org,
            project=project,
            owner_user=client_user,
            name="Private",
            client_safe=False,
            filters={},
            sort={},
            group_by="none",
        )
        SavedView.objects.create(
            org=org,
            project=project,
            owner_user=client_user,
            name="Public",
            client_safe=True,
            filters={},
            sort={},
            group_by="none",
        )
        list_views = client.get(f"/api/orgs/{org.id}/projects/{project.id}/saved-views")
        self.assertEqual(list_views.status_code, 200)
        self.assertEqual(len(list_views.json()["saved_views"]), 1)
        self.assertEqual(list_views.json()["saved_views"][0]["name"], "Public")

    def test_cross_org_object_access_is_404(self) -> None:
        pm = get_user_model().objects.create_user(email="pm4@example.com", password="pw")
        org_a = Org.objects.create(name="Org A")
        org_b = Org.objects.create(name="Org B")
        OrgMembership.objects.create(org=org_a, user=pm, role=OrgMembership.Role.PM)
        project_b = Project.objects.create(org=org_b, name="Project B")

        SavedView.objects.create(
            org=org_b,
            project=project_b,
            owner_user=pm,
            name="x",
            filters={},
            sort={},
            group_by="none",
        )
        other_view_id = SavedView.objects.get(org=org_b, project=project_b, owner_user=pm).id

        self.client.force_login(pm)
        response = self._patch_json(
            f"/api/orgs/{org_a.id}/saved-views/{other_view_id}", {"name": "y"}
        )
        self.assertEqual(response.status_code, 404)
