"""ARK Operator config."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address  # required for Pydantic # noqa: TC003
from pathlib import Path  # required for Pydantic # noqa: TC003
from typing import Any, Literal

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
    "@canonical": ["BobsMissions_WP", *ALL_CANONICAL],
    "@canonicalNoClub": ALL_CANONICAL,
    "@official": ["BobsMissions_WP", *ALL_OFFICIAL],
    "@officialNoClub": ALL_OFFICIAL,
}

States = Literal[
    "Initializing",
    "Creating PVCs",
    "Initializing PVCs",
    "Updating PVCs",
    "Creating Resources",
    "Running",
    "Updating Server",
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

    load_balancer_ip: IPv4Address | IPv6Address | None = None
    storage_class: str | None = None
    size: int | str = "50Gi"
    maps: list[str] = ["@canonical"]
    persist: bool = False
    game_port_start: int = 7777
    rcon_port_start: int = 27020
    resources: dict[str, Any] | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_maps(self) -> list[str]:
        """Expand maps into list of full maps."""

        from ark_operator.ark.utils import expand_maps

        return expand_maps(self.maps)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_servers(self) -> dict[str, GameServer]:
        """Return list of all servers."""

        game_port = self.game_port_start
        rcon_port = self.rcon_port_start
        servers = {}
        for map_id in self.all_maps:
            servers[map_id] = GameServer(
                map_id=map_id,
                port=game_port,
                rcon_port=rcon_port,
            )
            game_port += 1
            rcon_port += 1

        return servers


class ArkDataSpec(BaseK8sModel):
    """ArkCluster.spec.data CRD spec."""

    storage_class: str | None = None
    size: int | str = "50Gi"
    persist: bool = True


class ArkClusterSettings(BaseK8sModel):
    """ArkCluster.spec.cluster CRD spec."""

    session_name_format: str = "ASA - {map_name}"
    multihome_ip: str | None = None
    max_players: int = 70
    cluster_id: str = "ark-cluster"
    battleye: bool = True
    allowed_platforms: list[str] = ["ALL"]
    whitelist: bool = False
    params: list[str] = []
    opts: list[str] = []
    mods: list[int] = []

    def get_envs(self, map_id: str) -> dict[str, str]:
        """Get envs for given map."""

        from ark_operator.ark import get_map_name

        map_name = get_map_name(map_id)
        envs = {
            "ARK_SERVER_MAP": map_id,
            "ARK_SERVER_SESSION_NAME": self.session_name_format.format(
                map_name=map_name
            ),
            "ARK_SERVER_AUTO_UPDATE": "false",
            "ARK_SERVER_CLUSTER_MODE": "true",
            "ARK_SERVER_MAX_PLAYERS": str(self.max_players),
            "ARK_SERVER_CLUSTER_ID": self.cluster_id,
            "ARK_SERVER_BATTLEYE": str(self.battleye).lower(),
            "ARK_SERVER_ALLOWED_PLATFORMS": ",".join(self.allowed_platforms),
            "ARK_SERVER_WHITELIST": str(self.whitelist).lower(),
        }

        if self.multihome_ip:
            envs["ARK_SERVER_MULTIHOME"] = self.multihome_ip
        if map_id != "BobsMissions_WP" and self.params:
            envs["ARK_SERVER_PARAMS"] = ",".join(self.params)
        if map_id != "BobsMissions_WP" and self.opts:
            envs["ARK_SERVER_OPTS"] = ",".join(self.opts)
        if map_id != "BobsMissions_WP" and self.mods:
            envs["ARK_SERVER_MODS"] = ",".join(str(m) for m in self.mods)

        return envs


class ArkClusterSpec(BaseK8sModel):
    """ArkCluster.spec CRD spec."""

    server: ArkServerSpec = ArkServerSpec()
    data: ArkDataSpec = ArkDataSpec()
    run_as_user: int = 65535
    run_as_group: int = 65535
    node_selector: dict[str, Any] | None = None
    tolerations: list[dict[str, Any]] | None = None
    global_settings: ArkClusterSettings = ArkClusterSettings()


class ArkClusterStatus(BaseK8sModel):
    """ArkCluster.status CRD spec."""

    ready: bool = False
    state: States | str = "Initializing"
    initalized: bool = False
    stages: dict[ClusterStage, bool] | None = None
    active_volume: Literal["server-a", "server-b"] | None = None
    active_buildid: int | None = None
    latest_buildid: int | None = None

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
