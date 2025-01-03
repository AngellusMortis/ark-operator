FROM python:3.12-slim-bookworm AS base

LABEL org.opencontainers.image.source=https://github.com/AngellusMortis/ark-operator

ENV PYTHONUNBUFFERED=1
ENV UV_SYSTEM_PYTHON=true
ARG TARGETPLATFORM

RUN addgroup --system --gid 1000 app \
    && adduser --system --shell /bin/bash --uid 1000 --home /home/app --ingroup app app

RUN --mount=type=cache,mode=0755,id=apt-cache-TARGETPLATFORM,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,mode=0755,id=apt-data-TARGETPLATFORM,target=/var/lib/apt,sharing=locked \
    apt-get update -qq \
    && apt-get install -yqq lib32stdc++6


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

USER app
WORKDIR /workspaces/ark-operator/


# dev container
FROM prod AS dev

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
ENV ARK_STEAM_DIR=/workspaces/ark-operator/steam/install
ENV ARK_SERVER_A_DIR=/workspaces/ark-operator/steam/ark_a
ENV ARK_SERVER_B_DIR=/workspaces/ark-operator/steam/ark_b

USER app
WORKDIR /workspaces/ark-operator/
