# -*- coding: utf-8 -*-


def set_reminder(text: str, minutes: int) -> str:
    # 后端只跑在无头服务器上，不再起常驻定时线程（消除线程泄漏），诚实告知做不到
    return "定时提醒这个我在网页版还做不到呢～到点了我没法主动弹消息给你。要不你先用手机的闹钟提醒一下？"
