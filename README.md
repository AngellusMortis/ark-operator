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

> [!WARNING]
> WIP come back later.

## K8s Operator

> [!WARNING]
> WIP come back later.

## Development

> [!WARNING]
> WIP come back later.
