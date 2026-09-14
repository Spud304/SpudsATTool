"""Fixture data for the browser tests: real ATXXII-legal items from the practice sheet."""

ABSO_FIT = """[Absolution, Octo Ewar Abso]

Prototype Compact Thermal Armor Hardener I
Multispectrum Energized Membrane II
Damage Control II
800mm Crystalline Carbonide Restrained Plates
Heat Sink II
Heat Sink II
Reactive Armor Hardener

50MN Y-T8 Compact Microwarpdrive
Tracking Computer II, Optimal Range Script
Medium F-RX Compact Capacitor Booster, Navy Cap Booster 400

Heavy Beam Laser II, Imperial Navy Multifrequency M
Heavy Beam Laser II, Imperial Navy Multifrequency M
Information Command Burst II, Electronic Hardening Charge
Heavy Beam Laser II, Imperial Navy Multifrequency M
Armor Command Burst II, Armor Reinforcement Charge
Heavy Beam Laser II, Imperial Navy Multifrequency M
Heavy Beam Laser II, Imperial Navy Multifrequency M

Medium Energy Locus Coordinator I
Medium Energy Locus Coordinator I


Light Armor Maintenance Bot I x5
"""

# The same fit with a faction module, illegal under the ATXXII default T1/T2 rule.
FACTION_FIT = ABSO_FIT.replace("[Absolution, Octo Ewar Abso]", "[Absolution, Faction web]").replace(
    "Reactive Armor Hardener", "Federation Navy Stasis Webifier"
)

# OF 99 set 1: exactly 200 points under ATXXII.
OF99_HULLS = [
    "Astarte",
    "Astarte",
    "Absolution",
    "Zealot",
    "Ashimmu",
    "Augoror Navy Issue",
    "Keres",
    "Deacon",
    "Deacon",
    "Maulus",
]
