# ARK Operator

K8s operator for managing ARK: Survival Ascended server clusters. Because this project is to designed to manage all things related to running ARK in k8s, it can be used for a few other things as well.

## Server CLI

You can use the `arkctl server` interface to help you with an ARK server.

### Install

`ark-operator` is not available on PyPi due to some upstream dependencies also not being on PyPi. But it can still be easily installed through [pipx](https://pipx.pypa.io/latest/installation/).

```bash
pipx install git+https://github.com/AngellusMortis/ark-operator@master
```

You can also use the latest container image as well.

```bash
function arkctl() {
    docker pull ghcr.io/angellusmortis/arkctl:master
    docker run --rm run ghcr.io/angellusmortis/arkctl:master "$@"
}
```

### RCON

```bash
arkctl server --host 127.0.0.1 --rcon-password password rcon ListPlayers

arkctl server --host 127.0.0.1 --rcon-password password save
# ^ same as
arkctl server --host 127.0.0.1 --rcon-password password rcon SaveWorld

arkctl server --host 127.0.0.1 --rcon-password password broadcast msg
# ^ same as
arkctl server --host 127.0.0.1 --rcon-password password rcon ServerChat msg

arkctl server --host 127.0.0.1 --rcon-password password shutdown
# ^ same as
arkctl server --host 127.0.0.1 --rcon-password password rcon SaveWorld
arkctl server --host 127.0.0.1 --rcon-password password rcon DoExit
```

## Server Container

### Requirements

* linux/amd64 Host -- Either via Docker Desktop/similar or an actual Linux machine. MacOS (ARM64) will **not** work (it might through Rosetta, but will likely give really bad performance)
* 2 Volumes, at least 50GB each -- one for ARK server, one for save data

### Docker Compose

Below is an example `docker-compose.yml` file:

#### .env
```
# shared envs

ARK_SERVER_RCON_PASSWORD=password
# only enable auto-update on one server
ARK_SERVER_AUTO_UPDATE=false
```

#### docker-compose.yml
```yml
services:
  club-ark:
    image: ghcr.io/angellusmortis/ark-server:master
    env_file: .env
    environment:
      ARK_SERVER_MAP: BobsMissions_WP
      ARK_SERVER_SESSION_NAME: ASA Club Ark
      ARK_SERVER_RCON_PORT: "27020"
      ARK_SERVER_GAME_PORT: "7777"
      # only enable auto-update on one server
      ARK_SERVER_AUTO_UPDATE: "true"
    volumes:
      - ./server:/srv/ark/server
      - ./data:/srv/ark/data
      - ./data/maps/BobsMissions_WP/saved:/srv/ark/server/ark/ShooterGame/Saved
      - ./data/maps/BobsMissions_WP/mods:/srv/ark/server/ark/ShooterGame/Binaries/Win64/ShooterGame
    ports:
      - "27020:27020"
      - "7777:7777"
  island:
    image: ghcr.io/angellusmortis/ark-server:master
    env_file: .env
    environment:
      ARK_SERVER_MAP: TheIsland_WP
      ARK_SERVER_SESSION_NAME: ASA The Island
      ARK_SERVER_RCON_PORT: "27021"
      ARK_SERVER_GAME_PORT: "7778"
    volumes:
      # server volume should be read-only on all
      # containers that do not have auto-update on
      - ./server:/srv/ark/server:ro
      - ./data:/srv/ark/data
      - ./data/maps/TheIsland_WP/saved:/srv/ark/server/ark/ShooterGame/Saved
      - ./data/maps/TheIsland_WP/mods:/srv/ark/server/ark/ShooterGame/Binaries/Win64/ShooterGame
    ports:
      - "27021:27021"
      - "7778:7778"
```

### Environment Variables

Below a list of available environment variables.

| env                          | default     | description                                      |
|------------------------------|-------------|--------------------------------------------------|
| ARK_SERVER_RCON_PASSWORD     |             | Required. RCON / Admin password for the server.  |
| ARK_SERVER_MAP               |             | Required. The map for the server.                |
| ARK_SERVER_SESSION_NAME      |             | Required. Session name for server.               |
| ARK_SERVER_AUTO_UPDATE       | true        | If server should auto-update (Steam) or not.     |
| ARK_SERVER_RCON_PORT         | 27020       | The RCON port for server.                        |
| ARK_SERVER_GAME_PORT         | 7777        | The game port for the server.                    |
| ARK_SERVER_MULTIHOME         |             | Multihome IP for the server. Use when you public IP does not match the IP players should connect to. |
| ARK_SERVER_MAX_PLAYERS       | 70          | Max number of players allowed.                   |
| ARK_SERVER_CLUSTER_ID        | ark-cluster | Cluster ID for server cluster.                   |
| ARK_SERVER_BATTLEYE          | true        | If BattlEye should be enabled.                   |
| ARK_SERVER_ALLOWED_PLATFORMS | ALL         | Allow platforms for server. Comma list.          |
| ARK_SERVER_WHITELIST         | false       | If server should have whitelist.                 |
| ARK_SERVER_PARAMS            |             | Comma list of additional params (?)              |
| ARK_SERVER_OPTS              |             | Additional list of options (-)                   |
| ARK_SERVER_MODS              |             | Additional list of mods (Club ARK mod automatically added if that is the map). |
| ARK_OP_LOG_FORMAT            | auto        | Logging format. Choices: auto, rich, basic, json |
| ARK_OP_LOG_LEVEL             | INFO        | Log level. Choices: DEBUG, INFO, WARNING, ERROR  |

### Managed Parameters, Options and Settings

`arkctl` manages a lot of stuff for you. As a result you **MUST NOT** set any of the managed parameters, options or settings. All of these can be managed through the above environment variables.

See the [ARK wiki](https://ark.wiki.gg/wiki/Server_configuration) for full list of settings.

#### Managed Parameters (?)

- SessionName
- RCONEnabled
- RCONPort
- ServerAdminPassword

#### Managed Options (-)

- port
- WinLiveMaxPlayers
- clusterid
- ClusterDirOverride
- NoTransferFromFiltering
- ServerPlatform
- NoBattlEye
- exclusivejoin
- MULTIHOME
- mods

#### Managed GameUserSettings

- ServerSettings -> RCONEnabled
- ServerSettings -> RCONPort
- ServerSettings -> ServerAdminPassword
- SessionSettings -> Port
- SessionSettings -> SessionName
- SessionSettings -> MultiHome
- MultiHome -> Multihome

## K8s Operator

> [!WARNING]
> WIP come back later.

## Development

> [!WARNING]
> WIP come back later.
