"""ARK Operator config."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path  # required for Pydantic # noqa: TC003
from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings

from ark_operator.data.types import ClusterStage  # required for Pydantic # noqa: TC001

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=r"invalid escape sequence '\\-'")
    warnings.filterwarnings("ignore", message=r"invalid escape sequence '\\\('")
    warnings.filterwarnings("ignore", message=r"invalid escape sequence '\\d'")
    warnings.filterwarnings("ignore", category=DeprecationWarning)


ALL_CANONICAL = ["TheIsland_WP", "ScorchedEarth_WP", "Aberration_WP", "Extinction_WP"]
ALL_OFFICIAL = [
    "TheIsland_WP",
    "TheCenter_WP",
    "ScorchedEarth_WP",
    "Aberration_WP",
    "Extinction_WP",
]
MAP_LOOPUP_MAP = {
    "canonical": ["BobsMissions_WP", *ALL_CANONICAL],
    "canonicalNoClub": ALL_CANONICAL,
    "official": ["BobsMissions_WP", *ALL_OFFICIAL],
    "officialNoClub": ALL_OFFICIAL,
}

States = Literal[
    "Initializing", "Creating PVCs", "Updating PVCs", "Deleting PVCs", "Running"
]


class BaseK8sModel(BaseModel):
    """Base model for k8s spec."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class Config(BaseSettings):
    """ARK Operator config."""

    steam_install_dir: Path
    ark_a_install_dir: Path
    ark_b_install_dir: Path


@dataclass
class GameServer:
    """Wrapper for game server representation."""

    map_id: str
    port: int = 7777
    rcon_port: int = 27020

    @property
    def map_name(self) -> str:
        """Get user friendly name for map."""

        from ark_operator.ark import get_map_name

        return get_map_name(self.map_id)


class ArkServerSpec(BaseK8sModel):
    """ArkCluster.spec.server CRD spec."""

    storage_class: str | None = None
    size: int | str = "50Gi"
    maps: list[str] = ["canonical"]
    persist: bool = False
    game_port_start: int = 7777
    rcon_port_start: int = 27020

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_maps(self) -> list[str]:
        """Expand maps into list of full maps."""

        maps = set()
        for map_id in self.maps:
            if expanded_maps := MAP_LOOPUP_MAP.get(map_id):
                maps |= set(expanded_maps)
            else:
                maps.add(map_id)

        ordered_maps = []
        map_order = MAP_LOOPUP_MAP["official"]
        for map_id in map_order:
            if map_id in maps:
                ordered_maps.append(map_id)
                maps.remove(map_id)
        ordered_maps += list(maps)

        return ordered_maps

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_servers(self) -> list[GameServer]:
        """Return list of all servers."""

        game_port = self.game_port_start
        rcon_port = self.rcon_port_start
        servers = []
        for map_id in self.all_maps:
            servers.append(
                GameServer(
                    map_id=map_id,
                    port=game_port,
                    rcon_port=rcon_port,
                )
            )
            game_port += 1
            rcon_port += 1

        return servers


class ArkDataSpec(BaseK8sModel):
    """ArkCluster.spec.data CRD spec."""

    storage_class: str | None = None
    size: int | str = "50Gi"
    persist: bool = True


class ArkClusterSpec(BaseK8sModel):
    """ArkCluster.spec CRD spec."""

    server: ArkServerSpec = ArkServerSpec()
    data: ArkDataSpec = ArkDataSpec()


class ArkClusterStatus(BaseK8sModel):
    """ArkCluster.status CRD spec."""

    ready: bool = False
    state: States | str = "Initializing"
    stages: dict[ClusterStage, bool] | None = None

    @property
    def is_error(self) -> bool:
        """Check if state is currently an error."""

        return self.state.startswith("Error: ")

    def is_stage_completed(self, stage: ClusterStage) -> bool:
        """Check if stage is completed."""

        self.stages = self.stages or {}
        return self.stages.get(stage, False)

    def mark_stage_complete(self, stage: ClusterStage) -> dict[str, bool]:
        """Mark stage complete."""

        self.stages = self.stages or {}
        self.stages[stage] = True
        return {stage.value: True}
