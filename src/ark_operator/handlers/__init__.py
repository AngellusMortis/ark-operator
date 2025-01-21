"""Handlers for kopf."""

from ark_operator.handlers.conf import on_update_conf
from ark_operator.handlers.create import (
    on_create_data_pvc,
    on_create_init,
    on_create_init_pvc,
    on_create_resources,
    on_create_server_pvc,
    on_create_state,
)
from ark_operator.handlers.delete import (
    on_delete_resources,
)
from ark_operator.handlers.misc import cleanup, startup
from ark_operator.handlers.update import (
    on_update_data_pvc,
    on_update_server_pvc,
    on_update_state,
)

__all__ = [
    "cleanup",
    "on_create_data_pvc",
    "on_create_init",
    "on_create_init_pvc",
    "on_create_resources",
    "on_create_server_pvc",
    "on_create_state",
    "on_delete_resources",
    "on_update_conf",
    "on_update_data_pvc",
    "on_update_server_pvc",
    "on_update_state",
    "startup",
]
