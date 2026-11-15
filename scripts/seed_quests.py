"""Install the first quest without replacing existing content or player data."""

from sqlalchemy import select

from app.database import SessionLocal
from app.models import CareerDirection
from app.quest_models import QuestDefinition, QuestObjective


def seed(session):
    if session.scalar(
        select(QuestDefinition).where(QuestDefinition.slug == "server-on-vacation")
    ):
        return
    direction = session.scalar(
        select(CareerDirection).where(CareerDirection.slug == "backend")
    )
    quest = QuestDefinition(
        slug="server-on-vacation",
        title="Сервер ушёл в отпуск",
        description=(
            "Помогите Борису выяснить причину сбоя и восстановить работу сервера."
        ),
        category="professional",
        direction_id=direction.id if direction else None,
        giver_npc_id="boris",
        location_slug="backend",
        availability_config={},
        is_published=True,
    )
    session.add(quest)
    session.flush()
    steps = [
        (
            "Осмотрите сервер",
            "Проверьте состояние сервера.",
            "object_inspected",
            "backend_server",
            {},
        ),
        (
            "Изучите терминал",
            "Прочитайте диагностический журнал.",
            "terminal_investigated",
            "backend_terminal",
            {},
        ),
        (
            "Исправьте конфигурацию",
            "Настройте порт сервера и запустите проверку.",
            "terminal_problem_fixed",
            "backend_terminal",
            {"port": 8080},
        ),
        (
            "Доложите Борису",
            "Расскажите Борису о восстановлении сервера.",
            "npc_reported",
            "boris",
            {},
        ),
    ]
    for index, (title, description, kind, target, payload) in enumerate(steps):
        session.add(
            QuestObjective(
                quest_id=quest.id,
                title=title,
                description=description,
                order_index=index,
                objective_type=kind,
                target_key=target,
                required_count=1,
                validation_config={"payload": payload},
                is_required=True,
            )
        )
    session.commit()


if __name__ == "__main__":
    with SessionLocal() as session:
        seed(session)
