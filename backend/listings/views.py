from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from onboarding.views import domain_errors
from properties.models import Property

from . import services
from .guesty import Guesty
from .models import Photo, PhotoSet
from .serializers import ListingProfileSerializer, PhotoSerializer, PhotoSetSerializer


def listing_payload(prop):
    ps = services.current_set(prop)
    return {
        "property": prop.id,
        "nickname": prop.nickname,
        "guesty_listing_id": prop.guesty_listing_id,
        "profile": ListingProfileSerializer(services.profile(prop)).data,
        "photo_set": PhotoSetSerializer(ps).data if ps else None,
        "previous_sets": PhotoSetSerializer(prop.photo_sets.filter(is_current=False), many=True).data,
        "readiness": services.readiness(prop),
        "channels": services.channels(prop),
        "min_photos": settings.LISTINGS["MIN_PHOTOS"],
        "rooms": Photo.ROOMS,
        "amenity_options": services.DEFAULT_AMENITIES + ["Free parking on premises", "Gym", "Pool", "Elevator", "Balcony",
                                                         "Dishwasher", "Coffee maker", "Crib", "Pets allowed"],
    }


@api_view(["GET", "PATCH"])
@domain_errors
def listing(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    if request.method == "PATCH":
        ser = ListingProfileSerializer(services.profile(prop), data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
    return Response(listing_payload(prop))


@api_view(["POST"])
@parser_classes([MultiPartParser])
@domain_errors
def upload_photos(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    files = [(f.name, f.read()) for f in request.FILES.getlist("files")]
    kind = request.data.get("kind") or PhotoSet.Kind.SHOOT
    if kind not in PhotoSet.Kind.values:
        return Response({"detail": "Unknown photo set type."}, status=400)
    services.add_photos(prop, files, kind=kind, new_set=request.data.get("new_set") in ("1", "true"), user=request.user)
    return Response(listing_payload(prop), status=201)


@api_view(["POST"])
@parser_classes([JSONParser])
@domain_errors
def import_drive(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    services.import_from_drive(prop, request.data.get("url", ""), kind=request.data.get("kind") or "shoot", user=request.user)
    return Response(listing_payload(prop), status=201)


@api_view(["PATCH", "DELETE"])
def photo(request, pk):
    p = get_object_or_404(Photo.objects.select_related("photo_set__property"), pk=pk)
    prop = p.photo_set.property
    if request.method == "DELETE":
        was_cover = p.is_cover
        p.image.delete(save=False)
        p.delete()
        if was_cover:
            nxt = p.photo_set.photos.first()
            if nxt:
                services.set_cover(nxt)
        return Response(listing_payload(prop))
    if request.data.get("is_cover"):
        services.set_cover(p)
    ser = PhotoSerializer(p, data={k: v for k, v in request.data.items() if k in ("room", "caption")}, partial=True)
    ser.is_valid(raise_exception=True)
    ser.save()
    return Response(listing_payload(prop))


@api_view(["POST"])
def reorder(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    ps = services.current_set(prop)
    if ps:
        services.reorder(ps, request.data.get("ids", []))
    return Response(listing_payload(prop))


def guesty_status():
    return "live" if Guesty().live else "dry_run"


# ---------- guest guide and go-live ----------
from agents.serializers import AgentRunSerializer  # noqa: E402
from onboarding.views import actor_name  # noqa: E402

from . import golive  # noqa: E402
from .models import GuestGuide  # noqa: E402

GUIDE_FIELDS = [f.name for f in GuestGuide._meta.fields if f.name not in ("id", "property")]


def guide_payload(prop):
    g = golive.guide(prop)
    data = {f: getattr(g, f) for f in GUIDE_FIELDS}
    for f in GuestGuide.SECRET_FIELDS:
        data[f] = golive.MASK if data[f] else ""
    data["missing"] = g.missing()
    step = prop.steps.get(template__number=11)
    data["step"] = {"status": step.status, "tasks": [{"title": t.template.title, "done": t.done} for t in step.tasks.select_related("template")]}
    return data


@api_view(["GET", "PATCH"])
@parser_classes([JSONParser])
def guest_guide(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    notes = []
    if request.method == "PATCH":
        _, notes = golive.update_guide(prop, request.data, user=request.user)
    return Response({**guide_payload(prop), "notes": notes})


@api_view(["POST"])
def reveal_guide(request, pk):
    return Response(golive.reveal(get_object_or_404(Property, pk=pk), user=request.user))


def golive_payload(prop):
    return {**golive.preflight(prop), "channels": services.channels(prop), "guesty_listing_id": prop.guesty_listing_id}


@api_view(["GET"])
def go_live(request, pk):
    return Response(golive_payload(get_object_or_404(Property, pk=pk)))


@api_view(["POST"])
@domain_errors
def approve_go_live(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    run = golive.approve(prop, user=request.user)
    return Response({**golive_payload(prop), "run": AgentRunSerializer(run).data})


@api_view(["POST"])
@domain_errors
def confirm_channel(request, pk, channel):
    prop = get_object_or_404(Property, pk=pk)
    golive.confirm_channel(prop, channel, user=request.user)
    return Response(golive_payload(prop))


@api_view(["POST"])
@domain_errors
def unlist(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    golive.unlist(prop, request.data.get("reason", ""), user=request.user)
    return Response(golive_payload(prop))
