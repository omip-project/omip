"""Basic service health API."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter


def create_health_router(
    *,
    mqtt_status: Callable[[], dict[str, Any]],
) -> APIRouter:
    """Create the basic OMIP health router.

    Dependencies are supplied by the application composition root so this
    module remains independent from ``main.py`` and can be tested in isolation.
    """

    router = APIRouter(tags=["Health"])

    @router.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "omip-platform-api",
            "version": "0.5.2",
            "mqtt_enabled": mqtt_status()["enabled"],
        }

    return router
