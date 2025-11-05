#!/usr/bin/env python3
"""
Initialize a NovAtel OEM7 receiver on a USB serial port and stream the incoming
messages to the terminal. Uses Python 3 standard library only.
"""

import argparse
import logging
import os
import select
import sys
import termios
from typing import Iterable, Sequence

try:
    from gps_init import open_serial, send_commands
except ImportError:  # pragma: no cover - defensive in case gps_init is moved.
    # Fallback: update sys.path to include sibling directory.
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    from gps_init import open_serial, send_commands  # type: ignore


DEFAULT_PORT = "/dev/ttyUSB1"
DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 1.5

# Minimal command set that works on all tested OEM7 variants and enables NMEA.
DEFAULT_COMMANDS = (
    "UNLOGALL THISPORT",
    "LOG GPGGA ONTIME 1",
    "LOG GPGSA ONTIME 1",
    "LOG GPGSV ONTIME 1",
    "LOG GPRMC ONTIME 1",
)


def stream_output(fd: int, nmea_only: bool) -> None:
    """
    Continuously read from the receiver and print decoded ASCII lines.
    """
    logging.info("Streaming messages. Press Ctrl+C to stop.")
    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 1.0)
            if fd not in ready:
                continue

            data = os.read(fd, 4096)
            if not data:
                continue

            for raw_line in data.splitlines():
                if not raw_line:
                    continue

                text = raw_line.decode("ascii", errors="replace")
                if nmea_only and not text.startswith(("$", "<")):
                    continue
                print(text, flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        os.close(fd)
        logging.info("Closed serial port.")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send OEM7 initialization commands and display incoming messages."
    )
    parser.add_argument(
        "--port",
        default=DEFAULT_PORT,
        help=f"Serial device path (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=DEFAULT_BAUD,
        help=f"Baud rate to configure (default: {DEFAULT_BAUD})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Response timeout while sending commands (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--nmea-only",
        action="store_true",
        help="Print only NMEA-like sentences (prefix $ or <).",
    )
    parser.add_argument(
        "--extra-command",
        action="append",
        dest="extra_commands",
        default=[],
        help="Additional command string to append (can be repeated).",
    )
    parser.add_argument(
        "--no-init",
        action="store_true",
        help="Skip sending initialization commands; just stream the port.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging output.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    try:
        fd = open_serial(args.port, args.baud)
    except OSError as exc:
        logging.error("Failed to open %s: %s", args.port, exc)
        return 1
    except ValueError as exc:
        logging.error(str(exc))
        return 1

    logging.info("Opened %s at %d baud.", args.port, args.baud)

    if not args.no_init:
        command_sequence: Iterable[str] = DEFAULT_COMMANDS + tuple(args.extra_commands)
        send_commands(fd, command_sequence, args.timeout)
        # Flush any immediate binary bursts before streaming readability loop.
        termios.tcflush(fd, termios.TCIFLUSH)
    else:
        logging.info("Skipping initialization as requested.")

    stream_output(fd, args.nmea_only)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
