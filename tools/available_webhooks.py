from os import getenv
from tools.govee.controller import govee_controller, ToggleLights

# Each entry subscribes to one SSE endpoint and queues events when data changes.
#
# Fields:
#   url       : SSE endpoint URL
#   auth      : Authorization header value
#   variable  : only trigger when this specific key changes (optional)
#   actions   : dict mapping variable values → callable(data), bypasses the model
#   prompt    : Python format string passed to the model — use {field} for SSE data keys
#   tts_text  : Python format string spoken directly     — use {field} for SSE data keys
#
# Template variables: {field} = any SSE key, {changed} = dict of changed fields, {data} = full payload

WEBHOOKS = [
    {
        "url":      "http://kyle.squirting.uk/api/subscribe",
        "auth":     getenv("KYLE_SERVER_AUTH"),
        "variable": "is_home",
        "actions": {
            True:  lambda data: govee_controller.toggle_lights(ToggleLights(action="on",  room="bedroom")),
            False: lambda data: govee_controller.toggle_lights(ToggleLights(action="off", room="bedroom")),
        },
    },
]
