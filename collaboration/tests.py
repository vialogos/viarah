import hashlib
import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from identity.models import Org, OrgMembership
from work_items.models import Epic, Project, Task


class CollaborationApiTests(TestCase):
    def _post_json(self, url: str, payload: dict, *, client=None):
        active_client = client or self.client
        return active_client.post(url, data=json.dumps(payload), content_type="application/json")

    def test_markdown_is_sanitized_and_links_are_safe(self) -> None:
        user = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.PM)
        project = Project.objects.create(org=org, name="Project")
        epic = Epic.objects.create(project=project, title="Epic")
        task = Task.objects.create(epic=epic, title="Task")

        self.client.force_login(user)

        payload = {
            "body_markdown": "Hello\\n\\n<script>alert(1)</script>\\n\\n[link](https://example.com)\\n\\n![x](https://example.com/x.png)"
        }
        create_resp = self._post_json(f"/api/orgs/{org.id}/tasks/{task.id}/comments", payload)
        self.assertEqual(create_resp.status_code, 201)
        comment = create_resp.json()["comment"]
        body_html = comment["body_html"]

        self.assertNotIn("<script", body_html.lower())
        self.assertNotIn("<img", body_html.lower())
        self.assertIn('rel="nofollow noopener noreferrer"', body_html)
        self.assertIn('href="https://example.com"', body_html)

        list_resp = self.client.get(f"/api/orgs/{org.id}/tasks/{task.id}/comments")
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(len(list_resp.json()["comments"]), 1)

    def test_client_role_is_forbidden(self) -> None:
        user = get_user_model().objects.create_user(email="client@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.CLIENT)
        project = Project.objects.create(org=org, name="Project")
        epic = Epic.objects.create(project=project, title="Epic")
        task = Task.objects.create(epic=epic, title="Task")

        self.client.force_login(user)

        response = self.client.get(f"/api/orgs/{org.id}/tasks/{task.id}/comments")
        self.assertEqual(response.status_code, 403)

        response = self._post_json(
            f"/api/orgs/{org.id}/tasks/{task.id}/comments", {"body_markdown": "nope"}
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            f"/api/orgs/{org.id}/tasks/{task.id}/attachments",
            data={"file": SimpleUploadedFile("x.txt", b"x", content_type="text/plain")},
        )
        self.assertEqual(response.status_code, 403)

    def test_attachment_upload_download_and_comment_binding(self) -> None:
        user = get_user_model().objects.create_user(email="member@example.com", password="pw")
        org = Org.objects.create(name="Org")
        OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.MEMBER)
        project = Project.objects.create(org=org, name="Project")
        epic = Epic.objects.create(project=project, title="Epic")
        task = Task.objects.create(epic=epic, title="Task")

        self.client.force_login(user)

        comment_resp = self._post_json(
            f"/api/orgs/{org.id}/tasks/{task.id}/comments", {"body_markdown": "hi"}
        )
        self.assertEqual(comment_resp.status_code, 201)
        comment_id = comment_resp.json()["comment"]["id"]

        content = b"hello world"
        file = SimpleUploadedFile("hello.txt", content, content_type="text/plain")
        upload_resp = self.client.post(
            f"/api/orgs/{org.id}/tasks/{task.id}/attachments",
            data={"file": file, "comment_id": comment_id},
        )
        self.assertEqual(upload_resp.status_code, 201)
        attachment = upload_resp.json()["attachment"]
        self.assertEqual(attachment["filename"], "hello.txt")
        self.assertEqual(attachment["content_type"], "text/plain")
        self.assertEqual(attachment["size_bytes"], len(content))
        self.assertEqual(attachment["sha256"], hashlib.sha256(content).hexdigest())
        self.assertEqual(attachment["comment_id"], comment_id)

        list_comments = self.client.get(f"/api/orgs/{org.id}/tasks/{task.id}/comments")
        self.assertEqual(list_comments.status_code, 200)
        listed = list_comments.json()["comments"][0]
        self.assertEqual(listed["attachment_ids"], [attachment["id"]])

        list_attachments = self.client.get(f"/api/orgs/{org.id}/tasks/{task.id}/attachments")
        self.assertEqual(list_attachments.status_code, 200)
        self.assertEqual(len(list_attachments.json()["attachments"]), 1)

        download_resp = self.client.get(attachment["download_url"])
        self.assertEqual(download_resp.status_code, 200)
        downloaded = b"".join(download_resp.streaming_content)
        self.assertEqual(downloaded, content)
        self.assertIn("hello.txt", download_resp.headers.get("Content-Disposition", ""))

    def test_cross_org_download_is_blocked(self) -> None:
        user = get_user_model().objects.create_user(email="member2@example.com", password="pw")
        org_a = Org.objects.create(name="Org A")
        org_b = Org.objects.create(name="Org B")
        OrgMembership.objects.create(org=org_a, user=user, role=OrgMembership.Role.MEMBER)

        project_b = Project.objects.create(org=org_b, name="Project")
        epic_b = Epic.objects.create(project=project_b, title="Epic")
        task_b = Task.objects.create(epic=epic_b, title="Task")

        uploader = get_user_model().objects.create_user(email="pm@example.com", password="pw")
        OrgMembership.objects.create(org=org_b, user=uploader, role=OrgMembership.Role.PM)
        self.client.force_login(uploader)
        upload_resp = self.client.post(
            f"/api/orgs/{org_b.id}/tasks/{task_b.id}/attachments",
            data={"file": SimpleUploadedFile("x.txt", b"x", content_type="text/plain")},
        )
        self.assertEqual(upload_resp.status_code, 201)
        attachment_id = upload_resp.json()["attachment"]["id"]

        self.client.force_login(user)

        wrong_org_path = f"/api/orgs/{org_a.id}/attachments/{attachment_id}/download"
        response = self.client.get(wrong_org_path)
        self.assertEqual(response.status_code, 404)

        correct_org_path = f"/api/orgs/{org_b.id}/attachments/{attachment_id}/download"
        response = self.client.get(correct_org_path)
        self.assertEqual(response.status_code, 403)
