"""Parser for wiffi telegrams and server for wiffi devices."""
import asyncio
import json

import time
import websockets
from websockets.protocol import State


class LightingLairdHub:
    """Representation of wiffi device properties reported in the json telegram."""

    def __init__(self, moduletype, data, configuration_url):
        """Initialize the instance."""
        self._moduletype = moduletype
        self._mac_address = data.get("MAC-Adresse")
        self._dest_ip = data.get("Homematic_CCU_ip")
        self._wlan_ssid = data.get("WLAN_ssid")
        self._wlan_signal_strength = float(data.get("WLAN_Signal_dBm", 0))
        self._sw_version = data.get("firmware")
        self._configuration_url = configuration_url

    @property
    def moduletype(self):
        """Return the wiffi device type, e.g. 'weatherman'."""
        return self._moduletype

    @property
    def mac_address(self):
        """Return the mac address of the wiffi device."""
        return self._mac_address

    @property
    def dest_ip(self):
        """Return the destination ip address for json telegrams."""
        return self._dest_ip

    @property
    def wlan_ssid(self):
        """Return the configured WLAN ssid."""
        return self._wlan_ssid

    @property
    def wlan_signal_strength(self):
        """Return the measured WLAN signal strength in dBm."""
        return self._wlan_signal_strength

    @property
    def sw_version(self):
        """Return the firmware revision string of the wiffi device."""
        return self._sw_version

    @property
    def configuration_url(self):
        """Return the URL to the web interface of the wiffi device."""
        return self._configuration_url


class LightingLairdDevices:
    def __init__(self, server):
        """Initialize the instance."""
        self._server = server

    def getAllLamps():
        return []


class LightingLairdConnection:
    """Representation of a TCP connection between a wiffi device and the server.

    The following behaviour has been observed with weatherman firmware 107:
    For every json telegram which has to be sent by the wiffi device to the TCP
    server, a new TCP connection will be opened. After 1 json telegram has been
    transmitted, the connection will be closed again. The telegram is terminated
    by a 0x04 character. Therefore we read until we receive a 0x04 character and
    parse the whole telegram afterwards. Then we wait for the next telegram, but
    the connection will be closed by the wiffi device. Therefore we get an
    'IncompleteReadError exception which we will ignore. We don't close the
    connection on our own, because the behaviour that the wiffi device closes
    the connection after every telegram may change in the future.
    """

    def __init__(self, server):
        """Initialize the instance."""
        self._server = server

    async def __call__(self, reader, writer):
        """Process callback from the TCP server if a new connection has been opened."""
        peername = writer.get_extra_info("peername")
        while not reader.at_eof():
            try:
                data = await reader.readuntil(
                    b"\x04"
                )  # read until separator \x04 received
                await self.parse_msg(peername, data[:-1])  # omit separator with [:-1]
            except asyncio.IncompleteReadError:
                pass

    async def parse_msg(self, peername, raw_data):
        """Parse received telegram which is terminated by 0x04."""
        data = json.loads(raw_data.decode("utf-8"))

        moduletype = data["modultyp"]
        systeminfo = data["Systeminfo"]
        configuration_url = f"http://{peername[0]}"

        metrics = []
        for var in data["vars"]:
            metrics.append(WiffiMetric(var))

        try:
            metrics.append(
                WiffiMetricFromSystemInfo(
                    "rssi", "dBm", "number", data["Systeminfo"]["WLAN_Signal_dBm"]
                )
            )
        except KeyError:
            pass

        try:
            metrics.append(
                WiffiMetricFromSystemInfo(
                    "uptime", "s", "number", data["Systeminfo"]["sec_seit_reset"]
                )
            )
        except KeyError:
            pass

        try:
            metrics.append(
                WiffiMetricFromSystemInfo(
                    "ssid", None, "string", data["Systeminfo"]["WLAN_ssid"]
                )
            )
        except KeyError:
            pass

        if self._server.callback is not None:
            await self._server.callback(
                WiffiDevice(moduletype, systeminfo, configuration_url), metrics
            )


class LightingLairdWebSocketServer:
    """Manages TCP server for wiffi devices.

    Opens a single port and listens for incoming TCP connections.
    """

    def __init__(self, host, callback=None):
        """Initialize instance."""
        self.host = host
        self.callback = callback
        self.server = None
        self.disableRecv = False

    async def consumer_handler(self, websocket):
        async for message in websocket:
            message = await websocket.recv()
            print(f"client got {message}")

    async def client(self, websocket):
        await asyncio.gather(self.consumer_handler(websocket))

    async def start_server(self):

        testSock = await websockets.connect(f"ws://{self.host}/ws")
        await testSock.send("ping")
        message = await testSock.recv()
        self.server = testSock

        '''        while True:
            try:
                # Attempt to establish the connection
                testSock = await websockets.connect(f"ws://{self.host}/ws")
                self.server = testSock
                print("Connected to the WebSocket")
                
                # Example of sending and receiving a message
                await testSock.send("ping")
                message = await testSock.recv()
                print(f"Received message: {message}")
                
                # Optionally continue handling communication here...
                # Keep the connection open
                while True:
                    pass

            except (websockets.ConnectionClosedError, websockets.ConnectionClosedOK) as e:
                print(f"Connection lost: {e}. Reconnecting in 5 seconds...")
                time.sleep(5)  # Wait before retrying

            except Exception as e:
                print(f"An error occurred: {e}. Reconnecting in 5 seconds...")
                time.sleep(5)  # Wait before retrying
        '''

    async def disable_recv(self):
        self.disableRecv = True

    async def get_lamps(self):
        if self.server is not None and self.server.state is not State.OPEN:
            await self.start_server()

        if self.server is not None:
            await self.server.send("getAllLamps")
            if self.disableRecv is False:
                message = await self.server.recv()
                return message

    async def get_buttons(self):
        if self.server is not None and self.server.state is not State.OPEN:
            await self.start_server()

        if self.server is not None:
            await self.server.send("getAllButtons")
            if self.disableRecv is False:
                message = await self.server.recv()
                return message

    async def close_server(self):
        """Close TCP server."""
        if self.server is not None:
            await self.server.close()
            await self.server.wait_closed()

    async def sendMsg(self, msg):
        if self.server is not None and self.server.state is not State.OPEN:
            await self.start_server()

        if self.server is not None:
            await self.server.send(msg)
            if self.disableRecv is False:
                message = await self.server.recv()
                return message
