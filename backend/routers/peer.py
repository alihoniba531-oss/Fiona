# -*- coding: utf-8 -*-
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
        # room_id → {username: WebSocket}
        self.rooms: dict[str, dict[str, WebSocket]] = {}

    async def connect(self, room_id: str, username: str, ws: WebSocket):
        await ws.accept()
        if room_id not in self.rooms:
            self.rooms[room_id] = {}
        self.rooms[room_id][username] = ws

    def disconnect(self, room_id: str, username: str):
        if room_id in self.rooms:
            self.rooms[room_id].pop(username, None)
            if not self.rooms[room_id]:
                del self.rooms[room_id]

    async def broadcast(self, room_id: str, message: dict, exclude: str | None = None):
        if room_id not in self.rooms:
            return
        dead = []
        for uname, ws in self.rooms[room_id].items():
            if uname == exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(uname)
        for uname in dead:
            self.disconnect(room_id, uname)


ws_manager = ConnectionManager()


@router.websocket("/ws/peer/{room_id}")
async def peer_chat_ws(ws: WebSocket, room_id: str):
    """WebSocket 鉴权走 query: ?token=<jwt>（或 DEV_MODE 下 ?dev_user=<name>）"""
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
    # 连接后推送历史消息
    history = await get_peer_messages(room_id, limit=100)
    await ws.send_json({"type": "history", "messages": history})
    try:
        while True:
            data = await ws.receive_json()
            content = (data.get("content") or "").strip()
            if not content:
                continue
            await save_peer_message(room_id, username, content)
            msg = {"type": "message", "sender": username, "content": content,
                   "created_at": datetime.now().isoformat()}
            # 给自己确认
            await ws.send_json(msg)
            # 广播给房间里的其他人
            await ws_manager.broadcast(room_id, msg, exclude=username)
    except WebSocketDisconnect:
        ws_manager.disconnect(room_id, username)


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
