"""The client's 12-step onboarding process, from signed agreement to live listing.

Edit this list to change the process, then run `python manage.py sync_steps`.
Existing properties get new tasks added; removed tasks are kept for history.

owner_kind: agent | team | external | client
requires_proof: the task can only be ticked with a link or note as evidence.
"""

STEPS = [
    {
        "number": 1, "key": "agreement", "name": "Agreement signed",
        "owner": "Client", "owner_kind": "client", "depends_on": [],
        "tasks": [
            ("Owner signed agreement", False),
            ("Signed PDF received", True),
        ],
    },
    {
        "number": 2, "key": "admin", "name": "Admin setup",
        "owner": "Intake agent", "owner_kind": "agent", "depends_on": [1],
        "tasks": [
            ("Agreement saved to unit Drive folder", True),
            ("Added to portfolio tracker", False),
            ("Lease sent to building management", True),
            ("Keys and fobs registered", False),
            ("Parking registered", False),
            ("Utilities set up", False),
            ("Internet set up", False),
        ],
    },
    {
        "number": 3, "key": "licence", "name": "STR licence and unit email",
        "owner": "Compliance agent", "owner_kind": "agent", "depends_on": [1],
        "tasks": [
            ("Unique unit email created", False),
            ("Licence application submitted", True),
            ("Licence approved", True),
            ("Licence expiry added to tracker", False),
        ],
    },
    {
        "number": 4, "key": "inspection", "name": "Property inspection",
        "owner": "Handyman", "owner_kind": "external", "depends_on": [2],
        "tasks": [
            ("Inspection booked", False),
            ("Condition report generated", True),
            ("Photos saved to Drive", True),
            ("Unit measured", False),
        ],
    },
    {
        "number": 5, "key": "furniture", "name": "Furniture",
        "owner": "Procurement agent", "owner_kind": "agent", "depends_on": [4],
        "tasks": [
            ("Standard furniture list generated", False),
            ("Furniture ordered", False),
            ("Delivery confirmed", False),
        ],
    },
    {
        "number": 6, "key": "supplies", "name": "Supplies and furnishing kit",
        "owner": "Procurement agent", "owner_kind": "agent", "depends_on": [1],
        "tasks": [
            ("Quantities calculated", False),
            ("Price and stock checked", False),
            ("Carts cross-checked against checklist", False),
            ("Order approved and placed", False),
            ("Order document saved", False),
        ],
    },
    {
        "number": 7, "key": "setup_day", "name": "Setup day",
        "owner": "Team", "owner_kind": "team", "depends_on": [5, 6],
        "tasks": [
            ("All deliveries received", False),
            ("Assembly done", False),
            ("Beds made", False),
            ("Staging done", False),
        ],
    },
    {
        "number": 8, "key": "photography", "name": "Photography",
        "owner": "Photographer", "owner_kind": "external", "depends_on": [7],
        "tasks": [
            ("Shoot booked", False),
            ("Photos received (Drive link)", True),
        ],
    },
    {
        "number": 9, "key": "guesty", "name": "Listing build in Guesty",
        "owner": "Listing agent", "owner_kind": "agent", "depends_on": [8],
        "tasks": [
            ("Listing created with nickname", True),
            ("Photos uploaded to Guesty", False),
        ],
    },
    {
        "number": 10, "key": "optimization", "name": "Listing optimization",
        "owner": "Angel Host", "owner_kind": "external", "depends_on": [9],
        "tasks": [
            ("Angel Host emailed: ready to optimize", False),
            ("Optimization confirmed", False),
        ],
    },
    {
        "number": 11, "key": "guest_experience", "name": "Guest experience setup",
        "owner": "Team", "owner_kind": "team", "depends_on": [7],
        "tasks": [
            ("Enso Connect guidebook set up", False),
            ("Lockbox code set", False),
            ("Building buzzer access set", False),
        ],
    },
    {
        "number": 12, "key": "go_live", "name": "Go live",
        "owner": "Client approval", "owner_kind": "client", "depends_on": [3, 10, 11],
        "tasks": [
            ("Final check passed", False),
            ("Live on Airbnb", False),
            ("Live on Booking.com", False),
            ("Live on direct-booking site", False),
        ],
    },
]


def sync_definitions(StepTemplate, TaskTemplate):
    """Create or update step and task templates from STEPS. Safe to run repeatedly.

    Takes the model classes as arguments so migrations can pass historical models.
    """
    by_number = {}
    for s in STEPS:
        step, _ = StepTemplate.objects.update_or_create(
            number=s["number"],
            defaults={"key": s["key"], "name": s["name"], "owner": s["owner"], "owner_kind": s["owner_kind"]},
        )
        by_number[s["number"]] = step
        for order, (title, proof) in enumerate(s["tasks"], start=1):
            TaskTemplate.objects.update_or_create(
                step=step, order=order, defaults={"title": title, "requires_proof": proof}
            )
    for s in STEPS:
        by_number[s["number"]].depends_on.set([by_number[n] for n in s["depends_on"]])
    return by_number
