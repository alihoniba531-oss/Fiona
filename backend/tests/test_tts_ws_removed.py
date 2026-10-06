"""Retired TTS socket must close without removing other streaming routes."""
import pytest
from starlette.websockets import WebSocketDisconnect


def test_retired_tts_socket_route_is_absent(client):
    import main

    paths = {getattr(route, "path", None) for route in main.app.routes}
    assert "/tts/" + "ws" not in paths
    assert "/ws/peer/{room_id}" in paths
    assert "/tts/stream" in paths


def test_retired_tts_socket_cannot_connect(client):
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect("/tts/" + "ws?dev_user=removed_socket_tester"):
            pass
    assert error.value.code != 4401
