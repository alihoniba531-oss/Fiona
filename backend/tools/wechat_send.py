# -*- coding: utf-8 -*-
# Windows-only tool — stubbed for Linux server environment

def send_wechat_message(contact: str, message: str) -> str:
    return "微信发送功能仅在 Windows 客户端可用，服务器端不支持。"

def start_wechat_voice_call(contact: str) -> str:
    return "微信语音通话功能仅在 Windows 客户端可用。"

def start_wechat_video_call(contact: str) -> str:
    return "微信视频通话功能仅在 Windows 客户端可用。"
