from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from onboarding import views as ob
from procurement import views as pr
from agents import views as ag
from listings import views as li

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

api = [
    path("auth/login/", ob.login),
    path("auth/me/", ob.me),
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

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
