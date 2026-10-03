"""Backend tests for EASA Part-66 AI Study Assistant."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://easa-module3-prep.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@easa-study.app"
ADMIN_PASS = "Part66Admin!2026"


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data
    assert data["user"]["email"] == ADMIN_EMAIL
    return data["token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# --- Auth tests ---
class TestAuth:
    def test_login_wrong_password(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"}, timeout=20)
        assert r.status_code == 401

    def test_admin_unauth_401(self):
        r = requests.get(f"{BASE_URL}/api/admin/status", timeout=20)
        assert r.status_code == 401

    def test_admin_me(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL


# --- Admin status/configuration ---
class TestAdminStatus:
    def test_status(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/status", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        print("ADMIN STATUS:", r.json())

    def test_files(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/files", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        data = r.json()
        print("FILES:", data)

    def test_module3_report(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/modules/3/report", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        rep = r.json()
        print("REPORT:", rep)
        # Expect 52 Q, 65 min, 3 options, 1 correct
        txt = str(rep)
        assert "52" in txt
        assert "65" in txt

    def test_jobs(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/jobs", headers=admin_headers, timeout=20)
        assert r.status_code == 200

    def test_admin_questions(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/questions", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        data = r.json()
        print(f"QUESTIONS COUNT: {len(data) if isinstance(data, list) else data}")


# --- Student endpoints ---
class TestStudent:
    def test_modules(self):
        r = requests.get(f"{BASE_URL}/api/modules", timeout=20)
        assert r.status_code == 200
        data = r.json()
        print("MODULES:", data)

    def test_questions_no_correct_answer_exposed(self):
        r = requests.get(f"{BASE_URL}/api/questions", params={"module": 3}, timeout=20)
        assert r.status_code == 200
        data = r.json()
        questions = data["questions"] if isinstance(data, dict) else data
        assert isinstance(questions, list)
        assert len(questions) > 0, "Expected validated questions to exist"
        print(f"Total questions returned: {len(questions)}")
        for q in questions[:10]:
            assert "correct_answer" not in q, f"Question {q.get('question_id')} exposes correct_answer!"
            # Should have exactly 3 options a/b/c
            assert "option_a" in q and "option_b" in q and "option_c" in q
            assert "option_d" not in q

    def test_attempt_invalid_option_D(self):
        r = requests.get(f"{BASE_URL}/api/questions", params={"module": 3}, timeout=20)
        assert r.status_code == 200
        data = r.json()
        qs = data["questions"] if isinstance(data, dict) else data
        if not qs:
            pytest.skip("no questions")
        qid = qs[0].get("question_id") or qs[0].get("id")
        r2 = requests.post(f"{BASE_URL}/api/questions/{qid}/attempt",
                           json={"profile_id": "local", "selected": "D"}, timeout=20)
        assert r2.status_code == 400, f"Expected 400 for invalid D, got {r2.status_code}: {r2.text}"

    def test_practice_next(self):
        r = requests.get(f"{BASE_URL}/api/practice/next", params={"profile_id": "local", "module": 3}, timeout=20)
        assert r.status_code in (200, 404), r.text
        if r.status_code == 200:
            data = r.json()
            # should not expose correct_answer
            assert "correct_answer" not in data

    def test_performance(self):
        r = requests.get(f"{BASE_URL}/api/performance", params={"profile_id": "local", "module": 3}, timeout=20)
        assert r.status_code == 200

    def test_mistakes(self):
        r = requests.get(f"{BASE_URL}/api/mistakes", params={"profile_id": "local", "module": 3}, timeout=20)
        assert r.status_code == 200

    def test_study_plan(self):
        r = requests.get(f"{BASE_URL}/api/study-plan", params={"profile_id": "local", "module": 3}, timeout=20)
        assert r.status_code == 200


# --- Exam flow ---
class TestExam:
    def test_create_exam(self):
        r = requests.post(f"{BASE_URL}/api/exams", json={"profile_id": "local", "module": 3}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        print("EXAM CREATED:", {k: data.get(k) for k in ("exam_id", "duration_minutes", "pass_threshold")})
        assert "exam_id" in data
        qs = data.get("questions", [])
        assert len(qs) == 52, f"Expected 52 questions got {len(qs)}"
        for q in qs[:5]:
            assert "option_a" in q and "option_b" in q and "option_c" in q
            assert "option_d" not in q
            assert "correct_answer" not in q
