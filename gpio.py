# A simple library to interact with the esp32-wroom-32 GPIO in common ways
from machine import Pin
from time import sleep_ms


def blink(pin, delay=500):
    """
    blink :: machin.Pin -> int -> GPIO
    blink a specified output pin
    """
    pin.on()
    sleep_ms(delay)
    pin.off()
    sleep_ms(delay)
