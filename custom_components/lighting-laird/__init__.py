"""Component for wiffi support."""
import asyncio
from datetime import timedelta
import errno
import json
import logging

from websockets.exceptions import ConnectionClosedError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, CONF_TIMEOUT, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.dt import utcnow

from .const import (
    CHECK_ENTITIES_SIGNAL,
    CREATE_ENTITY_SIGNAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    UPDATE_ENTITY_SIGNAL,
)
from .lairdserver import LightingLairdWebSocketServer
from .models import LightingLairdData

_LOGGER = logging.getLogger(__name__)


PLATFORMS = [Platform.BINARY_SENSOR, Platform.LIGHT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up wiffi from a config entry, config_entry contains data from config entry database."""
    if not entry.update_listeners:
        entry.add_update_listener(async_update_options)

    @callback
    def plex_websocket_callback(msgtype, data, error):
        _LOGGER.info(f"websocket message received {msgtype}")

    # create api object
    api = LightingLairdIntegrationApi(hass, plex_websocket_callback)
    api.async_setup(entry)

    async def async_get():
        # global latestLampData
        # if latestLampData is None:
        latestLampData = {}

        try:
            lampData = await api.getAllLamps()
            buttonData = await api.getAllButtons()
            if lampData is not None:
                lampData = lampData[8:]
                latestLampData["Lamps"] = json.loads(lampData)
            if buttonData is not None:
                buttonData = buttonData[10:]
                latestLampData["Buttons"] = json.loads(buttonData)

            if "Lamps" in latestLampData and "Buttons" in latestLampData:
                return latestLampData
            else:
                print(
                    f"Failed to update buttons and lamps on LightingLaird: Lamps:{lampData} Buttons:{buttonData}"
                )

            return coordinator.data
        except OSError as err:
            raise Exception(err) from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Lighting Laird",
        update_method=async_get,
        update_interval=timedelta(seconds=60),
    )

    # store api object
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = LightingLairdData(
        coordinator, api
    )

    async def readWebSockMessages(webSocket):
        while True:
            try:
                if api.server.server is not None:
                    async for message in api.server.server:
                        print(f"client got {message}")
                        msgArgs = message.split(" ")
                        if len(msgArgs) > 0 and msgArgs[0] == "bl":  # brightness level
                            lampId = int(msgArgs[1])
                            lampBrightness = int(msgArgs[2])
                            event_data = {
                                "lampId": lampId,
                                "brightness": lampBrightness,
                            }
                            hass.bus.async_fire("laird-brightness", event_data)
                        elif len(msgArgs) > 0 and msgArgs[0] == "bs":  # button state
                            buttonId = int(msgArgs[1])
                            buttonState = int(msgArgs[2])
                            event_data = {"buttonId": buttonId, "state": buttonState}
                            hass.bus.async_fire("laird-button", event_data)
                        elif len(msgArgs) > 0 and msgArgs[0] == "lampData":
                            lampJson = message[8:]
                            coordinator.data["Lamps"] = json.loads(lampJson)
                            coordinator.async_set_updated_data(coordinator.data)
                        elif len(msgArgs) > 0 and msgArgs[0] == "buttonData":
                            buttonJson = message[10:]
                            coordinator.data["Buttons"] = json.loads(buttonJson)
                            coordinator.async_set_updated_data(coordinator.data)
            except ConnectionClosedError:
                try:
                    print("Exception! Reconnecting to Lighting Laird Hub")
                    await asyncio.wait_for(api.server.start_server(), timeout=5)
                except ConnectionRefusedError:
                    await asyncio.sleep(5)
                    print("connection refused.  wait for retry")
            except ConnectionRefusedError:
                await asyncio.sleep(5)
                print("connection refused.  wait for retry")

    try:
        await asyncio.wait_for(api.server.start_server(), timeout=5)

    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            _LOGGER.error("Start_server failed, errno: %d", exc.errno)
            return False
        _LOGGER.error("Port %s already in use", entry.data[CONF_PORT])
        raise ConfigEntryNotReady from exc

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = LightingLairdData(coordinator, api)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await api.server.disable_recv()
    asyncio.ensure_future(readWebSockMessages(api.server.server))

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    instance: LightingLairdData = hass.data[DOMAIN][entry.entry_id]
    await instance.api.server.close_server()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        api = hass.data[DOMAIN].pop(entry.entry_id)
    # api.shutdown()

    return unload_ok


def generate_unique_id(device, metric):
    """Generate a unique string for the entity."""
    return f"{device.mac_address.replace(':', '')}-{metric.name}"


class LightingLairdIntegrationApi:
    """API object for wiffi handling. Stored in hass.data."""

    coordinator: DataUpdateCoordinator

    def __init__(self, hass, websocketCallback):
        """Initialize the instance."""
        self._hass = hass
        self._server = None
        self._known_devices = {}
        self._periodic_callback = None
        self._websocketCallback = websocketCallback
        _LOGGER.info("laird lighting init")

    def async_setup(self, config_entry):
        """Set up api instance."""
        _LOGGER.info("laird lighting setup")
        self._server = LightingLairdWebSocketServer(
            host=config_entry.data[CONF_IP_ADDRESS], callback=self._websocketCallback
        )
        self._periodic_callback = async_track_time_interval(
            self._hass, self._periodic_tick, timedelta(seconds=10)
        )

    def async_update_state(self, lampId, state):
        response = None
        if state == True:
            response = self._server.sendMsg(f"turn_on  {lampId}")
        else:
            response = self._server.sendMsg(f"turn_off  {lampId}")
        return response

    def async_update_value(self, lampId, value):
        value = int((value / 100) * 254)
        response = self._server.sendMsg(f"set_brightness  {lampId} {value}")
        return response

    def getAllLamps(self):
        response = self._server.sendMsg("getAllLamps")
        return response

    def getAllButtons(self):
        response = self._server.sendMsg("getAllButtons")
        return response

    def shutdown(self):
        """Shutdown wiffi api.

        Remove listener for periodic callbacks.
        """
        if (remove_listener := self._periodic_callback) is not None:
            remove_listener()

    async def __call__(self, device, metrics):
        """Process callback from TCP server if new data arrives from a device."""
        if device.mac_address not in self._known_devices:
            # add empty set for new device
            self._known_devices[device.mac_address] = set()

        for metric in metrics:
            if metric.id not in self._known_devices[device.mac_address]:
                self._known_devices[device.mac_address].add(metric.id)
                async_dispatcher_send(self._hass, CREATE_ENTITY_SIGNAL, device, metric)
            else:
                async_dispatcher_send(
                    self._hass,
                    f"{UPDATE_ENTITY_SIGNAL}-{generate_unique_id(device, metric)}",
                    device,
                    metric,
                )

    @property
    def server(self):
        """Return TCP server instance for start + close."""
        return self._server

    @callback
    def _periodic_tick(self, now=None):
        """Check if any entity has timed out because it has not been updated."""
        async_dispatcher_send(self._hass, CHECK_ENTITIES_SIGNAL)


class WiffiEntity(Entity):
    """Common functionality for all wiffi entities."""

    _attr_should_poll = False

    def __init__(self, device, metric, options):
        """Initialize the base elements of a wiffi entity."""
        self._id = generate_unique_id(device, metric)
        self._attr_unique_id = self._id
        self._attr_device_info = DeviceInfo(
            connections={(dr.CONNECTION_NETWORK_MAC, device.mac_address)},
            identifiers={(DOMAIN, device.mac_address)},
            manufacturer="stall.biz",
            model=device.moduletype,
            name=f"{device.moduletype} {device.mac_address}",
            sw_version=device.sw_version,
            configuration_url=device.configuration_url,
        )
        self._attr_name = metric.description
        self._expiration_date = None
        self._value = None
        self._timeout = options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)

    async def async_added_to_hass(self):
        """Entity has been added to hass."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{UPDATE_ENTITY_SIGNAL}-{self._id}",
                self._update_value_callback,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, CHECK_ENTITIES_SIGNAL, self._check_expiration_date
            )
        )
        self.async_on_remove()

    def reset_expiration_date(self):
        """Reset value expiration date.

        Will be called by derived classes after a value update has been received.
        """
        self._expiration_date = utcnow() + timedelta(minutes=self._timeout)

    @callback
    def _update_value_callback(self, device, metric):
        """Update the value of the entity."""

    @callback
    def _check_expiration_date(self):
        """Periodically check if entity value has been updated.

        If there are no more updates from the wiffi device, the value will be
        set to unavailable.
        """
        if (
            self._value is not None
            and self._expiration_date is not None
            and utcnow() > self._expiration_date
        ):
            self._value = None
            self.async_write_ha_state()

    def _is_measurement_entity(self):
        """Measurement entities have a value in present time."""
        return (
            not self._attr_name.endswith("_gestern") and not self._is_metered_entity()
        )

    def _is_metered_entity(self):
        """Metered entities have a value that keeps increasing until reset."""
        return self._attr_name.endswith("_pro_h") or self._attr_name.endswith("_heute")
