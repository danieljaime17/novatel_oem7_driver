#!/usr/bin/env python3
"""
Simple standalone utility that scans USB serial ports, detects a GPS receiver by
sniffing NMEA-like traffic, and continuously prints the incoming sentences.

Dependencies: Python 3 standard library only.
"""

import glob
import logging
import os
import select
import sys
import termios
import time
from typing import Dict, Iterable, Optional, Tuple

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]


BAUD_MAP: Dict[int, int] = {
    115200: termios.B115200,
    57600: termios.B57600,
    38400: termios.B38400,
    19200: termios.B19200,
    9600: termios.B9600,
    4800: termios.B4800,
}

TTY_PATTERNS = ("/dev/ttyUSB*", "/dev/ttyACM*")
NMEA_PREFIXES = (b"$GP", b"$GN", b"$PQ", b"$PM", b"$PN")
INIT_COMMANDS = (
    "UNLOGALL THISPORT",
    "LOG GPGGA ONTIME 1",
    "LOG GPGSA ONTIME 1",
    "LOG GPGSV ONTIME 1",
    "LOG GPRMC ONTIME 1",
)


def iter_candidate_ports() -> Iterable[str]:
    for pattern in TTY_PATTERNS:
        for path in sorted(glob.glob(pattern)):
            yield path


def configure_port(fd: int, baud_const: int) -> None:
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0  # iflag
    attrs[1] = 0  # oflag
    attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
    attrs[3] = 0  # lflag (raw mode)
    attrs[4] = baud_const  # ispeed
    attrs[5] = baud_const  # ospeed
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 1
    termios.tcflush(fd, termios.TCIOFLUSH)
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def open_serial(path: str, baud: int) -> Optional[int]:
    baud_const = BAUD_MAP.get(baud)
    if baud_const is None:
        return None

    try:
        fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    except OSError as exc:
        logging.debug("Unable to open %s: %s", path, exc)
        return None

    try:
        configure_port(fd, baud_const)
    except termios.error as exc:
        logging.debug("Failed to configure %s at %d: %s", path, baud, exc)
        os.close(fd)
        return None

    return fd


def sniff_for_gps(fd: int, timeout: float = 3.0) -> Tuple[bool, bytes]:
    deadline = time.time() + timeout
    captured = bytearray()

    while time.time() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.5)
        if fd not in ready:
            continue

        try:
            chunk = os.read(fd, 4096)
        except OSError as exc:
            logging.debug("Read error: %s", exc)
            break

        if not chunk:
            continue

        captured.extend(chunk)
        for line in captured.splitlines():
            for prefix in NMEA_PREFIXES:
                if line.startswith(prefix):
                    return True, bytes(captured)

    return False, bytes(captured)


def make_blocking(fd: int) -> None:
    if fcntl is None:
        return
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)


def send_command(fd: int, cmd: str, timeout: float = 1.5) -> None:
    """
    Sends a simple ASCII command to the receiver and prints the first response line.
    """
    payload = (cmd + "\r\n").encode("ascii")
    logging.info("-> %s", cmd)

    try:
        os.write(fd, payload)
    except OSError as exc:
        logging.error("Write failed for '%s': %s", cmd, exc)
        return

    end = time.time() + timeout
    reply = bytearray()

    while time.time() < end:
        ready, _, _ = select.select([fd], [], [], 0.2)
        if fd not in ready:
            continue

        try:
            chunk = os.read(fd, 4096)
        except OSError as exc:
            logging.debug("Command read error: %s", exc)
            break

        if not chunk:
            continue

        reply.extend(chunk)
        if b"\n" in reply:
            break

    if reply:
        text = reply.decode("ascii", errors="replace").strip()
        if text:
            logging.info("<- %s", text)


def initialize_receiver(fd: int) -> None:
    """
    Issues a basic set of commands so the receiver starts streaming NMEA logs.
    """
    termios.tcflush(fd, termios.TCIOFLUSH)

    for cmd in INIT_COMMANDS:
        send_command(fd, cmd)


def stream_sentences(fd: int) -> None:
    make_blocking(fd)
    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 1.0)
            if fd not in ready:
                continue
            data = os.read(fd, 4096)
            if not data:
                continue
            for line in data.splitlines():
                if not line:
                    continue
                try:
                    text = line.decode("ascii", errors="replace")
                except UnicodeDecodeError:
                    text = "<binary data>"
                print(text, flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        os.close(fd)


def detect_gps() -> Optional[Tuple[str, int, int]]:
    for port in iter_candidate_ports():
        for baud in BAUD_MAP.keys():
            fd = open_serial(port, baud)
            if fd is None:
                continue

            logging.info("Probing %s at %d baud...", port, baud)
            matched, sample = sniff_for_gps(fd, timeout=1.5)
            if not matched:
                logging.info("No data detected yet, attempting receiver initialization...")
                initialize_receiver(fd)
                matched, sample = sniff_for_gps(fd, timeout=4.0)
            if matched:
                logging.info("Detected GPS on %s @ %d baud", port, baud)
                if sample:
                    try:
                        text = sample.decode("ascii", errors="replace")
                    except UnicodeDecodeError:
                        text = ""
                    if text:
                        print("--- Sample data ---")
                        for line in text.splitlines():
                            if line.strip():
                                print(line)
                        print("--- End sample ---")
                return port, baud, fd

            os.close(fd)

    return None


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("Scanning USB serial ports for GPS data...", flush=True)

    result = detect_gps()
    if result is None:
        print("No GPS device detected. Ensure it is connected and accessible.", flush=True)
        return 1

    port, baud, fd = result
    initialize_receiver(fd)
    print(f"Streaming data from {port} at {baud} baud. Press Ctrl+C to stop.", flush=True)
    stream_sentences(fd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
