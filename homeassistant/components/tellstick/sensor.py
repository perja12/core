"""Support for Tellstick sensors."""
from collections import namedtuple
import logging

from tellcore.telldus import AsyncioCallbackDispatcher, TelldusCore
import tellcore.constants as tellcore_constants
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_ID,
    CONF_NAME,
    CONF_PROTOCOL,
    TEMP_CELSIUS,
    UNIT_PERCENTAGE,
)
from homeassistant.core import callback
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)

DatatypeDescription = namedtuple("DatatypeDescription", ["name", "unit"])

CONF_DATATYPE_MASK = "datatype_mask"
CONF_ONLY_NAMED = "only_named"
CONF_TEMPERATURE_SCALE = "temperature_scale"
CONF_MODEL = "model"

DEFAULT_DATATYPE_MASK = 127
DEFAULT_TEMPERATURE_SCALE = TEMP_CELSIUS

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(
            CONF_TEMPERATURE_SCALE, default=DEFAULT_TEMPERATURE_SCALE
        ): cv.string,
        vol.Optional(
            CONF_DATATYPE_MASK, default=DEFAULT_DATATYPE_MASK
        ): cv.positive_int,
        vol.Optional(CONF_ONLY_NAMED, default=[]): vol.All(
            cv.ensure_list,
            [
                vol.Schema(
                    {
                        vol.Required(CONF_ID): cv.positive_int,
                        vol.Required(CONF_NAME): cv.string,
                        vol.Optional(CONF_PROTOCOL): cv.string,
                        vol.Optional(CONF_MODEL): cv.string,
                    }
                )
            ],
        ),
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Tellstick sensors."""
    _LOGGER.info("tellstick setup_platform")

    sensor_value_descriptions = {
        tellcore_constants.TELLSTICK_TEMPERATURE: DatatypeDescription(
            "temperature", config.get(CONF_TEMPERATURE_SCALE)
        ),
        tellcore_constants.TELLSTICK_HUMIDITY: DatatypeDescription(
            "humidity", UNIT_PERCENTAGE
        ),
        tellcore_constants.TELLSTICK_RAINRATE: DatatypeDescription("rain rate", ""),
        tellcore_constants.TELLSTICK_RAINTOTAL: DatatypeDescription("rain total", ""),
        tellcore_constants.TELLSTICK_WINDDIRECTION: DatatypeDescription(
            "wind direction", ""
        ),
        tellcore_constants.TELLSTICK_WINDAVERAGE: DatatypeDescription(
            "wind average", ""
        ),
        tellcore_constants.TELLSTICK_WINDGUST: DatatypeDescription("wind gust", ""),
    }

    try:
        tellcore_lib = TelldusCore(
            callback_dispatcher=AsyncioCallbackDispatcher(hass.loop)
        )
    except OSError:
        _LOGGER.exception("Could not initialize Tellstick")
        return

    datatype_mask = config.get(CONF_DATATYPE_MASK)

    named_sensors = {}
    if config[CONF_ONLY_NAMED]:
        for named_sensor in config[CONF_ONLY_NAMED]:
            name = named_sensor[CONF_NAME]
            proto = named_sensor.get(CONF_PROTOCOL)
            model = named_sensor.get(CONF_MODEL)
            id_ = named_sensor[CONF_ID]
            if proto is not None:
                if model is not None:
                    named_sensors[f"{proto}{model}{id_}"] = name
                else:
                    named_sensors[f"{proto}{id_}"] = name
            else:
                named_sensors[id_] = name

    _LOGGER.info("tellstick named_sensors: ")
    for key in named_sensors:
        _LOGGER.info("tellstick key:%s value:%s", key, named_sensors[key])

    registered_sensors = []

    @callback
    def async_handle_callback(protocol, model, id_, dataType, value, timestamp, cid):
        """Handle the actual callback from Tellcore."""
        # Construct id/name, check if already registered and if not add it.
        _LOGGER.info("Tellstick got callback: protocol:%s model:%s id:%s value:%s datatype:%s", protocol, model, id_, value, dataType)

        if not config[CONF_ONLY_NAMED]:
            sensor_name = str(id_)
        else:
            proto_id = f"{protocol}{id_}"
            proto_model_id = f"{protocol}{model}{id_}"

            if id_ in named_sensors:
                sensor_name = named_sensors[id_]
            elif proto_id in named_sensors:
                sensor_name = named_sensors[proto_id]
            elif proto_model_id in named_sensors:
                sensor_name = named_sensors[proto_model_id]
            else:
                return

        sensor = f"{sensor_name}-{dataType}"

        if sensor not in registered_sensors:
            registered_sensors.append(sensor)

            sensors = []
            if dataType in sensor_value_descriptions:
                if dataType & datatype_mask:
                    sensor_info = sensor_value_descriptions[dataType]
                    sensors.append(
                        TellstickSensor(sensor_name, dataType, sensor_info)
                    )

            add_entities(sensors)

    # Register callback
    callback_id = tellcore_lib.register_device_event(async_handle_callback)

    def clean_up_callback(event):
        """Unregister the callback bindings."""
        if callback_id is not None:
            tellcore_lib.unregister_callback(callback_id)

    hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, clean_up_callback)


class TellstickSensor(Entity):
    """Representation of a Tellstick sensor."""

    def __init__(self, name, datatype, sensor_info):
        """Initialize the sensor."""
        self._datatype = datatype
        self._unit_of_measurement = sensor_info.unit or None
        self._value = None

        self._name = f"{name} {sensor_info.name}"

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._value

    @property
    def should_poll(self):
        """No need to poll."""
        return False

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement
