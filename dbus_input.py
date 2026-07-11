import queue
import threading

import gi  # noqa: E402

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from utils import log_and_print  # noqa: E402

_text_queue = queue.Queue()

DBUS_INTERFACE = "org.freedesktop.IBus.STT.CommandMode"
DBUS_SIGNAL = "CommandText"
DBUS_PATH = "/org/freedesktop/IBus/STT"


def _on_command_text(connection, sender, path, interface, signal, params):
    text = params.unpack()[0]
    log_and_print(f'[IBUS] Received: "{text}"')
    _text_queue.put(text)


def _listener_thread():
    ctx = GLib.MainContext.new()
    ctx.push_thread_default()

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    bus.signal_subscribe(
        None,
        DBUS_INTERFACE,
        DBUS_SIGNAL,
        DBUS_PATH,
        None,
        Gio.DBusSignalFlags.NONE,
        _on_command_text,
    )

    loop = GLib.MainLoop.new(ctx, False)
    loop.run()


def start_dbus_listener():
    thread = threading.Thread(target=_listener_thread, daemon=True)
    thread.start()
    log_and_print("[IBUS] D-Bus listener started, waiting for CommandText signals")


def wait_for_command_text():
    return _text_queue.get()
