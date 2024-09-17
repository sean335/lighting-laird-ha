from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .models import LightingLairdData


class LightingLairdEntity(CoordinatorEntity):
    """Parent class for Advantage Air Entities."""

    _attr_has_entity_name = True

    def __init__(self, instance: LightingLairdData) -> None:
        """Initialize common aspects of an Advantage Air entity."""
        super().__init__(instance.coordinator)
        # self._attr_unique_id: str = self.coordinator.data["system"]["rid"]

    def update_handle_factory(self, func, *keys):
        """Return the provided API function wrapped.

        Adds an error handler and coordinator refresh, and presets keys.
        """

        async def update_handle(*values):
            try:
                if await func(*keys, *values):
                    await self.coordinator.async_refresh()
            except OSError as err:
                raise HomeAssistantError(err) from err

        return update_handle
