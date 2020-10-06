# esp32-ble-demo

This is a demo project to learn about and implement a basic environmental sensor
with a controllable led using bluetooth low energy (ble).
This project is written in micropython.

The environment is sampled using a bme280 or bmp280 sensor and served via a GATT server.
Additionally an l.e.d. can be blinked when the utf-8 string 'blink' is sent to the GATT server via the string characteristic.


<!-- vim-markdown-toc GFM -->

* [parts](#parts)
* [ble_environment.py](#ble_environmentpy)
    * [BLEEnvironment class](#bleenvironment-class)
        * [\_\_init\_\_](#__init_)
        * [_irq](#irq)
        * [set_environment_data](#set_environment_data)
        * [read_act](#read_act)
        * [_advertise](#advertise)
* [bme280_float.py](#bme280_floatpy)
* [gpio.py](#gpiopy)
* [ble_advertising.py](#ble_advertisingpy)

<!-- vim-markdown-toc -->
## parts

- ESP32-WROOM-32 microcontroller
- bmp280 environmental sensor (temperature, pressure)
- led

## ble_environment.py

This file defines the BLEEnvironment class that runs the application

---

```python
import bluetooth
import random
import struct
import time
from ble_advertising import advertising_payload

from micropython import const

import bme280_float as bme280
from machine import Pin, I2C

from gpio import blink

```

standard micropython and project specific libraries.
ble_advertising, bme280_float, and gpio will be explained in their own sections.

```python
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_INDICATE_DONE = const(20)

```

Define event code constants.

```python
# org.bluetooth.service.environmental_sensing
_ENV_SENSE_UUID = bluetooth.UUID(0x181A)
```

Use a predefined uuid for the enviornmental_sensing service.

```python

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
```

Also using predefine uuids define the characteristics the service will offer.

```python

_ENV_SENSE_SERVICE = (
    _ENV_SENSE_UUID,
    (_TEMP_CHAR, _PRESSURE_CHAR, _HUMIDITY_CHAR, _STRING_CHAR),
)

# org.bluetooth.characteristic.gap.appearance.xml
_ADV_APPEARANCE_GENERIC_ENVIRONMENTAL_SENSOR = const(5696)

```

Using the service and characteristics previously defined fully define the service
to be registered on the GATT server.

### BLEEnvironment class

The following are methods of BLEEnvironment class.

#### \_\_init\_\_

```python
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
```

\_\_init\_\_ constructs an object of the BLEEnvironment class.
ble is a bluetooth.BLE object.
This method sets up and begins to advertise the device for bluetooth connections.

#### _irq

```python
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
```

Define a simple event handler for GATT stack events.
This method is used by bluethooth.BLE.irq

####  set_environment_data

```python
def set_environment_data(self, temp, pressure, humidity, notify=False, indicate=False):

    # write fresh temperature, pressure, and humidity data to the GATT server characteristics
    self._ble.gatts_write(
        self._temp_handle, struct.pack("<i", int(temp)))
    self._ble.gatts_write(self._pressure_handle,
                          struct.pack("<i", int(pressure)))
    self._ble.gatts_write(self._humidity_handle,
                          struct.pack("<i", int(humidity)))

    # write fresh temperature, pressure, and humidity data to the GATT server characteristics
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
```
set_environment_data is used to update the environmental data that is being served by the GATT server.
Optionally connected centrals can be notified or indicated about updates to the characteristics.

#### read_act

```python
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

```
read_act implements the message protocol.
The method reads from the string characteristic and calls the appropriate method
if a recognized message is received.

#### _advertise

```python
def _advertise(self, interval_us=500000):
    self._ble.gap_advertise(interval_us, adv_data=self._payload)
```
_advertise uses the precomputed self._payload to advertise the device.



## bme280_float.py
This file implements the BME280 class which allows a bme280 or bmp280 environment
sensor to sample temperature, pressure, and humidity data.

## gpio.py
This file implements common uses of the esp32 GPIO.
Specifically a blink functionality.

## ble_advertising.py
Helper functions for generation ble advertising payloads.
