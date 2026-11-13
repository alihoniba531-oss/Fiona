"""续拆走查后端：在隔离环境里起 FastAPI，并把工作室导演模型换成本地假模型（不访问任何外部服务、不计真实费用）。

由 walk-backend.sh 在候选副本的 backend/ 目录下运行。假模型每次调用先等 4 秒，便于观察「进行中」状态。
"""
import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.getcwd())

import uvicorn

from studio import brain

NAMES = ('阿岚', '阿禾', '船夫')


async def options(_owner):
    return [{'id': 'qwen', 'available': True, 'label': '千问', 'model': 'qwen3.8-max'},
            {'id': 'deepseek', 'available': True, 'label': 'DeepSeek', 'model': 'deepseek-flash'}]


class Adapter:
    def __init__(self, model):
        self.model = model

    async def call(self, task, inputs, images=None, repair=None):
        await asyncio.sleep(4)
        if task == 'novel_complete':
            chapters, new = [], []
            for chapter in inputs.get('chapters', []):
                lines = [line.strip() for line in chapter['text'].splitlines() if len(line.strip()) >= 12]
                scenes = []
                for line in lines[1:3] or lines[:1]:
                    scenes.append({'location': '渡口', 'summary': line[:40], 'characters': [n for n in NAMES if n in line],
                                   'est_seconds': 100, 'change': '', 'start_anchor': line[:12]})
                chapters.append({'chapter': chapter['chapter'], 'scenes': scenes})
                if '阿禾' in chapter['text'] and not new and chapter['chapter'] == 2:
                    new.append({'name': '阿禾', 'role': '同伴', 'first_chapter': 2, 'excerpt': ''})
            output = {'chapters': chapters, 'locations': [], 'props': [], 'appearance_fills': [], 'new_characters': new}
        elif task == 'episode_plan':
            seqs = [unit['seq'] for unit in inputs.get('units', [])]
            episodes = []
            for index in range(0, len(seqs), 2):
                part = seqs[index:index + 2]
                episodes.append({'unit_from': part[0], 'unit_to': part[-1], 'title': f'渡江 · 单元 {part[0]}–{part[-1]}',
                                 'change': '局势推进一步。', 'hook': '船还没来。'})
            output = {'episodes': episodes}
        elif task == 'synopsis':
            output = {'logline': '少年过江', 'synopsis': '少年在封渡前夜过江。', 'genre': '成长', 'tone': '克制', 'themes': ['离开']}
        else:
            raise RuntimeError('unexpected task ' + task)
        return brain.BrainReply(json.dumps(output, ensure_ascii=False), {'input_tokens': 100, 'output_tokens': 50},
                                self.model, 'stop', .01)


async def get_provider(provider, username, **kwargs):
    return Adapter('deepseek-flash' if provider == 'deepseek' else 'qwen3.8-max')


brain.provider_options = options
brain.get_provider = get_provider

import main  # noqa: E402

uvicorn.run(main.app, host='127.0.0.1', port=8064)
