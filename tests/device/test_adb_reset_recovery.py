import time
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch

from module.device.connection import Connection
from module.exception import RequestHumanTakeover
from module.map.map_grids import SelectedGrids


class TestAdbResetRecovery(TestCase):
    def setUp(self):
        self.connection = Connection.__new__(Connection)
        self.connection.config = SimpleNamespace(Emulator_AdbRestart=True)
        self.reset = ConnectionResetError(10054, 'connection reset')

    def test_fresh_socket_recovers_without_server_restart(self):
        devices = object()
        with patch.object(self.connection, '_list_device_once', side_effect=[self.reset, devices]) as query, \
             patch.object(self.connection, 'adb_restart') as restart, \
             patch('module.device.connection.time.sleep'):
            self.assertIs(self.connection.list_device(), devices)
        self.assertEqual(query.call_count, 2)
        restart.assert_not_called()

    def test_server_restarts_once_after_second_reset(self):
        devices = object()
        with patch.object(self.connection, '_list_device_once', side_effect=[self.reset, self.reset, devices]) as query, \
             patch.object(self.connection, 'adb_restart') as restart, \
             patch.object(self.connection, 'adb_start_server') as start_server, \
             patch('module.device.connection.time.sleep'):
            self.assertIs(self.connection.list_device(), devices)
        self.assertEqual(query.call_count, 3)
        restart.assert_called_once_with()
        start_server.assert_called_once_with()

    def test_device_connect_recovers_without_reopening_alas(self):
        self.connection.config.DEVICE_OVER_HTTP = False
        self.connection.serial = '127.0.0.1:16384'
        client = Mock()
        client.connect.side_effect = [self.reset, 'connected to 127.0.0.1:16384']
        self.connection.adb_client = client
        with patch.object(self.connection, 'list_device', return_value=SelectedGrids([])), \
             patch.object(self.connection, 'adb_restart') as restart, \
             patch('module.device.connection.time.sleep'):
            self.assertTrue(self.connection.adb_connect(wait_device=False))
        self.assertEqual(client.connect.call_count, 2)
        restart.assert_not_called()

    def test_device_connect_restarts_server_after_second_reset(self):
        self.connection.config.DEVICE_OVER_HTTP = False
        self.connection.serial = '127.0.0.1:16384'
        client = Mock()
        client.connect.side_effect = [self.reset, self.reset, 'connected to 127.0.0.1:16384']
        self.connection.adb_client = client
        with patch.object(self.connection, 'list_device', return_value=SelectedGrids([])), \
             patch.object(self.connection, 'adb_restart') as restart, \
             patch.object(self.connection, 'adb_start_server') as start_server, \
             patch('module.device.connection.time.sleep'):
            self.assertTrue(self.connection.adb_connect(wait_device=False))
        self.assertEqual(client.connect.call_count, 3)
        restart.assert_called_once_with()
        start_server.assert_called_once_with()

    def test_normal_device_list_is_preserved(self):
        protocol = Mock()
        protocol.read_string_block.return_value = '127.0.0.1:16384\tdevice\n'
        client = MagicMock()
        client._connect.return_value.__enter__.return_value = protocol
        self.connection.adb_client = client
        devices = self.connection._list_device_once()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].serial, '127.0.0.1:16384')
        self.assertEqual(devices[0].status, 'device')

    def test_persistent_reset_stops_after_three_queries(self):
        with patch.object(self.connection, '_list_device_once', side_effect=self.reset) as query, \
             patch.object(self.connection, 'adb_restart') as restart, \
             patch.object(self.connection, 'adb_start_server'), \
             patch('module.device.connection.time.sleep'):
            with self.assertRaises(RequestHumanTakeover):
                self.connection.list_device()
        self.assertEqual(query.call_count, 3)
        restart.assert_called_once_with()

    def test_restart_setting_and_cooldown_are_respected(self):
        for enabled, recently_restarted in ((False, False), (True, True)):
            self.connection.config.Emulator_AdbRestart = enabled
            if recently_restarted:
                self.connection._adb_reset_last_restart = time.monotonic()
            with patch.object(self.connection, '_list_device_once', side_effect=self.reset) as query, \
                 patch.object(self.connection, 'adb_restart') as restart, \
                 patch('module.device.connection.time.sleep'):
                with self.assertRaises(RequestHumanTakeover):
                    self.connection.list_device()
            self.assertEqual(query.call_count, 2)
            restart.assert_not_called()
