#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

if [[ -z "${ARK_BASE_DIR+x}" ]]; then
    echo "ARK_BASE_DIR not set"
    exit 1
fi

if [[ -z "${ARK_SERVER_DIR+x}" ]]; then
    echo "ARK_SERVER_DIR not set"
    exit 1
fi

if [[ -z "${ARK_STEAM_DIR+x}" ]]; then
    echo "ARK_STEAM_DIR not set"
    exit 1
fi

if [[ -z "${ARK_DATA_DIR+x}" ]]; then
    echo "ARK_DATA_DIR not set"
    exit 1
fi

if [[ -z "${ARK_SERVER_RCON_PASSWORD+x}" ]]; then
    echo "ARK_SERVER_RCON_PASSWORD not set"
    exit 1
fi

if [[ -z "${ARK_SERVER_MAP+x}" ]]; then
    echo "ARK_SERVER_MAP not set"
    exit 1
fi

if [[ -z "${ARK_SERVER_SESSION_NAME+x}" ]]; then
    echo "ARK_SERVER_SESSION_NAME not set"
    exit 1
fi

ARK_SERVER_AUTO_UPDATE=${ARK_SERVER_AUTO_UPDATE:-true}
ARK_SERVER_GAME_PORT=${ARK_SERVER_GAME_PORT:-7777}
ARK_OP_DRY_RUN=${ARK_OP_DRY_RUN:-false}
set +e
IS_READ_ONLY=$(touch $ARK_BASE_DIR/server/.perm-test 2>/dev/null 1>&2 && echo "false" || echo "true")
INITIALIZED=$([[ -f ${ARK_SERVER_DIR}/steamapps/appmanifest_2430930.acf && -d ${ARK_DATA_DIR}/maps/${ARK_SERVER_MAP} ]] && echo "true" || echo "false")
set -e

function shutdown() {
    echo "Shutting down server"
    if [[ "$ARK_OP_DRY_RUN" == "true" ]]; then
        return
    fi
    arkctl server --host 127.0.0.1 shutdown

    # Server exit doesn't close pid for some reason, so lets check that the port is closed and then send SIGTERM to main pid
    while netstat -aln | grep -q $ARK_SERVER_GAME_PORT; do
        sleep 1
    done
    kill -15 $pid
}

if [[ -f $ARK_SERVER_DIR/.perm-test ]]; then
    rm -f $ARK_SERVER_DIR/.perm-test
fi
if [[ -f $ARK_DATA_DIR/maps/$ARK_SERVER_MAP/saved/.started ]]; then
    rm -f $ARK_DATA_DIR/maps/$ARK_SERVER_MAP/saved/.started
fi

echo arkctl version: $(arkctl --version)
echo "log_level: $ARK_OP_LOG_LEVEL"
echo "ark_dir: $ARK_SERVER_DIR"
echo "steam_dir: $ARK_STEAM_DIR"
echo "data_dir: $ARK_DATA_DIR"
echo "read_only: $IS_READ_ONLY"
echo "initialized: $INITIALIZED"
echo "map_id: $ARK_SERVER_MAP"

if [[ "$ARK_OP_DRY_RUN" != "true" && "${INITIALIZED}" == "false" ]]; then
    if [[ "${IS_READ_ONLY}" == "true" ]]; then
        echo "Server is not initalized and server file system is read-only."

        echo "ARK_SERVER_DIR"
        ls -la ${ARK_SERVER_DIR}

        echo ARK_SERVER_DIR/steamapps/appmanifest_2430930.acf
        ls -la ${ARK_SERVER_DIR}/steamapps/appmanifest_2430930.acf

        echo "ARK_DATA_DIR"
        ls -la ${ARK_DATA_DIR}

        echo ARK_DATA_DIR/maps/ARK_SERVER_MAP
        ls -la ${ARK_DATA_DIR}/maps/${ARK_SERVER_MAP}
        exit 1
    fi

    echo "Installing ARK ($ARK_SERVER_DIR) and setting up data volume ($ARK_DATA_DIR) for map $ARK_SERVER_MAP..."
    ARK_CLUSTER_SPEC="{\"server\": {\"maps\": [\"${ARK_SERVER_MAP}\"], \"load_balancer_ip\": \"127.0.0.1\"}}" arkctl cluster init-volumes --single-server /srv/ark
fi

if [[ "${ARK_SERVER_AUTO_UPDATE}" == "true" ]]; then
    if [[ "${IS_READ_ONLY}" == "true" ]]; then
        echo "WARNING: Skipping auto-update because server file system is read-only"
    else
        echo "Checking ARK install ($ARK_SERVER_DIR) for updates..."
        arkctl server install
    fi
fi

EXTRA_ARGS=""
if [[ "${IS_READ_ONLY}" == "true" ]]; then
    EXTRA_ARGS="--immutable"
fi
if [[ "${ARK_SERVER_CLUSTER_MODE}" == "false" ]]; then
    EXTRA_ARGS="$EXTRA_ARGS --map-gus=$ARK_DATA_DIR/maps/$ARK_SERVER_MAP/saved/Config/WindowsServer/GameUserSettings.ini"
    if [[ "${ARK_SERVER_MAP}" != "BobsMissions_WP" ]]; then
        EXTRA_ARGS="$EXTRA_ARGS --global-gus=$ARK_DATA_DIR/GameUserSettings.ini"
    fi
fi


echo "Running ARK: Survival Ascended server"
if [[ "$ARK_OP_DRY_RUN" == "true" ]]; then
    echo "DRY RUN"
    echo arkctl server run $EXTRA_ARGS &
    sleep infinity
else
    arkctl server run $EXTRA_ARGS &
fi

trap 'shutdown' TERM
pid=$!
wait $pid
