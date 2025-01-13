FROM python:3.12-slim-bookworm AS base

LABEL org.opencontainers.image.source=https://github.com/AngellusMortis/ark-operator

ENV PYTHONUNBUFFERED=1
ENV UV_SYSTEM_PYTHON=true
ENV UV_PIP_SYSTEM_PYTHON=true
ARG TARGETPLATFORM

RUN addgroup --system --gid 1000 app \
    && adduser --system --shell /bin/bash --uid 1000 --home /home/app --ingroup app app

RUN --mount=type=cache,mode=0755,id=apt-cache-TARGETPLATFORM,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,mode=0755,id=apt-data-TARGETPLATFORM,target=/var/lib/apt,sharing=locked \
    apt-get update -qq \
    && apt-get install -yqq lib32stdc++6 dbus libfreetype6 locales net-tools \
    # required for Steam/Proton
    && rm -f /etc/machine-id \
    && dbus-uuidgen --ensure=/etc/machine-id \
    && echo 'LANG="en_US.UTF-8"' > /etc/default/locale \
    && echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen \
    && locale-gen


FROM base AS builder-prod

RUN --mount=type=cache,mode=0755,id=apt-cache-TARGETPLATFORM,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,mode=0755,id=apt-data-TARGETPLATFORM,target=/var/lib/apt,sharing=locked \
    apt-get update -qq \
    && apt-get install -yqq build-essential git

COPY requirements.txt /
RUN --mount=type=cache,mode=0755,id=pip-$TARGETPLATFORM,target=/root/.cache \
    pip install --root-user-action=ignore -U pip uv \
    && uv pip install -r /requirements.txt \
    && rm /requirements.txt \
    # do not keep uv for prod layer as it is large
    && pip uninstall -y uv


FROM builder-prod AS builder-dev

COPY dev-requirements.txt /
RUN --mount=type=cache,mode=0755,id=pip,target=/root/.cache \
    pip install --root-user-action=ignore -U pip uv \
    && uv pip install -r /dev-requirements.txt \
    && rm /dev-requirements.txt


# production container
FROM base AS prod

COPY --from=builder-prod /usr/local/bin/ /usr/local/bin/
COPY --from=builder-prod /usr/local/lib/python3.12/ /usr/local/lib/python3.12/

RUN --mount=source=./,target=/tmp/ark-operator,type=bind \
    --mount=type=cache,id=apt-cache-TARGETPLATFORM,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-data-TARGETPLATFORM,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,mode=0755,id=pip,target=/root/.cache \
    ls -la /tmp/ark-operator \
    && cd /tmp/ark-operator \
    && apt-get update -qq \
    && apt-get install -yqq git \
    && pip install . \
    && apt-get remove -yqq git \
    && apt-get autoremove -yqq
USER app
WORKDIR /
ENTRYPOINT [ "arkctl" ]


# ark-server image
FROM prod AS server

ENV ARK_BASE_DIR=/srv/ark
ENV ARK_SERVER_DIR=${ARK_BASE_DIR}/server/ark
ENV ARK_STEAM_DIR=${ARK_BASE_DIR}/server/steam
ENV ARK_DATA_DIR=${ARK_BASE_DIR}/data
ENV ARK_OP_LOG_LEVEL=INFO
ENV ARK_OP_LOG_FORMAT=basic
ENV ARK_SERVER_CLUSTER_MODE=false

COPY --chmod=755 .docker/server-entry.sh /entrypoint
VOLUME [ "/srv/ark/server", "/srv/ark/data" ]
ENTRYPOINT [ "/entrypoint" ]
HEALTHCHECK --interval=5s --timeout=5s --start-period=10s --retries=5 CMD [ "sh", "-c", "arkctl server --host 127.0.0.1 rcon ListPlayers" ]

# dev container
FROM base AS dev

USER root
# Python will not automatically write .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
# Enables Python development mode, see https://docs.python.org/3/library/devmode.html
ENV PYTHONDEVMODE=1

COPY --from=builder-dev /usr/local/bin/ /usr/local/bin/
COPY --from=builder-dev /usr/local/lib/python3.12/ /usr/local/lib/python3.12/
COPY ./.docker/docker-fix.sh /usr/local/bin/docker-fix
COPY ./.docker/bashrc /root/.bashrc
COPY ./.docker/bashrc /home/app/.bashrc

RUN --mount=type=cache,id=apt-cache-TARGETPLATFORM,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-data-TARGETPLATFORM,target=/var/lib/apt,sharing=locked \
    apt-get update -qq \
    && apt-get install -yqq git curl vim procps curl jq yq sudo zip \
    && echo 'app ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers \
    && curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl \
    && rm kubectl \
    && chown app:app /home/app/.bashrc \
    && chmod +x /usr/local/bin/docker-fix

ENV PYTHONPATH=/workspaces/ark-operator/src/:/workspaces/ark-operator/test/
ENV PATH=$PATH:/workspaces/ark-operator/.bin
ENV ARK_OP_DEBUG=True
ENV ARK_STEAM_DIR=/workspaces/ark-operator/test/server/server-a/steam
ENV ARK_SERVER_DIR=/workspaces/ark-operator/test/server/server-a/ark
ENV ARK_SERVER_A_DIR=/workspaces/ark-operator/test/server/server-a/ark
ENV ARK_SERVER_B_DIR=/workspaces/ark-operator/test/server/server-b/ark
ENV ARK_DATA_DIR=/workspaces/ark-operator/test/server/data
ENV ARK_SERVER_IMAGE_VERSION=master

USER app
WORKDIR /workspaces/ark-operator/
