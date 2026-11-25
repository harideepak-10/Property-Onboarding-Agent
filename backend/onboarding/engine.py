"""Checklist engine: creates each property's checklist and keeps step statuses correct.

Rules
- A step is locked until every step it depends on is done.
- A task in a locked step can't be ticked.
- Some tasks need proof (a link or a note) before they count as done.
- Blocked and waiting are set by people or agents and cleared when resolved or done.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from properties.services import log

from .models import PropertyStep, PropertyTask, StepTemplate, TaskTemplate

S = PropertyStep.Status


def create_checklist(prop):
    """Create the step and task rows for a new property. Safe to call again (adds missing rows)."""
    for tmpl in StepTemplate.objects.prefetch_related("tasks"):
        step, _ = PropertyStep.objects.get_or_create(property=prop, template=tmpl)
        for t in tmpl.tasks.all():
            PropertyTask.objects.get_or_create(step=step, template=t)
    refresh_statuses(prop)


def _compute(step, done_numbers):
    tasks = list(step.tasks.all())
    n_done = sum(1 for t in tasks if t.done)
    if tasks and n_done == len(tasks):
        return S.DONE
    if step.blocked_reason:
        return S.BLOCKED
    deps = [d.number for d in step.template.depends_on.all()]
    if any(n not in done_numbers for n in deps):
        return S.LOCKED
    if step.waiting_note:
        return S.WAITING
    return S.IN_PROGRESS if n_done else S.READY


def refresh_statuses(prop):
    """Recompute every step's status. Returns the step numbers that became unlocked."""
    steps = list(
        PropertyStep.objects.filter(property=prop)
        .select_related("template")
        .prefetch_related("tasks", "template__depends_on")
    )
    # Done-ness doesn't depend on other steps, so compute it first.
    done_numbers = {
        s.template.number for s in steps if s.tasks.all() and all(t.done for t in s.tasks.all())
    }
    unlocked = []
    for step in steps:
        new = _compute(step, done_numbers)
        if new != step.status:
            if step.status == S.LOCKED and new != S.LOCKED:
                unlocked.append(step.template.number)
            step.status = new
            step.completed_at = timezone.now() if new == S.DONE else None
            if new == S.DONE:
                step.waiting_note = ""
            step.save(update_fields=["status", "completed_at", "waiting_note"])
    return unlocked


@transaction.atomic
def set_task(task: PropertyTask, done: bool, actor: str, user=None, proof_url="", proof_note=""):
    step = task.step
    if step.status == S.LOCKED and done:
        missing = [
            f"{d.number}. {d.name}"
            for d in step.template.depends_on.all()
            if not PropertyStep.objects.filter(property=step.property, template=d, status=S.DONE).exists()
        ]
        raise ValidationError(f"Step {step.template.number} is locked until these are done: {', '.join(missing)}.")
    if done and task.template.requires_proof and not (proof_url or proof_note or task.proof_url or task.proof_note):
        raise ValidationError(f"“{task.template.title}” needs proof: add a link or a note.")

    task.done = done
    task.done_at = timezone.now() if done else None
    task.done_by = actor if done else ""
    task.done_by_user = user if done else None
    if proof_url:
        task.proof_url = proof_url
    if proof_note:
        task.proof_note = proof_note
    task.save()

    prop = step.property
    log(prop, f"{'Completed' if done else 'Reopened'}: {task.template.title}", actor=actor, user=user)
    unlocked = refresh_statuses(prop)
    step.refresh_from_db()
    if step.status == S.DONE and done:
        log(prop, f"Step {step.template.number} complete: {step.template.name}", actor="System")
    for n in unlocked:
        name = StepTemplate.objects.get(number=n).name
        log(prop, f"Step {n} unlocked: {name}", actor="System")
    return unlocked


def complete_by_title(prop, step_number: int, titles, actor: str, user=None, proof_note=""):
    """Used by agents/modules to tick specific tasks (e.g. procurement completing step 6)."""
    tasks = PropertyTask.objects.filter(
        step__property=prop, step__template__number=step_number, template__title__in=titles, done=False
    ).select_related("step", "template")
    for t in tasks:
        set_task(t, True, actor=actor, user=user, proof_note=proof_note)


@transaction.atomic
def set_blocked(step: PropertyStep, reason: str, actor: str, user=None):
    step.blocked_reason = reason.strip()
    step.save(update_fields=["blocked_reason"])
    msg = f"Blocked step {step.template.number}: {reason}" if reason else f"Resolved blocker on step {step.template.number}"
    log(step.property, msg, actor=actor, user=user)
    refresh_statuses(step.property)


@transaction.atomic
def set_waiting(step: PropertyStep, note: str, actor: str, user=None):
    step.waiting_note = note.strip()
    step.save(update_fields=["waiting_note"])
    if note:
        log(step.property, f"Waiting on step {step.template.number}: {note}", actor=actor, user=user)
    refresh_statuses(step.property)


def progress(prop) -> int:
    tasks = PropertyTask.objects.filter(step__property=prop)
    total = tasks.count()
    return round(100 * tasks.filter(done=True).count() / total) if total else 0


def current_step(prop):
    """The step that most needs attention: blocked first, then in progress/waiting, then ready."""
    steps = list(PropertyStep.objects.filter(property=prop).select_related("template"))
    for wanted in ([S.BLOCKED], [S.IN_PROGRESS, S.WAITING], [S.READY]):
        for s in steps:
            if s.status in wanted:
                return s
    return None


def overall_state(prop) -> str:
    statuses = set(PropertyStep.objects.filter(property=prop).values_list("status", flat=True))
    if statuses == {S.DONE}:
        return "live"
    if S.BLOCKED in statuses:
        return "blocked"
    cur = current_step(prop)
    if cur and cur.status == S.WAITING:
        return "waiting"
    return "on_track"
