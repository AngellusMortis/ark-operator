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

* **A Container Engine** -- Docker, Podman, Containerd, whatever should work
* **linux/amd64 Container Host** -- Either via Docker Desktop on Windows/WSL or similar or an actual Linux machine. MacOS (ARM64) will **not** work.
* **2 Volumes, at least 50GB each** -- one for ARK server, one for save data

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
    image: ghcr.io/angellusmortis/ark-server:v0.4.0
    env_file: .env
    environment:
      ARK_SERVER_MAP: BobsMissions_WP
      ARK_SERVER_SESSION_NAME: ASA Club Ark
      ARK_SERVER_RCON_PORT: "27020"
      ARK_SERVER_GAME_PORT: "7777"
      # only enable auto-update on one server
      ARK_SERVER_AUTO_UPDATE: "true"
    healthcheck:
      test: [ "CMD", "sh", "-c", "arkctl server --host 127.0.0.1 rcon ListPlayers" ]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 30s
      start_interval: 10s
    volumes:
      - ./server:/srv/ark/server
      - ./data:/srv/ark/data
      - ./data/maps/BobsMissions_WP/saved:/srv/ark/server/ark/ShooterGame/Saved
      - ./data/maps/BobsMissions_WP/mods:/srv/ark/server/ark/ShooterGame/Binaries/Win64/ShooterGame
      - ./data/lists/PlayersExclusiveJoinList.txt:/srv/ark/server/ark/ShooterGame/Binaries/Win64/PlayersExclusiveJoinList.txt
      - ./data/lists/PlayersJoinNoCheckList.txt:/srv/ark/server/ark/ShooterGame/Binaries/Win64/PlayersJoinNoCheckList.txt
    # should be the UID / GID of your current user
    user: "1000:1000"
    ports:
      - "27020:27020"
      - "7777:7777"
  island:
    image: ghcr.io/angellusmortis/ark-server:v0.4.0
    env_file: .env
    environment:
      ARK_SERVER_MAP: TheIsland_WP
      ARK_SERVER_SESSION_NAME: ASA The Island
      ARK_SERVER_RCON_PORT: "27021"
      ARK_SERVER_GAME_PORT: "7778"
    healthcheck:
      test: [ "CMD", "sh", "-c", "arkctl server --host 127.0.0.1 rcon ListPlayers" ]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 30s
      start_interval: 10s
    volumes:
      # server volume should be read-only on all
      # containers that do not have auto-update on
      - ./server:/srv/ark/server:ro
      - ./data:/srv/ark/data
      - ./data/maps/TheIsland_WP/saved:/srv/ark/server/ark/ShooterGame/Saved
      - ./data/maps/TheIsland_WP/mods:/srv/ark/server/ark/ShooterGame/Binaries/Win64/ShooterGame
      - ./data/lists/PlayersExclusiveJoinList.txt:/srv/ark/server/ark/ShooterGame/Binaries/Win64/PlayersExclusiveJoinList.txt
      - ./data/lists/PlayersJoinNoCheckList.txt:/srv/ark/server/ark/ShooterGame/Binaries/Win64/PlayersJoinNoCheckList.txt
    # should be the UID / GID of your current user
    user: "1000:1000"
    ports:
      - "27021:27021"
      - "7778:7778"
```

#### Setup

```bash
# make all of the directories that will be bind mounted so they are not owned by root
mkdir -p \
    server/ark/ShooterGame/Saved \
    server/ark/ShooterGame/Binaries/Win64/ShooterGame \
    data/maps/BobsMissions_WP/saved \
    data/maps/BobsMissions_WP/mods \
    data/maps/TheIsland_WP/saved \
    data/maps/TheIsland_WP/mods
# let auto-update server initialize everything
docker compose up -d club-ark
# watch logs
docker compose logs club-ark -f
# and wait for it to say "Server: "ASA Club Ark" has successfully started!"

# then start rest of servers
docker compose up -d
```

#### Updating ARK

```bash
# stop all servers
docker compose stop
# run auto-update server
docker compose up -d club-ark
# watch logs
docker compose logs club-ark -f
# and wait for it to say "Server: "ASA Club Ark" has successfully started!"

# then start rest of servers
docker compose up -d
```

### Global GameUserSettings.ini

For any server that is ran that is _not_ Club Ark (map=`BobsMissions_WP`), the container will automatically attempt to merge a `GameUserSettings.ini` that is located at `data/GameUserSettings.ini` with the one in the map specific `saved` directory. So you can set all of your common/shared settings in `data/GameUserSettings.ini` and then your map specific ones in `saved/Config/WindowsServer/GameUserSettings.ini`.

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
| ARK_OP_LOG_FORMAT            | basic       | Logging format. Choices: auto, rich, basic, json |
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
