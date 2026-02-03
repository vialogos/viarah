from django.test import TestCase


class HealthzTests(TestCase):
    def test_healthz_is_200_when_db_is_reachable(self) -> None:
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")
