"""Persistence and concurrency rules for questionnaire attempts."""

from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import select

from app.models import User
from app.questionnaire_catalog import (
    CATALOG_VERSION,
    INTERPRETATION_VERSION,
    QUESTION_BY_ID,
    QUESTIONS,
)
from app.questionnaire_models import (
    QuestionnaireAnswer,
    QuestionnaireAttempt,
    QuestionnaireOperation,
    now,
)


def validate_answer(question_id, answer):
    question = QUESTION_BY_ID.get(question_id)
    if (
        not question
        or not isinstance(answer, dict)
        or set(answer) - {"status", "value"}
    ):
        raise HTTPException(422, "Некорректный ответ")
    status = answer.get("status")
    value = answer.get("value")
    if status in ("skipped", "unsure"):
        if value is not None:
            raise HTTPException(422, "Для пропуска значение не требуется")
        return {"status": status, "value": None}
    if status != "answered":
        raise HTTPException(422, "Некорректное состояние ответа")
    if question["format"] == "scale":
        if type(value) is not int or not 1 <= value <= 5:
            raise HTTPException(422, "Выберите оценку от 1 до 5")
    else:
        options = {option["id"] for option in question["options"]}
        if (
            not isinstance(value, list)
            or not all(isinstance(v, str) for v in value)
            or not 1 <= len(value) <= question["max_choices"]
            or len(set(value)) != len(value)
            or not set(value) <= options
        ):
            raise HTTPException(422, "Выберите допустимые варианты")
        value = sorted(value)
    return {"status": status, "value": value}


def signals(answers):
    values = defaultdict(list)
    for question_id, answer in answers.items():
        if answer["status"] != "answered":
            continue
        question = QUESTION_BY_ID[question_id]
        if question["format"] == "scale":
            for signal in set(question["signals"]):
                values[signal].append(answer["value"])
        else:
            selected = set(answer["value"])
            traits = {
                signal
                for option in question["options"]
                if option["id"] in selected
                for signal in option["signals"]
            }
            for signal in traits:
                values[signal].append(4)
    return {key: sum(items) / len(items) for key, items in values.items()}


class QuestionnaireService:
    def __init__(self, session, user_id):
        self.session = session
        self.user_id = user_id

    def attempts(self):
        return list(
            self.session.scalars(
                select(QuestionnaireAttempt)
                .where(QuestionnaireAttempt.user_id == self.user_id)
                .order_by(QuestionnaireAttempt.number.desc())
            )
        )

    def get(self, attempt_id):
        attempt = self.session.scalar(
            select(QuestionnaireAttempt).where(
                QuestionnaireAttempt.id == attempt_id,
                QuestionnaireAttempt.user_id == self.user_id,
            )
        )
        if attempt is None:
            raise HTTPException(404, "Попытка не найдена")
        return attempt

    def answers(self, attempt):
        return {
            row.question_id: row.answer
            for row in self.session.scalars(
                select(QuestionnaireAnswer).where(
                    QuestionnaireAnswer.attempt_id == attempt.id
                )
            )
        }

    def view(self, attempt):
        return {
            "id": attempt.id,
            "number": attempt.number,
            "catalog_version": attempt.catalog_version,
            "interpretation_version": attempt.interpretation_version,
            "status": attempt.status,
            "current_question_id": attempt.current_question_id,
            "revision": attempt.revision,
            "started_at": attempt.started_at.isoformat(),
            "completed_at": attempt.completed_at.isoformat()
            if attempt.completed_at
            else None,
            "answers": self.answers(attempt),
        }

    def state(self):
        attempts = self.attempts()
        current = next((a for a in attempts if a.status == "in_progress"), None)
        completed = next((a for a in attempts if a.status == "completed"), None)
        return {
            "status": "in_progress"
            if current
            else "completed"
            if completed
            else "not_started",
            "current": self.view(current) if current else None,
            "last_completed": self.view(completed) if completed else None,
        }

    def execute(self, request_id, operation, request, callback):
        self.session.execute(
            select(User.id).where(User.id == self.user_id).with_for_update()
        ).scalar_one()
        previous = self.session.scalar(
            select(QuestionnaireOperation).where(
                QuestionnaireOperation.user_id == self.user_id,
                QuestionnaireOperation.request_id == request_id,
            )
        )
        if previous:
            if previous.operation != operation or previous.request != request:
                raise HTTPException(409, "Request ID has different content")
            return previous.result, previous.status_code
        result, code = callback()
        self.session.add(
            QuestionnaireOperation(
                user_id=self.user_id,
                request_id=request_id,
                operation=operation,
                request=request,
                result=result,
                status_code=code,
            )
        )
        self.session.commit()
        return result, code

    def start(self, retake):
        attempts = self.attempts()
        current = next((a for a in attempts if a.status == "in_progress"), None)
        if current:
            return self.view(current), 200
        if attempts and not retake:
            raise HTTPException(409, "Для повторного прохождения подтвердите начало")
        attempt = QuestionnaireAttempt(
            user_id=self.user_id,
            number=(attempts[0].number + 1 if attempts else 1),
            catalog_version=CATALOG_VERSION,
            interpretation_version=INTERPRETATION_VERSION,
            status="in_progress",
            current_question_id=QUESTIONS[0]["id"],
            revision=0,
        )
        self.session.add(attempt)
        self.session.flush()
        return self.view(attempt), 201

    def progress(self, attempt_id, revision, current_question_id, update):
        attempt = self.get(attempt_id)
        self.check_revision(attempt, revision)
        if current_question_id not in QUESTION_BY_ID:
            raise HTTPException(422, "Неизвестный вопрос")
        if update is not None:
            question_id = update["question_id"]
            answer = validate_answer(question_id, update["answer"])
            row = self.session.scalar(
                select(QuestionnaireAnswer).where(
                    QuestionnaireAnswer.attempt_id == attempt.id,
                    QuestionnaireAnswer.question_id == question_id,
                )
            )
            if row is None:
                row = QuestionnaireAnswer(
                    attempt_id=attempt.id, question_id=question_id, answer=answer
                )
                self.session.add(row)
            else:
                row.answer = answer
        attempt.current_question_id = current_question_id
        attempt.revision += 1
        self.session.flush()
        return self.view(attempt), 200

    def complete(self, attempt_id, revision):
        attempt = self.get(attempt_id)
        self.check_revision(attempt, revision)
        if len(self.answers(attempt)) != len(QUESTIONS):
            raise HTTPException(409, "Ответьте или пропустите каждый вопрос")
        attempt.status = "completed"
        attempt.completed_at = now()
        attempt.revision += 1
        self.session.flush()
        return self.view(attempt), 200

    @staticmethod
    def check_revision(attempt, revision):
        if attempt.status != "in_progress" or attempt.revision != revision:
            raise HTTPException(409, "Состояние опроса изменилось; обновите страницу")

    def results(self, attempt_id):
        attempt = self.get(attempt_id)
        if attempt.status != "completed":
            raise HTTPException(409, "Опрос ещё не завершён")
        return {**self.view(attempt), "interests": signals(self.answers(attempt))}
