"""Demo platform that offers a fake button entity."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN
from .entity import LightingLairdEntity
from .models import LightingLairdData


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    instance: LightingLairdData = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[BinarySensorEntity] = []
    my_buttons = instance.coordinator.data["Buttons"]
    if my_buttons is not None:
        print(f"Got Buttons: {my_buttons}")
        for button in my_buttons:
            entities.append(
                LightingLairdButton(
                    hass=hass, instance=instance, button=my_buttons.get(button)
                )
            )
    async_add_entities(entities)


class LightingLairdButton(LightingLairdEntity, BinarySensorEntity):
    """Representation of a demo button entity."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False

    def __init__(
        self, hass: HomeAssistant, instance: LightingLairdData, button: dict[str, Any]
    ) -> None:
        """Initialize an Advantage Air Light."""
        super().__init__(instance)

        self._id: str = button["buttonId"]
        self._attr_unique_id = f"LairdButton-{self._id}"
        self._is_on = False
        if "state" in button:
            self._is_on = button["state"]

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            via_device=(DOMAIN, "LairdHub"),
            name=button["name"],
        )
        self.async_update_state = self.update_handle_factory(
            instance.api.async_update_state, self._id
        )

        hass.bus.async_listen("laird-button", self._async_button_change)

    def _async_button_change(self, data):
        if data.data["buttonId"] == int(self._id):
            self._is_on = data.data["state"]
            self.schedule_update_ha_state()

    @property
    def _data(self) -> dict[str, Any]:
        """Return the button object."""
        if "Buttons" in self.coordinator.data:
            if self._id in self.coordinator.data["Buttons"]:
                return self.coordinator.data["Buttons"][self._id]

    @property
    def name(self) -> str:
        return self._data["name"]

    @property
    def is_on(self) -> bool:
        """State of the binary sensor."""
        return self._is_on
