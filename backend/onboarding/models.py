from django.conf import settings
from django.db import models

from properties.models import Property


class StepTemplate(models.Model):
    class OwnerKind(models.TextChoices):
        AGENT = "agent", "AI agent"
        TEAM = "team", "Team"
        EXTERNAL = "external", "Outside party"
        CLIENT = "client", "Client"

    number = models.PositiveSmallIntegerField(unique=True)
    key = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=120)
    owner = models.CharField(max_length=80)
    owner_kind = models.CharField(max_length=10, choices=OwnerKind.choices)
    depends_on = models.ManyToManyField("self", symmetrical=False, blank=True, related_name="unlocks")

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return f"{self.number}. {self.name}"


class TaskTemplate(models.Model):
    step = models.ForeignKey(StepTemplate, on_delete=models.CASCADE, related_name="tasks")
    order = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=200)
    requires_proof = models.BooleanField(default=False)

    class Meta:
        ordering = ["step__number", "order"]
        unique_together = [("step", "order")]

    def __str__(self):
        return self.title


class PropertyStep(models.Model):
    class Status(models.TextChoices):
        LOCKED = "locked", "Not started"
        READY = "ready", "Ready to start"
        IN_PROGRESS = "in_progress", "In progress"
        WAITING = "waiting", "Waiting"
        BLOCKED = "blocked", "Blocked"
        DONE = "done", "Done"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="steps")
    template = models.ForeignKey(StepTemplate, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.LOCKED)
    blocked_reason = models.TextField(blank=True)
    waiting_note = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["template__number"]
        unique_together = [("property", "template")]

    def __str__(self):
        return f"{self.property.nickname} · {self.template}"


class PropertyTask(models.Model):
    step = models.ForeignKey(PropertyStep, on_delete=models.CASCADE, related_name="tasks")
    template = models.ForeignKey(TaskTemplate, on_delete=models.PROTECT, related_name="+")
    done = models.BooleanField(default=False)
    done_at = models.DateTimeField(null=True, blank=True)
    done_by = models.CharField(max_length=80, blank=True)
    done_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    proof_url = models.URLField(blank=True, max_length=500)
    proof_note = models.TextField(blank=True)

    class Meta:
        ordering = ["template__order"]
        unique_together = [("step", "template")]

    def __str__(self):
        return self.template.title
