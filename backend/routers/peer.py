# -*- coding: utf-8 -*-
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from auth_dep import get_current_user, ws_authenticate
from database import get_accepted_matches, get_peer_messages, save_peer_message

router = APIRouter()


# ── WebSocket 真人聊天 ──────────────────────────────────────────

def make_room_id(user_a: str, user_b: str) -> str:
    """房间 ID = 两个用户名排序后拼接，确保 A-B 和 B-A 是同一个房间"""
    return "__".join(sorted([user_a, user_b]))


async def _require_peer_room_access(user: str, room_id: str) -> str:
    """校验当前用户能访问 room_id，并返回 peer 用户名。"""
    parts = room_id.split("__")
    if len(parts) != 2 or user not in parts:
        raise HTTPException(status_code=403, detail="不在该房间内")
    peer = parts[1] if parts[0] == user else parts[0]
    if peer == user:
        raise HTTPException(status_code=403, detail="房间无效")
    accepted_peers = await get_accepted_matches(user)
    if peer not in accepted_peers:
        raise HTTPException(status_code=403, detail="双方尚未互相接受匹配")
    if make_room_id(user, peer) != room_id:
        raise HTTPException(status_code=403, detail="房间无效")
    return peer


class ConnectionManager:
    def __init__(self):
        # room_id → {username: {WebSocket, ...}}
        self.rooms: dict[str, dict[str, set[WebSocket]]] = {}

    async def connect(self, room_id: str, username: str, ws: WebSocket):
        await ws.accept()
        if room_id not in self.rooms:
            self.rooms[room_id] = {}
        self.rooms[room_id].setdefault(username, set()).add(ws)

    def disconnect(self, room_id: str, username: str, ws: WebSocket):
        room = self.rooms.get(room_id)
        if not room:
            return
        sockets = room.get(username)
        if sockets is not None:
            sockets.discard(ws)
            if not sockets:
                room.pop(username, None)
        if not room:
            self.rooms.pop(room_id, None)

    async def broadcast(self, room_id: str, message: dict, exclude: WebSocket | None = None):
        room = self.rooms.get(room_id)
        if not room:
            return
        dead: list[tuple[str, WebSocket]] = []
        for uname, sockets in list(room.items()):
            for socket in list(sockets):
                if socket is exclude:
                    continue
                try:
                    await socket.send_json(message)
                except Exception:
                    dead.append((uname, socket))
        for uname, socket in dead:
            self.disconnect(room_id, uname, socket)

    async def disconnect_user(self, username: str):
        """删号/退出时关闭该用户所有真人聊天连接。"""
        targets = []
        for room_id, room in list(self.rooms.items()):
            for socket in list(room.get(username, set())):
                targets.append((room_id, socket))
        for room_id, socket in targets:
            try:
                await socket.close(code=4401)
            except Exception:
                pass
            self.disconnect(room_id, username, socket)


ws_manager = ConnectionManager()


@router.websocket("/ws/peer/{room_id}")
async def peer_chat_ws(ws: WebSocket, room_id: str):
    """WebSocket 鉴权走 HttpOnly Cookie（DEV_MODE 可用 dev_user 调试）。"""
    username = await ws_authenticate(ws)
    if not username:
        await ws.close(code=4401)
        return
    try:
        await _require_peer_room_access(username, room_id)
    except HTTPException:
        await ws.close(code=4403)
        return
    await ws_manager.connect(room_id, username, ws)
    try:
        # 连接后推送历史消息
        history = await get_peer_messages(room_id, limit=100)
        await ws.send_json({"type": "history", "messages": history})
        while True:
            try:
                data = await ws.receive_json()
            except WebSocketDisconnect:
                raise
            except (json.JSONDecodeError, ValueError, TypeError, KeyError):
                continue
            if not isinstance(data, dict):
                continue
            raw_content = data.get("content")
            if not isinstance(raw_content, str):
                continue
            content = raw_content.strip()
            if not content:
                continue
            await save_peer_message(room_id, username, content)
            msg = {"type": "message", "sender": username, "content": content,
                   "created_at": datetime.now().isoformat()}
            # 给自己确认
            await ws.send_json(msg)
            # 广播给房间里的其他人
            await ws_manager.broadcast(room_id, msg, exclude=ws)
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(room_id, username, ws)


@router.get("/peer/rooms")
async def get_peer_rooms(user: str = Depends(get_current_user)):
    """返回当前用户所有已接受匹配的对方用户名（可开启聊天的列表）"""
    peers = await get_accepted_matches(user)
    rooms = [{"peer": p, "room_id": make_room_id(user, p)} for p in peers]
    return {"username": user, "rooms": rooms}


@router.get("/peer/history/{room_id}")
async def peer_history(room_id: str, limit: int = 100, user: str = Depends(get_current_user)):
    await _require_peer_room_access(user, room_id)
    messages = await get_peer_messages(room_id, limit=limit)
    return {"room_id": room_id, "messages": messages}
