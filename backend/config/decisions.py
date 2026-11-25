"""Decisions we made on the client's open questions, so the build isn't blocked.

Each one is a sensible default and can be changed (setting, env var or admin) without code changes
unless noted. Shown in the app on the Decisions page; the client confirms or overrides.
"""

DECISIONS = [
    {
        "area": "Supplies", "question": "Glasses: per bed or per guest?",
        "decision": "Per guest. Wine and drinking glasses use a new 'per guest (sleeps)' rule, 1 each per guest.",
        "why": "A queen bed is two guests; per-guest matches how many people actually drink. Per-bed under-counts sofa beds.",
        "change": "Master list → rule and multiplier on each item.",
    },
    {
        "area": "Supplies", "question": "How is 'sleeps' worked out?",
        "decision": "2 per king/queen/double bed, 1 per twin, 2 per sofa bed. Can be overridden per unit.",
        "why": "Matches the usual Airbnb occupancy count and the Guesty 'accommodates' field.",
        "change": "UNIT.SLEEPS_PER_BED / SLEEPS_PER_SOFA_BED in settings; 'Sleeps override' on the Unit tab.",
    },
    {
        "area": "Supplies", "question": "Do sofa beds count as beds for purchasing?",
        "decision": "For bedding and pillows yes (double size); for mattresses and bed frames no.",
        "why": "A sofa bed has its own mattress but needs sheets, a duvet and pillows.",
        "change": "Master list → 'Count sofa beds' on each per-bed item; UNIT.SOFA_BED_SIZE.",
    },
    {
        "area": "Supplies", "question": "Different bed sizes in one unit (e.g. twins in the second bedroom)?",
        "decision": "Each bedroom records its bed size and count. Size-specific items (mattress, frame, sheets, duvet) only count beds of their size.",
        "why": "Otherwise a twin room gets queen sheets.",
        "change": "Unit tab → bedrooms; master list → 'Bed size' on each item.",
    },
    {
        "area": "Supplies", "question": "Blackout curtains: standard kit or decor?",
        "decision": "Standard kit, one pair per bedroom. Living-room curtains are decor (picked by hand).",
        "why": "Bedroom blackout is a guest-review must-have; living room style varies.",
        "change": "Master list.",
    },
    {
        "area": "Supplies", "question": "What does 'typical price' mean, and when is an item flagged?",
        "decision": "Typical price is the master-list reference price, updated whenever the list is re-imported. Flag at more than 25% over it, or out of stock.",
        "why": "Simple to maintain from the client's sheet.",
        "change": "PROCUREMENT.OVER_PRICE_THRESHOLD (0.25).",
    },
    {
        "area": "Purchasing", "question": "Who places the orders and how do we know they arrived?",
        "decision": "The team checks out each store cart, then marks it ordered (with the store order number and expected date). Each line is marked delivered, missing or damaged on arrival. Missing/damaged lines roll into a top-up order.",
        "why": "Stores don't offer an ordering API for personal accounts; this keeps a full record per property.",
        "change": "—",
    },
    {
        "area": "Purchasing", "question": "Who can approve an order?",
        "decision": "Managers and admins. Coordinators prepare orders but can't approve them.",
        "why": "Spending needs a second person.",
        "change": "Users page → role.",
    },
    {
        "area": "Admin setup", "question": "Which utilities must be set up before step 2 is done?",
        "decision": "Electricity and internet. Water and gas are tracked but optional (often included by the building).",
        "why": "Most Toronto condos include water and heat; hydro and internet are always the unit's.",
        "change": "REQUIRED_UTILITIES env var (comma-separated).",
    },
    {
        "area": "Admin setup", "question": "When are 'Keys and fobs registered' and 'Parking registered' done?",
        "decision": "Automatically when the Unit tab shows at least one key or fob and the building has confirmed registration; parking when registered (or the unit has no parking).",
        "why": "Ties the checklist to real data instead of a manual tick.",
        "change": "—",
    },
    {
        "area": "Inspection", "question": "What does the inspection cover?",
        "decision": "A standard checklist per room (entry, kitchen, living, each bedroom, each bathroom, laundry, safety) with condition, action and estimated cost, plus room measurements. Rooms in feet, windows in inches.",
        "why": "Measurements drive rugs and curtains; the report becomes the condition record for the owner.",
        "change": "Items can be added per inspection; the default list is in operations/services.py.",
    },
    {
        "area": "Photography", "question": "When do we chase the photographer?",
        "decision": "3 days after the shoot with no Drive link, a follow-up email is drafted for approval.",
        "why": "Photos are the step most often delayed before listing.",
        "change": "PHOTO_FOLLOWUP_DAYS env var.",
    },
    {
        "area": "Listing", "question": "Nickname format",
        "decision": "Kept as A<sequence>-<CITY>-<STREET3><UNIT>, e.g. A37313-TOR-BAY617, numbering from 37331.",
        "why": "Matches the example the client gave.",
        "change": "ONBOARDING.NICKNAME_START; properties/services.py for the format.",
    },
    {
        "area": "Licence", "question": "Unit email format and licence documents",
        "decision": "Unit email is {street}{unit}@domain. The licence packet list stays a placeholder until the client sends the City of Toronto requirements.",
        "why": "The domain and the city's list must come from the client.",
        "change": "UNIT_EMAIL_DOMAIN / UNIT_EMAIL_PATTERN; AGENTS.LICENCE_PACKET.",
    },
    {
        "area": "Team", "question": "Who can do what?",
        "decision": "Four roles: admin (everything + users), manager (approvals, sending emails, go-live, master list), coordinator (day-to-day work), viewer (read-only).",
        "why": "Keeps spending, outgoing email and going live behind a manager.",
        "change": "Users page.",
    },
    {
        "area": "Notifications", "question": "How does the team hear about problems?",
        "decision": "A daily digest email to the ops inbox (blocked steps, late deliveries, visits this week, expiring licences, drafts waiting). Optional Slack via a webhook.",
        "why": "One message a day instead of many alerts.",
        "change": "DIGEST_TO, SLACK_WEBHOOK_URL env vars; run_agent_sweeps --digest.",
    },
    {
        "area": "Costs", "question": "What counts in the cost per property?",
        "decision": "Approved purchases (actual price when entered, otherwise the cart price), decor, and expenses (licence fee, inspection, photography, labour, repairs, building fees). Monthly utilities are shown separately.",
        "why": "Separates one-time onboarding cost from running cost.",
        "change": "—",
    },
]
