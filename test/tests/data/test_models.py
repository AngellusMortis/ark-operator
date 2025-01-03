"""Test data models."""

from __future__ import annotations

import pytest

from ark_operator.data.models import ArkServerSpec, GameServer


@pytest.mark.parametrize(
    ("input_maps", "expected_maps"),
    [
        (
            ["@canonical"],
            [
                "BobsMissions_WP",
                "TheIsland_WP",
                "ScorchedEarth_WP",
                "Aberration_WP",
                "Extinction_WP",
            ],
        ),
        (
            ["@canonicalNoClub"],
            [
                "TheIsland_WP",
                "ScorchedEarth_WP",
                "Aberration_WP",
                "Extinction_WP",
            ],
        ),
        (
            ["@official"],
            [
                "BobsMissions_WP",
                "TheIsland_WP",
                "TheCenter_WP",
                "ScorchedEarth_WP",
                "Aberration_WP",
                "Extinction_WP",
            ],
        ),
        (
            ["@officialNoClub"],
            [
                "TheIsland_WP",
                "TheCenter_WP",
                "ScorchedEarth_WP",
                "Aberration_WP",
                "Extinction_WP",
            ],
        ),
        (
            ["Astraeos_WP", "@canonicalNoClub", "@official"],
            [
                "BobsMissions_WP",
                "TheIsland_WP",
                "TheCenter_WP",
                "ScorchedEarth_WP",
                "Aberration_WP",
                "Extinction_WP",
                "Astraeos_WP",
            ],
        ),
        (
            ["@canonicalNoClub", "-Aberration_WP"],
            [
                "TheIsland_WP",
                "ScorchedEarth_WP",
                "Extinction_WP",
            ],
        ),
    ],
)
def test_map_expansion(input_maps: list[str], expected_maps: list[str]) -> None:
    """Test expansion shortcuts for maps."""

    spec = ArkServerSpec(maps=input_maps)

    assert spec.all_maps == expected_maps


def test_all_servers() -> None:
    """Test all_servers server spec."""

    spec = ArkServerSpec(maps=["Astraeos_WP", "@canonical"])

    assert spec.all_servers == {
        "BobsMissions_WP": GameServer(
            map_id="BobsMissions_WP", port=7777, rcon_port=27020
        ),
        "TheIsland_WP": GameServer(map_id="TheIsland_WP", port=7778, rcon_port=27021),
        "ScorchedEarth_WP": GameServer(
            map_id="ScorchedEarth_WP", port=7779, rcon_port=27022
        ),
        "Aberration_WP": GameServer(map_id="Aberration_WP", port=7780, rcon_port=27023),
        "Extinction_WP": GameServer(map_id="Extinction_WP", port=7781, rcon_port=27024),
        "Astraeos_WP": GameServer(map_id="Astraeos_WP", port=7782, rcon_port=27025),
    }


@pytest.mark.parametrize(
    ("input_map", "expected_map"),
    [
        ("Aberration_WP", "Aberration"),
        ("BobsMissions_WP", "Club Ark"),
        ("Extinction_WP", "Extinction"),
        ("ScorchedEarth_WP", "Scorched Earth"),
        ("TheCenter_WP", "The Center"),
        ("TheIsland_WP", "The Island"),
        ("TheIsland_SOTF", "The Survival Of The Fittest (The Island)"),
        ("Svartalfheim_WP", "Svartalfheim"),
        ("Astraeos_WP", "Astraeos"),
        ("Amissa_WP", "Amissa"),
        ("Forglar_WP", "Forglar"),
        ("insaluna_WP", "Insaluna"),
        ("Temptress_WP", "Temptress"),
        ("TeamDeathmatch", "Team Deathmatch"),
        ("Reverence_WP", "Reverence"),
        ("Althemia", "Althemia"),
        ("Nyrandil", "Nyrandil"),
        ("Frost_WP", "Frost"),
        ("M_ArkopolisWP", "Arkopolis"),
        ("Appalachia_Official_WP", "Appalachia Official"),
        ("TaeniaStella", "Taenia Stella"),
    ],
)
def test_map_name(input_map: str, expected_map: str) -> None:
    """Get user friendly map name for maps."""

    assert GameServer(map_id=input_map).map_name == expected_map
