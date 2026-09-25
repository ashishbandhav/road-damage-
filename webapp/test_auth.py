import os
import tempfile
import unittest
import uuid

os.environ["DATABASE_PATH"] = os.path.join(
    tempfile.gettempdir(), f"roadscan-auth-test-{uuid.uuid4().hex}.sqlite3"
)
os.environ["ADMIN_EMAIL"] = "admin@example.test"
os.environ["ADMIN_PASSWORD"] = "admin-test-password"

from app import app


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def create_account(self, email="user@example.test"):
        return self.client.post(
            "/api/auth/register",
            json={"email": email, "password": "user-test-password"},
            headers={"X-Client-Platform": "flutter", "User-Agent": "RoadScan test client"},
        )

    def test_private_detector_requires_authentication(self):
        response = self.client.get("/app")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])
        self.assertEqual(self.client.get("/api/updates").status_code, 401)

    def test_user_registration_role_boundary_and_token_logout(self):
        email = f"user-{uuid.uuid4().hex}@example.test"
        response = self.create_account(email)
        self.assertEqual(response.status_code, 201)
        token = response.get_json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        self.assertEqual(self.client.get("/api/auth/me", headers=headers).get_json()["user"]["role"], "user")
        self.assertEqual(self.client.get("/admin", headers=headers).status_code, 403)
        self.assertEqual(self.client.get("/api/updates", headers=headers).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 401)

    def test_admin_sees_login_and_client_activity(self):
        email = f"audited-{uuid.uuid4().hex}@example.test"
        self.assertEqual(self.create_account(email).status_code, 201)

        admin = app.test_client()
        response = admin.post(
            "/api/auth/login",
            json={"email": "admin@example.test", "password": "admin-test-password"},
            headers={"X-Client-Platform": "web"},
        )
        self.assertEqual(response.status_code, 200)
        admin_token = response.get_json()["access_token"]
        dashboard = admin.get("/admin", headers={"Authorization": f"Bearer {admin_token}"})
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(email.encode(), dashboard.data)
        self.assertIn(b"account_created", dashboard.data)
        self.assertIn(b"flutter", dashboard.data)
        self.assertIn(b"RoadScan test client", dashboard.data)

    def test_invalid_registration_is_rejected(self):
        response = self.client.post(
            "/api/auth/register", json={"email": "bad@example.test", "password": "short"}
        )
        self.assertEqual(response.status_code, 400)

    def test_browser_registration_session_and_logout(self):
        email = f"browser-{uuid.uuid4().hex}@example.test"
        response = self.client.post(
            "/register",
            data={"email": email, "password": "browser-test-password"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(email.encode(), response.data)
        self.assertEqual(self.client.post("/logout").status_code, 302)
        self.assertEqual(self.client.get("/app").status_code, 302)


if __name__ == "__main__":
    unittest.main()