"""Run each ALAS instance at configured local times while WebUI is open."""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from module.config.utils import alas_instance, filepath_config
from module.logger import logger
from module.submodule.utils import get_config_mod
from module.webui.process_manager import ProcessManager


class DailySchedule:
    def __init__(self):
        self.last_event = {}
        self.invalid_configs = set()

    @staticmethod
    def _time(value):
        if not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
            raise ValueError(f'Expected HH:MM, got {value!r}')
        return datetime.strptime(value, '%H:%M').time()

    @classmethod
    def latest_event(cls, settings, now):
        events = []
        for enabled_key, time_key, action in (
            ('StartEnabled', 'StartTime', 'start'),
            ('StopEnabled', 'StopTime', 'stop'),
        ):
            if not settings.get(enabled_key, False):
                continue
            at = cls._time(settings.get(time_key))
            for offset in (0, -1):
                day = now.date() + timedelta(days=offset)
                event_time = datetime.combine(day, at)
                if event_time <= now:
                    events.append((event_time, action == 'stop', action))
        return max(events, default=None)

    @staticmethod
    def run_action(name, action, stop_action):
        manager = ProcessManager.get_manager(name)
        if action == 'start':
            logger.info(f'Daily schedule: Start [{name}]')
            from module.webui.updater import updater

            manager.start(None, updater.event)
            return
        logger.info(f'Daily schedule: Stop [{name}], action={stop_action}')
        manager.stop()
        if manager.alive:
            raise RuntimeError(f'[{name}] is still running after stop')
        if stop_action in ('close_game', 'close_emulator'):
            manager.start(f'daily_{stop_action}')

    def tick(self, now=None):
        now = now or datetime.now()
        for name in alas_instance():
            if get_config_mod(name) != 'alas':
                continue
            path = Path(filepath_config(name))
            if not path.is_file():
                continue
            try:
                settings = json.loads(path.read_text(encoding='utf-8')).get('DailySchedule', {}).get('DailySchedule', {})
                event = self.latest_event(settings, now)
            except (OSError, ValueError, TypeError, AttributeError) as error:
                if name not in self.invalid_configs:
                    logger.warning(f'Daily schedule [{name}]: invalid settings: {error}')
                    self.invalid_configs.add(name)
                continue
            self.invalid_configs.discard(name)
            if event is None:
                self.last_event.pop(name, None)
                continue
            event_time, _, action = event
            stop_action = settings.get('StopAction', 'stop_tasks')
            if stop_action not in ('stop_tasks', 'close_game', 'close_emulator'):
                stop_action = 'stop_tasks'
            event_id = (event_time, action, stop_action)
            if self.last_event.get(name) == event_id:
                continue
            try:
                self.run_action(name, action, stop_action)
            except Exception:
                logger.exception(f'Daily schedule [{name}] failed to {action}')
                continue
            self.last_event[name] = event_id
