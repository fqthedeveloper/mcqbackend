# mcqapp/practice_service.py

import random
from mcqapp.models import PracticeQuestion, PracticeRun, PracticeAnswer
from mcqapp.practice_config import PRACTICE_RULES


def start_practice(student, subject, difficulty):
    if difficulty not in PRACTICE_RULES:
        return None, "Invalid difficulty selected"

    rule = PRACTICE_RULES[difficulty]

    qs = list(
        PracticeQuestion.objects.filter(
            subject=subject,
            difficulty=difficulty
        ).select_related("question")
    )

    if not qs:
        return None, f"No practice questions found for {difficulty}"

    if len(qs) < rule["count"]:
        return None, (
            f"Not enough practice questions. "
            f"Required {rule['count']}, available {len(qs)}"
        )

    random.shuffle(qs)
    selected = qs[: rule["count"]]

    run = PracticeRun.objects.create(
        student=student,
        subject=subject,
        difficulty=difficulty,
        duration_minutes=rule["duration"],
    )

    return run, selected


def submit_practice_answer(run, practice_question, selected_answers):
    correct = set(selected_answers.split(",")) == set(
        practice_question.question.correct_option.split(",")
    )

    PracticeAnswer.objects.update_or_create(
        run=run,
        practice_question=practice_question,
        defaults={
            "selected_answers": selected_answers,
            "is_correct": correct,
        }
    )


def finish_practice(run):
    answers = PracticeAnswer.objects.filter(run=run)
    total = answers.count()
    correct = answers.filter(is_correct=True).count()

    return {
        "total": total,
        "correct": correct,
        "wrong": total - correct,
        "accuracy": round((correct / total) * 100, 2) if total else 0,
    }
