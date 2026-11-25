from django.contrib import admin

from .models import PropertyStep, PropertyTask, StepTemplate, TaskTemplate


class TaskTemplateInline(admin.TabularInline):
    model = TaskTemplate
    extra = 0


@admin.register(StepTemplate)
class StepTemplateAdmin(admin.ModelAdmin):
    list_display = ["number", "name", "owner", "owner_kind"]
    inlines = [TaskTemplateInline]
    filter_horizontal = ["depends_on"]


class PropertyTaskInline(admin.TabularInline):
    model = PropertyTask
    extra = 0
    fields = ["template", "done", "done_by", "done_at", "proof_url", "proof_note"]
    readonly_fields = ["template"]


@admin.register(PropertyStep)
class PropertyStepAdmin(admin.ModelAdmin):
    list_display = ["property", "template", "status"]
    list_filter = ["status", "template"]
    inlines = [PropertyTaskInline]
