"""Console payloads explicitly distinguish unavailable measurements."""


def telemetry(message):
    return {
        **message,
        "state": "running" if message["running"] else "ready",
        "calibrated": None,
        "rssi_dbm": None,
        "mode": None,
        "line": None,
        "channels": {
            key: message[key]
            for key in (
                "sensors",
                "line_position",
                "line_lost",
                "error",
                "battery_v",
                "motors",
                "control",
                "odometry",
            )
            if key in message
        },
    }
