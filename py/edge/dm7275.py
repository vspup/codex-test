#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DM7275 Interface Module

- Can be run standalone (CLI interface)
- Or imported as a library to control the Hioki DM7275
"""

import time
import math
import sys
from datetime import datetime
import serial
from serial.tools import list_ports

# === PUBLIC API ===
__all__ = ["open_port", "setup_device", "read_voltage", "connect_dm7275", "scpi_query", "scpi_write"]

# === CONFIG ===
PORT_DEFAULT = "/dev/ttyACM0"
BAUD_DEFAULT = 9600
TIMEOUT_S = 2.0
TERM = b"\r\n"
DISPLAY_MODE = "dynamic"  # "normal" or "dynamic"

# === CORE SERIAL HELPERS ===
def open_port(port, baud=BAUD_DEFAULT, timeout=TIMEOUT_S):
    ser = serial.Serial(
        port=port, baudrate=baud,
        timeout=timeout, write_timeout=timeout,
        bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE, rtscts=False, dsrdtr=False, xonxoff=False
    )
    ser.setDTR(True)
    ser.setRTS(True)
    time.sleep(0.1)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    return ser

def scpi_write(ser, cmd: bytes):
    ser.write(cmd + TERM)
    ser.flush()

def scpi_query(ser, cmd: bytes) -> str:
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    ser.write(cmd + TERM)
    ser.flush()
    line = ser.readline()
    return line.decode(errors="ignore").strip()

def parse_float_or_none(s: str):
    try:
        v = float(s)
        if math.isfinite(v) and abs(v) < 1e30 and abs(v) != 9.91e37:
            return v
    except Exception:
        pass
    return None

def read_error_if_any(ser):
    resp = scpi_query(ser, b":SYST:ERR?")
    if not resp:
        return None
    try:
        code = int(resp.split(",")[0])
    except Exception:
        return resp
    return None if code == 0 else resp

# === MAIN DEVICE SETUP ===
def setup_device(ser, rng="AUTO"):
    scpi_write(ser, b":ABORt")
    scpi_write(ser, b"*CLS")
    scpi_write(ser, b":SENS:FUNC 'VOLT'")
    scpi_write(ser, b":SENS:VOLT:ZERO:AUTO OFF")

    if rng == "AUTO":
        scpi_write(ser, b":SENS:VOLT:RANG:AUTO ON")
    else:
        try:
            val = float(rng)
            scpi_write(ser, f":SENS:VOLT:RANG {val}".encode())
        except Exception:
            print("Invalid range — falling back to AUTO.")
            scpi_write(ser, b":SENS:VOLT:RANG:AUTO ON")

    scpi_write(ser, b":FORM:DATA ASCii")
    scpi_write(ser, b":TRIG:SOUR IMM")
    scpi_write(ser, b":INIT:CONT OFF")

    # Give time to settle, and discard first (possibly invalid) read
    time.sleep(1.0)
    _ = scpi_query(ser, b":READ?")
    _ = scpi_query(ser, b":SYST:ERR?")

# === PUBLIC WRAPPER ===
def read_voltage(ser) -> float:
    """Returns one voltage reading as float (or None)."""
    resp = scpi_query(ser, b":READ?")
    return parse_float_or_none(resp)

def connect_dm7275(port_hint=PORT_DEFAULT, rng="AUTO") -> serial.Serial:
    ser = open_port(port_hint)
    setup_device(ser, rng)
    return ser

# === OPTIONAL CLI / INTERACTIVE MODE ===
def choose_port():
    ports = list(list_ports.comports())
    print("Available ports:")
    if not ports:
        print("  (no detected ports) → enter manually, e.g. /dev/ttyACM0")
    else:
        for i, p in enumerate(ports):
            print(f"  [{i}] {p.device}  {p.description}")
    raw = input(f"Select index or enter path [{PORT_DEFAULT}]: ").strip()
    if raw == "":
        return PORT_DEFAULT
    if raw.isdigit():
        idx = int(raw)
        if 0 <= idx < len(ports):
            return ports[idx].device
        else:
            print("Invalid index. Using default.")
            return PORT_DEFAULT
    return raw

def main():
    port = choose_port()
    rng = input("Voltage range (AUTO or number in V, e.g. 1e-1/1/10) [AUTO]: ").strip().upper() or "AUTO"

    while True:
        try:
            interval = float(input("Polling interval, seconds (e.g. 0.5): ").strip())
            if interval <= 0:
                raise ValueError
            break
        except Exception:
            print("Please enter a positive number, e.g. 0.5")

    ser = open_port(port)
    idn = scpi_query(ser, b"*IDN?")
    print("IDN:", idn or "<no response>")

    setup_device(ser, rng)
    print(f"\nPolling started: every {interval} s. Press Ctrl+C to stop.\n")

    try:
        k = 0
        while True:
            ts = datetime.now().isoformat(timespec="seconds")
            v = read_voltage(ser)
            err = read_error_if_any(ser) if (k % 10 == 0) else None
            out = f"{ts}  V={v:.8f}" if v is not None else f"{ts}  V=<no response>"
            if err:
                out += f"  ERR={err}"

            if DISPLAY_MODE == "dynamic":
                sys.stdout.write("\r" + out + " " * 10)
                sys.stdout.flush()
            else:
                print(out)

            k += 1
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        ser.close()

if __name__ == "__main__":
    main()
