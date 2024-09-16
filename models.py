"""The Advantage Air integration models."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .lairdserver import LightingLairdDevices


@dataclass
class LightingLairdData:
    """Data for the Advantage Air integration."""

    coordinator: DataUpdateCoordinator
    api: LightingLairdDevices
