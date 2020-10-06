import bluetooth
import random
import struct
import time
from ble_advertising import advertising_payload

from micropython import const

import bme280_float as bme280
from machine import Pin, I2C

from gpio import blink

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_INDICATE_DONE = const(20)

# org.bluetooth.service.environmental_sensing
_ENV_SENSE_UUID = bluetooth.UUID(0x181A)

# org.bluetooth.characteristic.temperature
# temperature
_TEMP_CHAR = (
    bluetooth.UUID(0x2A6E),
    bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY | bluetooth.FLAG_INDICATE,
)

# atmospheric pressure
# org.bluetooth.characteristic.pressure
_PRESSURE_CHAR = (
    bluetooth.UUID(0x2A6D),
    bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY | bluetooth.FLAG_INDICATE,
)

# percentage humidity
# org.bluetooth.characteristic.humidity
_HUMIDITY_CHAR = (
    bluetooth.UUID(0x2A6F),
    bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY | bluetooth.FLAG_INDICATE,
)

# communication channel
# org.bluetooth.characteristic.string
_STRING_CHAR = (
    bluetooth.UUID(0x2A3D),
    bluetooth.FLAG_READ | bluetooth.FLAG_WRITE,
)

_ENV_SENSE_SERVICE = (
    _ENV_SENSE_UUID,
    (_TEMP_CHAR, _PRESSURE_CHAR, _HUMIDITY_CHAR, _STRING_CHAR),
)

# org.bluetooth.characteristic.gap.appearance.xml
_ADV_APPEARANCE_GENERIC_ENVIRONMENTAL_SENSOR = const(5696)


class BLEEnvironment:
    def __init__(self, ble, name="esp32-ble-demo"):
        """
        __init__ :: BLEEnvironment -> bluetooth.BLE -> str -> BLEEnvironment
        """
        self._ble = ble
        self._ble.active(True)
        # register the event handler for events in the BLE stack
        self._ble.irq(self._irq)
        # unpack the gatt handles returned from service registration
        ((self._temp_handle, self._pressure_handle, self._humidity_handle, self._string_handle),
         ) = self._ble.gatts_register_services((_ENV_SENSE_SERVICE,))
        # a set to contain connections to enable the sending of notifications
        self._connections = set()
        # create the payload for advertising the server
        self._payload = advertising_payload(
            name=name,
            services=[_ENV_SENSE_UUID],
            appearance=_ADV_APPEARANCE_GENERIC_ENVIRONMENTAL_SENSOR
        )
        # begin advertising the gatt server
        self._advertise()

    def _irq(self, event, data):
        # callback function for events from the BLE stack
        # Track connections so we can send notifications.
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _, _ = data
            self._connections.add(conn_handle)
        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, _, _ = data
            self._connections.remove(conn_handle)
            # Start advertising again to allow a new connection.
            self._advertise()
        elif event == _IRQ_GATTS_INDICATE_DONE:
            conn_handle, value_handle, status = data

    def set_environment_data(self, temp, pressure, humidity, notify=False, indicate=False):

        # write fresh temperature, pressure, and humidity data to the GATT server characteristics
        self._ble.gatts_write(
            self._temp_handle, struct.pack("<i", int(temp)))
        self._ble.gatts_write(self._pressure_handle,
                              struct.pack("<i", int(pressure)))
        self._ble.gatts_write(self._humidity_handle,
                              struct.pack("<i", int(humidity)))

        # optionally notify and or indicate connected centrals
        if notify or indicate:
            for conn_handle in self._connections:
                if notify:
                    # Notify connected centrals.
                    self._ble.gatts_notify(conn_handle, self._temp_handle)
                    self._ble.gatts_notify(conn_handle, self._pressure_handle)
                    self._ble.gatts_notify(conn_handle, self._humidity_handle)
                if indicate:
                    # Indicate connected centrals.
                    self._ble.gatts_indicate(conn_handle, self._temp_handle)
                    self._ble.gatts_indicate(
                        conn_handle, self._pressure_handle)
                    self._ble.gatts_indicate(
                        conn_handle, self._humidity_handle)

    def read_act(self):
        """
        Read the string channel in GATT, Act if the message is recognized
        """
        # value is read from the _string_handle
        value = self._ble.gatts_read(self._string_handle)

        # the message protocol is implemented
        # alternatively the message protocol can be implemented as a mapping from (utf-8 -> function.obj)
        # the functions could be written such that they can be spawned in a new thread so the main loop is not blocked.
        # currently the action requested by a message blocks until the action completes.
        if value == bytes('blink', 'utf-8'):
            p = Pin(23, Pin.OUT)
            for _ in range(3):
                blink(p)

        # the channel is cleared
        self._ble.gatts_write(self._string_handle, struct.pack("<i", 0))

    def _advertise(self, interval_us=500000):
        self._ble.gap_advertise(interval_us, adv_data=self._payload)


def run():
    ble = bluetooth.BLE()
    env = BLEEnvironment(ble)

    i = 0

    while True:
        # Write every second, notify every 10 seconds.
        i = (i + 1) % 10

        # using the bme280 library sample environment data
        i2c = I2C(scl=Pin(22), sda=Pin(21))
        bme = bme280.BME280(i2c=i2c)
        temp, pressure, humidity = bme.values

        # publish environment data
        env.set_environment_data(
            temp, pressure, humidity, notify=i == 0, indicate=False)

        # check the communication channel
        env.read_act()

        # take a break
        # TODO can micropython power the board down for a duration instead of sleeping? or is that how sleep is implemented?
        time.sleep_ms(1000)


if __name__ == "__main__":
    run()
