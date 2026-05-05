#!/usr/bin/python3

import secrets

import dbus
from gi.repository import GLib
from dbus.mainloop.glib import DBusGMainLoop


def new_request_path() -> tuple[str, str]:
    """
    Get request path and token.

    :return: Tuple with the resulting request strings.
    :rtype: tuple[str, str]
    """

    sender_name = bus.get_unique_name()[1:].replace(".", "_")
    request_token = f"screenshot_{secrets.token_hex(16)}"
    request_path = f"/org/freedesktop/portal/desktop/request/{sender_name}/{request_token}"
    return (request_path, request_token)


def screenshot_call(method, callback, parent_window="") -> None:
    """
    Screenshot call.

    :param method: DBus method to call.
    :type method: dbus method
    :param callback: Function to call on response.
    :type callback: function
    :param parent_window: Parent window.
    :type parent_window: str
    """

    (request_path, request_token) = new_request_path()
    options = {
        "handle_token": request_token
    }

    bus.add_signal_receiver(
        callback,
        "Response",
        "org.freedesktop.portal.Request",
        "org.freedesktop.portal.Desktop",
        request_path,
    )

    method(
        parent_window,
        options,
        dbus_interface="org.freedesktop.portal.Screenshot"
    )


def on_capture_response(response, result) -> None:
    """
    Capture response.

    :param response: Return code of response.
    :type response: int
    :param result: Results that will be returned.
    :type result: dict
    """

    if response == 0:
        print(result["uri"])
    else:
        print(f"Screenshot failed: {response}")

    loop.quit()


def permission_store_manipulation() -> None:
    """
    Manipulating permission store to not see the confirmation dialog on Fedora.
    """

    permission_store = bus.get_object(
        "org.freedesktop.impl.portal.PermissionStore",
        "/org/freedesktop/impl/portal/PermissionStore"
    )
    permission_store_interface = dbus.Interface(
        permission_store,
        dbus_interface="org.freedesktop.impl.portal.PermissionStore"
    )

    permission_store_interface.Set(
        "screenshot",
        dbus.Boolean(True),
        "screenshot",
        {"": ["yes"]},
        dbus.Byte(0x00)
    )

    permission_store_interface.Lookup("screenshot", "screenshot")


DBusGMainLoop(set_as_default=True)

loop = GLib.MainLoop()

bus = dbus.SessionBus()

portal = bus.get_object(
    "org.freedesktop.portal.Desktop",
    "/org/freedesktop/portal/desktop",
)

permission_store_manipulation()

screenshot_call(portal.Screenshot, on_capture_response)


try:
    loop.run()
except KeyboardInterrupt:
    loop.quit()

