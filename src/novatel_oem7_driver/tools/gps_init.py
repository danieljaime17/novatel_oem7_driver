#!/usr/bin/env python3
"""
Utility to send NovAtel OEM7 initialization commands over a USB serial port.

The script reads the standard command lists shipped with the driver and plays
them back to the receiver. It depends only on the Python 3 standard library.
"""

import argparse
import logging
import os
import select
import sys
import termios
import time
from pathlib import Path
from typing import Iterable, List, Sequence

try:
    import fcntl
except ImportError:  # pragma: no cover - platforms without fcntl (Windows)
    fcntl = None  # type: ignore[assignment]


DEFAULT_PORT = "/dev/ttyUSB1"
DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 1.5


def build_default_command_files(script_path: Path) -> List[Path]:
    config_dir = script_path.parents[1] / "config"
    return [
        config_dir / "std_init_commands.yaml",
        config_dir / "ext_parameteres.yaml",
    ]


def parse_command_file(path: Path) -> List[str]:
    commands: List[str] = []
    if not path.exists():
        logging.debug("Command file %s not found, skipping.", path)
        return commands

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("-"):
            continue

        # Remove inline comments.
        if "#" in line:
            line = line.split("#", 1)[0].strip()

        if not line.startswith("-"):
            continue

        # Expect YAML list with quoted string: - "COMMAND ..."
        first_quote = line.find('"')
        last_quote = line.rfind('"')
        if first_quote != -1 and last_quote > first_quote:
            command = line[first_quote + 1 : last_quote].strip()
        else:
            # Fallback: take text after "-".
            command = line[1:].strip()

        if command:
            commands.append(command)

    return commands


def load_command_sequence(paths: Sequence[Path], extra: Sequence[str]) -> List[str]:
    sequence: List[str] = []

    for path in paths:
        sequence.extend(parse_command_file(path))

    sequence.extend(extra)

    # Deduplicate consecutive duplicates while preserving order.
    deduped: List[str] = []
    for cmd in sequence:
        if not deduped or deduped[-1] != cmd:
            deduped.append(cmd)
    return deduped


def configure_port(fd: int, baud: int) -> None:
    baud_map = {
        115200: termios.B115200,
        57600: termios.B57600,
        38400: termios.B38400,
        19200: termios.B19200,
        9600: termios.B9600,
        4800: termios.B4800,
    }

    baud_const = baud_map.get(baud)
    if baud_const is None:
        raise ValueError(f"Unsupported baud rate: {baud}")

    attrs = termios.tcgetattr(fd)
    # Input flags, output flags.
    attrs[0] = termios.IGNPAR
    attrs[1] = 0
    # Control flags: 8N1, local connection, enable receiver.
    attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
    # Local modes: raw input.
    attrs[3] = 0
    # Input and output speeds.
    attrs[4] = baud_const
    attrs[5] = baud_const
    # Control characters: non-blocking reads with timeout.
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 20  # 2.0s timeout (units of 0.1s)

    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)

    if fcntl is not None:
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)


def open_serial(port: str, baud: int) -> int:
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        configure_port(fd, baud)
    except Exception:
        os.close(fd)
        raise
    return fd


def read_response(fd: int, timeout: float) -> str:
    deadline = time.time() + timeout
    buffer = bytearray()

    while time.time() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.1)
        if fd not in ready:
            continue

        chunk = os.read(fd, 4096)
        if not chunk:
            continue

        buffer.extend(chunk)
        if b"\n" in chunk or b"\r" in chunk:
            break

    if not buffer:
        return ""

    return buffer.decode("ascii", errors="replace").strip()


def send_commands(fd: int, commands: Iterable[str], timeout: float) -> None:
    for index, cmd in enumerate(commands, start=1):
        payload = (cmd + "\r\n").encode("ascii", errors="ignore")
        logging.info("[%02d] -> %s", index, cmd)
        os.write(fd, payload)

        response = read_response(fd, timeout)
        if response:
            logging.info("[%02d] <- %s", index, response)
        else:
            logging.info("[%02d] <- (no response)", index)

        time.sleep(0.1)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send NovAtel OEM7 initialization commands over a USB serial port."
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
        help=f"Response timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--command-file",
        action="append",
        dest="command_files",
        help="Additional YAML file to parse for command strings (can be repeated).",
    )
    parser.add_argument(
        "--extra-command",
        action="append",
        dest="extra_commands",
        default=[],
        help="Extra command string to append to the sequence (can be repeated).",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Print the resolved command sequence without sending anything.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    script_path = Path(__file__).resolve()
    default_files = build_default_command_files(script_path)
    user_files = [Path(p).expanduser() for p in args.command_files or []]
    command_files = default_files + user_files

    commands = load_command_sequence(command_files, args.extra_commands)

    if not commands:
        logging.error("No commands resolved from: %s", ", ".join(str(p) for p in command_files))
        return 1

    logging.info("Resolved %d commands.", len(commands))
    if args.list_only:
        for idx, cmd in enumerate(commands, start=1):
            print(f"[{idx:02d}] {cmd}")
        return 0

    try:
        fd = open_serial(args.port, args.baud)
    except OSError as exc:
        logging.error("Failed to open %s: %s", args.port, exc)
        return 1
    except ValueError as exc:
        logging.error(str(exc))
        return 1

    logging.info("Opened %s at %d baud.", args.port, args.baud)
    try:
        send_commands(fd, commands, args.timeout)
    finally:
        os.close(fd)
        logging.info("Closed %s.", args.port)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
