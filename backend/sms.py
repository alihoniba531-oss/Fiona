# -*- coding: utf-8 -*-
"""
短信发送模块。
开发阶段：验证码直接打印到后端控制台。
上线前将 send_sms 替换为阿里云短信 SDK 调用。
"""


def send_sms(phone: str, code: str) -> bool:
    """发送短信验证码。成功返回 True，失败返回 False。"""
    # ── 上线时替换这里 ──────────────────────────────────────
    # from aliyunsdkcore.client import AcsClient
    # from aliyunsdkcore.request import CommonRequest
    # client = AcsClient(ACCESS_KEY_ID, ACCESS_KEY_SECRET, "cn-hangzhou")
    # req = CommonRequest(); req.set_action_name("SendSms"); ...
    # ──────────────────────────────────────────────────────
    print(f"\n[SMS Dev] {phone}  code: {code}  (5min)\n")
    return True
