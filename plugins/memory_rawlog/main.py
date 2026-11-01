# -*- coding: utf-8 -*-
"""按天保存收到的消息原文，滚动保留若干天。

这一层不做归纳、不进 prompt，只是底稿：
出了「明明说过它却忘了」的情况时，能拿原文去对账。
"""

import json
import time
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

DATA_DIR = Path("/AstrBot/data/plugin_data/memory_rawlog")
HOT_DIR = DATA_DIR / "hot"


@register("memory_rawlog", "memory-kit", "按天保存对话原文（默认 7 天），供记忆审计和回看", "1.0.0")
class MemoryRawLog(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context, config)
        cfg = config or {}
        self.keep_days = int(cfg.get("keep_days", 7))
        self.dir = Path(cfg.get("dir") or HOT_DIR)

    async def initialize(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        self._prune()
        logger.info("memory_rawlog 已就绪：%s（保留 %d 天）", self.dir, self.keep_days)

    def _prune(self):
        cutoff = time.time() - self.keep_days * 86400
        for p in self.dir.glob("*.jsonl"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
            except Exception:
                pass

    @filter.event_message_type(
        filter.EventMessageType.PRIVATE_MESSAGE | filter.EventMessageType.GROUP_MESSAGE
    )
    async def on_message(self, event: AstrMessageEvent):
        try:
            text = (event.message_str or "").strip()
            if not text:
                return
            path = self.dir / (time.strftime("%Y-%m-%d") + ".jsonl")
            rec = {
                "ts": time.time(),
                "umo": str(event.unified_msg_origin),
                "text": text[:2000],
            }
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.debug("memory_rawlog 写入失败：%s", exc)
