from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app import main


def test_health_reports_database_available(monkeypatch) -> None:
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, statement):
            assert str(statement) == "SELECT 1"

    monkeypatch.setattr(main.engine, "connect", lambda: FakeConnection())

    response = TestClient(main.app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_reports_database_unavailable(monkeypatch) -> None:
    def fail_connect():
        raise OperationalError("SELECT 1", {}, Exception("offline"))

    monkeypatch.setattr(main.engine, "connect", fail_connect)

    response = TestClient(main.app).get("/health")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
