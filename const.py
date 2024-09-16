"""Constants for the wiffi component."""

# Component domain, used to store component data in hass data.
DOMAIN = "lightinglaird"

# Default port for TCP server
DEFAULT_IP_ADDRESS = "192.168.1.149"

# Default timeout in minutes
DEFAULT_TIMEOUT = 3

# Signal name to send create/update to platform (sensor/binary_sensor)
CREATE_ENTITY_SIGNAL = "wiffi_create_entity_signal"
UPDATE_ENTITY_SIGNAL = "wiffi_update_entity_signal"
CHECK_ENTITIES_SIGNAL = "wiffi_check_entities_signal"
