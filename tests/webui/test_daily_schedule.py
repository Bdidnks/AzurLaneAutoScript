import json
from datetime import datetime
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from module.webui.daily_schedule import DailySchedule


class TestDailySchedule(TestCase):
    def test_daytime_and_overnight_windows(self):
        settings = dict(StartEnabled=True, StartTime='08:00', StopEnabled=True, StopTime='10:00')
        self.assertEqual(DailySchedule.latest_event(settings, datetime(2026, 10, 25, 9))[-1], 'start')
        self.assertEqual(DailySchedule.latest_event(settings, datetime(2026, 10, 25, 11))[-1], 'stop')
        settings.update(StartTime='22:00', StopTime='02:00')
        self.assertEqual(DailySchedule.latest_event(settings, datetime(2026, 10, 25, 1))[-1], 'start')
        self.assertEqual(DailySchedule.latest_event(settings, datetime(2026, 10, 25, 3))[-1], 'stop')
        settings.update(StartTime='02:00')
        self.assertEqual(DailySchedule.latest_event(settings, datetime(2026, 10, 25, 2))[-1], 'stop')

    def test_start_and_stop_use_existing_process_controls(self):
        from unittest.mock import Mock
        manager = Mock()
        manager.alive = True
        manager.stop.side_effect = lambda: setattr(manager, 'alive', False)
        with patch('module.webui.daily_schedule.ProcessManager.get_manager', return_value=manager):
            DailySchedule.run_action('test', 'start', 'stop_tasks')
            from module.webui.updater import updater
            manager.start.assert_called_once_with(None, updater.event)
            DailySchedule.run_action('test', 'stop', 'stop_tasks')
            manager.stop.assert_called_once_with()
            self.assertEqual(manager.start.call_count, 1)
            manager.alive = True
            DailySchedule.run_action('test', 'stop', 'close_game')
            manager.start.assert_called_with('daily_close_game')
            manager.alive = True
            DailySchedule.run_action('test', 'stop', 'close_emulator')
            manager.start.assert_called_with('daily_close_emulator')
            manager.alive = False
            count = manager.start.call_count
            DailySchedule.run_action('test', 'stop', 'close_emulator')
            self.assertEqual(manager.start.call_count, count)

    def test_invalid_time(self):
        settings = dict(StartEnabled=True, StartTime='24:00')
        with self.assertRaises(ValueError):
            DailySchedule.latest_event(settings, datetime(2026, 10, 25, 9))

    def test_tick_once_per_daily_event(self):
        settings = dict(StartEnabled=True, StartTime='08:00', StopEnabled=True,
                        StopTime='10:00', StopAction='close_emulator')
        config = {'DailySchedule': {'DailySchedule': settings}}
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'test.json'
            path.write_text(json.dumps(config), encoding='utf-8')
            schedule = DailySchedule()
            with patch('module.webui.daily_schedule.alas_instance', return_value=['test']), \
                 patch('module.webui.daily_schedule.get_config_mod', return_value='alas'), \
                 patch('module.webui.daily_schedule.filepath_config', return_value=str(path)), \
                 patch.object(schedule, 'run_action') as action:
                schedule.tick(datetime(2026, 10, 25, 9))
                schedule.tick(datetime(2026, 10, 25, 9, 30))
                schedule.tick(datetime(2026, 10, 25, 11))
                schedule.tick(datetime(2026, 10, 26, 9))
                self.assertEqual(action.call_count, 3)
                self.assertEqual(action.call_args_list[0][0], ('test', 'start', 'close_emulator'))
                self.assertEqual(action.call_args_list[1][0], ('test', 'stop', 'close_emulator'))
                self.assertEqual(action.call_args_list[2][0], ('test', 'start', 'close_emulator'))
