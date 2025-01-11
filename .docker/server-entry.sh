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
set +e
IS_READ_ONLY=$(touch $ARK_SERVER_DIR/.perm-test 2>/dev/null 1>&2 && echo "false" || echo "true")
INITIALIZED=$([[ -f ${ARK_SERVER_DIR}/steamapps/appmanifest_2430930.acf && -d ${ARK_DATA_DIR}/maps/${ARK_SERVER_MAP} ]] && echo "true" || echo "false")
set -e

rm -f $ARK_SERVER_DIR/.perm-test 2>/dev/null 1>&2
echo "ark_dir: $ARK_SERVER_DIR"
echo "steam_dir: $ARK_STEAM_DIR"
echo "data_dir: $ARK_DATA_DIR"
echo "read_only: $IS_READ_ONLY"
echo "initialized: $INITIALIZED"

if [[ "${INITIALIZED}" == "false" ]]; then
    if [[ "${IS_READ_ONLY}" == "true" ]]; then
        echo "Server is not initalized and server file system is read-only."
        exit 1
    fi

    echo "Installing ARK ($ARK_SERVER_DIR) and setting up data volume ($ARK_DATA_DIR) for map $ARK_SERVER_MAP..."
    ARK_CLUSTER_SPEC="{\"server\": {\"maps\": [\"${ARK_SERVER_MAP}\"]}}" arkctl cluster init-volumes --single-server /srv/ark
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

arkctl server run $EXTRA_ARGS
