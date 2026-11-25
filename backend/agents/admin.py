from django.contrib import admin

from .models import AgentRun, AgreementDocument, Building, ComplianceItem, EmailDraft, LicenceReminder


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ["__str__", "street_number", "street_name", "management_company", "management_email"]
    search_fields = ["name", "street_name", "management_company"]


@admin.register(AgreementDocument)
class AgreementAdmin(admin.ModelAdmin):
    list_display = ["original_name", "status", "method", "property", "uploaded_at"]
    list_filter = ["status", "method"]


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    list_display = ["agent", "property", "status", "started_at", "finished_at"]
    list_filter = ["agent", "status"]


@admin.register(EmailDraft)
class EmailDraftAdmin(admin.ModelAdmin):
    list_display = ["subject", "property", "kind", "status", "to", "created_at", "sent_at"]
    list_filter = ["kind", "status"]


admin.site.register(ComplianceItem)
admin.site.register(LicenceReminder)
