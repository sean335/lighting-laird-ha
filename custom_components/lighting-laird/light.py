"""Demo light platform that implements lights."""
from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN
from .entity import LightingLairdEntity
from .models import LightingLairdData

LIGHT_COLORS = [(56, 86), (345, 75)]

LIGHT_EFFECT_LIST = ["rainbow", "none"]

LIGHT_TEMPS = [240, 380]

SUPPORT_DEMO = {ColorMode.HS, ColorMode.COLOR_TEMP}
SUPPORT_DEMO_HS_WHITE = {ColorMode.HS, ColorMode.WHITE}


class LightingLairdLight(LightingLairdEntity, LightEntity):
    """Representation of Advantage Air Light."""

    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_name = None

    def __init__(
        self, hass: HomeAssistant, instance: LightingLairdData, light: dict[str, Any]
    ) -> None:
        """Initialize an Advantage Air Light."""
        super().__init__(instance)

        self._id: str = light["lampId"]
        self._attr_unique_id = f"LairdLamp-{self._id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            via_device=(DOMAIN, "LairdHub"),
            name=light["name"],
        )
        self.async_update_state = self.update_handle_factory(
            instance.api.async_update_state, self._id
        )

        hass.bus.async_listen("laird-brightness", self._async_update_brightness)

    def _async_update_brightness(self, data):
        if data.data["lampId"] == self._id:
            print(f"Event received: {data}")
            self._data["brightness"] = data.data["brightness"]
            self.schedule_update_ha_state()

    @property
    def _data(self) -> dict[str, Any]:
        """Return the light object."""
        if "Lamps" in self.coordinator.data:
            return self.coordinator.data["Lamps"][self._id]

    @property
    def name(self) -> str:
        return self._data["name"]

    @property
    def is_on(self) -> bool:
        """Return if the light is on."""
        return self._data["brightness"] > 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        await self.async_update_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self.async_update_state(False)


class LightingLairdLightDimmable(LightingLairdLight):
    """Representation of Advantage Air Dimmable Light."""

    _attr_supported_color_modes = {ColorMode.ONOFF, ColorMode.BRIGHTNESS}

    def __init__(
        self, hass: HomeAssistant, instance: LightingLairdData, light: dict[str, Any]
    ) -> None:
        """Initialize an Advantage Air Dimmable Light."""
        super().__init__(hass, instance, light)
        self.async_update_value = self.update_handle_factory(
            instance.api.async_update_value, self._id
        )

    @property
    def brightness(self) -> int:
        """Return the brightness of this light between 0..255."""
        return round(self._data["brightness"])

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on and optionally set the brightness."""
        if ATTR_BRIGHTNESS in kwargs:
            return await self.async_update_value(round(kwargs[ATTR_BRIGHTNESS] / 2.55))
        return await self.async_update_state(True)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    instance: LightingLairdData = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[LightEntity] = []
    my_lights = instance.coordinator.data["Lamps"]
    if my_lights is not None:
        print(f"Got Lights: {my_lights}")
        for light in my_lights:
            if light is not None and light.get("dimmable") != 0:
                entities.append(
                    LightingLairdLight(hass=hass, instance=instance, light=light)
                )
            elif light is not None:
                entities.append(
                    LightingLairdLightDimmable(
                        hass=hass, instance=instance, light=light
                    )
                )
    async_add_entities(entities)
