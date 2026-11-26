from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from onboarding import views as ob
from procurement import views as pr
from agents import views as ag
from listings import views as li
from operations import views as op

router = DefaultRouter()
router.register("properties", ob.PropertyViewSet, basename="property")
router.register("stores", pr.StoreViewSet, basename="store")
router.register("master-items", pr.MasterItemViewSet, basename="master-item")
router.register("orders", pr.OrderViewSet, basename="order")
router.register("agreements", ag.AgreementViewSet, basename="agreement")
router.register("agent-runs", ag.AgentRunViewSet, basename="agent-run")
router.register("emails", ag.EmailDraftViewSet, basename="email")
router.register("buildings", ag.BuildingViewSet, basename="building")
router.register("compliance-items", ag.ComplianceItemViewSet, basename="compliance-item")
router.register("visits", op.VisitViewSet, basename="visit")
router.register("inspections", op.InspectionViewSet, basename="inspection")
router.register("expenses", op.ExpenseViewSet, basename="expense")
router.register("vendors", op.VendorViewSet, basename="vendor")

api = [
    path("auth/login/", ob.login),
    path("auth/me/", ob.me),
    path("auth/users/", op.users),
    path("auth/users/<int:pk>/", op.user_detail),
    path("properties/<int:pk>/unit/", op.unit_details),
    path("properties/<int:pk>/costs/", op.property_costs),
    path("inspections/<int:pk>/complete/", op.complete_inspection),
    path("inspections/<int:pk>/report/", op.inspection_report),
    path("inspections/<int:pk>/items/<int:item_id>/photo/", op.inspection_item_photo),
    path("order-lines/<int:pk>/track/", op.track_line),
    path("orders/<int:pk>/mark-store/", op.mark_store),
    path("purchasing/", op.purchasing),
    path("contacts/import/<str:kind>/", op.import_contacts),
    path("reports/", op.reports),
    path("reports/<str:key>/", op.report),
    path("digest/", op.digest),
    path("dashboard/", ob.dashboard),
    path("tasks/<int:pk>/set/", ob.set_task),
    path("steps/<int:pk>/block/", ob.block_step),
    path("steps/<int:pk>/wait/", ob.wait_step),
    path("order-lines/<int:pk>/resolve/", pr.resolve_line),
    path("order-lines/<int:pk>/", pr.delete_line),
    path("decor/<int:pk>/", pr.delete_decor),
    path("integrations/", ag.integrations_status),
    path("licences/", ag.licences),
    path("agents/sweeps/", ag.run_sweeps),
    path("properties/<int:pk>/agents/<str:agent>/", ag.run_agent),
    path("properties/<int:pk>/listing/", li.listing),
    path("properties/<int:pk>/photos/", li.upload_photos),
    path("properties/<int:pk>/photos/import-drive/", li.import_drive),
    path("properties/<int:pk>/photos/reorder/", li.reorder),
    path("photos/<int:pk>/", li.photo),
    path("properties/<int:pk>/guest-guide/", li.guest_guide),
    path("properties/<int:pk>/guest-guide/reveal/", li.reveal_guide),
    path("properties/<int:pk>/go-live/", li.go_live),
    path("properties/<int:pk>/go-live/approve/", li.approve_go_live),
    path("properties/<int:pk>/go-live/channels/<str:channel>/", li.confirm_channel),
    path("properties/<int:pk>/go-live/unlist/", li.unlist),
    path("", include(router.urls)),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(api)),
]

if settings.SERVE_MEDIA:
    from django.urls import re_path
    from django.views.static import serve

    urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]
