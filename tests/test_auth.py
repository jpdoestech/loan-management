"""Unit tests for crypto and auth service."""
import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.utils.crypto import hash_password, verify_password


class TestCrypto(unittest.TestCase):

    def test_hash_is_not_plaintext(self):
        h = hash_password("secret123")
        self.assertNotEqual(h, "secret123")

    def test_verify_correct_password(self):
        h = hash_password("mypassword")
        self.assertTrue(verify_password("mypassword", h))

    def test_verify_wrong_password(self):
        h = hash_password("mypassword")
        self.assertFalse(verify_password("wrong", h))

    def test_hash_different_each_time(self):
        h1 = hash_password("abc")
        h2 = hash_password("abc")
        # salted — should differ
        self.assertNotEqual(h1, h2)

    def test_empty_password(self):
        h = hash_password("")
        self.assertTrue(verify_password("", h))

    def test_unicode_password(self):
        pw = "pässwörD!123"
        h = hash_password(pw)
        self.assertTrue(verify_password(pw, h))


class TestAuthService(unittest.TestCase):

    def setUp(self):
        import tempfile, sqlite3
        from src.data.db_manager import DBManager
        from src.services.auth_service import AuthService
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db = DBManager(db_path=self.tmp.name)
        self.db.initialize()
        self.auth = AuthService(self.db)
        # Create test user
        self.db.create_user("testuser", hash_password("pass123"),
                            "Test User", "staff", None)

    def tearDown(self):
        self.db.close()
        os.unlink(self.tmp.name)

    def test_login_success(self):
        user = self.auth.login("testuser", "pass123")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "testuser")

    def test_login_wrong_password(self):
        user = self.auth.login("testuser", "wrongpass")
        self.assertIsNone(user)

    def test_login_unknown_user(self):
        user = self.auth.login("nobody", "pass123")
        self.assertIsNone(user)

    def test_logout_clears_session(self):
        self.auth.login("testuser", "pass123")
        self.assertTrue(self.auth.is_logged_in())
        self.auth.logout()
        self.assertFalse(self.auth.is_logged_in())

    def test_change_password(self):
        self.auth.login("testuser", "pass123")
        ok, msg = self.auth.change_password(
            self.auth.current_user.id, "pass123", "newpass456")
        self.assertTrue(ok)
        # verify new password works
        self.auth.logout()
        user = self.auth.login("testuser", "newpass456")
        self.assertIsNotNone(user)

    def test_change_password_wrong_old(self):
        self.auth.login("testuser", "pass123")
        ok, msg = self.auth.change_password(
            self.auth.current_user.id, "badold", "newpass456")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
