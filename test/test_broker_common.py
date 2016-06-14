#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Copyright (C) 2015-2015: Alignak team, see AUTHORS.txt file for contributors
#
# This file is part of Alignak.
#
# Alignak is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Alignak is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Alignak.  If not, see <http://www.gnu.org/licenses/>.

import ujson
import shlex
import unittest2
import time
import subprocess
import json
from alignak_module_backend.broker.module import AlignakBackendBrok
from alignak.objects.module import Module
from alignak.brok import Brok
from alignak_backend_client.client import Backend


class TestBrokerCommon(unittest2.TestCase):

    @classmethod
    def setUpClass(cls):

        # Delete used mongo DBs
        exit_code = subprocess.call(
            shlex.split(
                'mongo %s --eval "db.dropDatabase()"' % 'alignak-backend')
        )
        assert exit_code == 0

        cls.p = subprocess.Popen(['uwsgi', '-w', 'alignakbackend:app', '--socket', '0.0.0.0:5000', '--protocol=http', '--enable-threads'])
        time.sleep(3)
        cls.backend = Backend('http://127.0.0.1:5000')
        cls.backend.login("admin", "admin", "force")
        realms = cls.backend.get_all('realm')
        for cont in realms['_items']:
            cls.realm_all = cont['_id']

        # add commands
        data = json.loads(open('cfg/command_ping.json').read())
        data['_realm'] = cls.realm_all
        data_cmd_ping = cls.backend.post("command", data)
        data = json.loads(open('cfg/command_http.json').read())
        data['_realm'] = cls.realm_all
        data_cmd_http = cls.backend.post("command", data)
        # add host
        data = json.loads(open('cfg/host_srv001.json').read())
        data['check_command'] = data_cmd_ping['_id']
        data['realm'] = cls.realm_all
        cls.data_host = cls.backend.post("host", data)
        # add 2 services
        data = json.loads(open('cfg/service_srv001_ping.json').read())
        data['host'] = cls.data_host['_id']
        data['check_command'] = data_cmd_ping['_id']
        data['_realm'] = cls.realm_all
        cls.data_srv_ping = cls.backend.post("service", data)

        data = json.loads(open('cfg/service_srv001_http.json').read())
        data['host'] = cls.data_host['_id']
        data['check_command'] = data_cmd_http['_id']
        data['_realm'] = cls.realm_all
        cls.data_srv_http = cls.backend.post("service", data)

        # Start broker module
        modconf = Module()
        modconf.module_alias = "alignakbackendarbit"
        modconf.username = "admin"
        modconf.password = "admin"
        modconf.api_url = 'http://127.0.0.1:5000'
        cls.brokmodule = AlignakBackendBrok(modconf)

    @classmethod
    def tearDownClass(cls):
        cls.p.kill()

    def test_01_get_refs_host(self):
        self.brokmodule.get_refs('livehost')

        self.assertEqual(len(self.brokmodule.ref_live['host']), 1)
        self.assertEqual(self.brokmodule.ref_live['host'][self.data_host['_id']]['initial_state'], 'UNREACHABLE')
        self.assertEqual(self.brokmodule.ref_live['host'][self.data_host['_id']]['initial_state_type'], 'HARD')

        ref = {'srv001': self.data_host['_id']}
        self.assertEqual(self.brokmodule.mapping['host'], ref)

        r = self.backend.get('livestate')
        self.assertEqual(len(r['_items']), 3)

    def test_02_get_refs_service(self):
        self.brokmodule.get_refs('liveservice')

        self.assertEqual(len(self.brokmodule.ref_live['service']), 2)
        self.assertEqual(self.brokmodule.ref_live['service'][self.data_srv_ping['_id']]['initial_state'], 'OK')
        self.assertEqual(self.brokmodule.ref_live['service'][self.data_srv_ping['_id']]['initial_state_type'], 'HARD')

        self.assertEqual(self.brokmodule.ref_live['service'][self.data_srv_http['_id']]['initial_state'], 'OK')
        self.assertEqual(self.brokmodule.ref_live['service'][self.data_srv_http['_id']]['initial_state_type'], 'HARD')

        ref = {'srv001ping': self.data_srv_ping['_id'], 'srv001http toto.com': self.data_srv_http['_id']}
        self.assertEqual(self.brokmodule.mapping['service'], ref)

    def test_03_manage_brok_host(self):

        data = json.loads(open('cfg/brok_host_srv001_up.json').read())
        b = Brok({'data': data, 'type': 'host_check_result'}, False)
        b.prepare()
        self.brokmodule.manage_brok(b)

        items = self.backend.get('livestate')
        number = 0
        for index, item in enumerate(items['_items']):
            if item['service'] == None:
                self.assertEqual(item['last_state'], 'UNREACHABLE')
                self.assertEqual(item['state'], 'UP')
                self.assertEqual(item['last_state_type'], 'HARD')
                self.assertEqual(item['state_type'], 'HARD')
                self.assertEqual(item['output'], 'PING OK - Packet loss = 0%, RTA = 0.05 ms')
                self.assertEqual(item['perf_data'], 'rta=0.049000ms;2.000000;3.000000;0.000000 pl=0%;50;80;0')
                number += 1
        self.assertEqual(1, number)

        r = self.backend.get('livestate')
        self.assertEqual(len(r['_items']), 3)

        r = self.backend.get('livesynthesis')
        self.assertEqual(len(r['_items']), 1)
        self.assertEqual(r['_items'][0]['hosts_total'], 1)
        self.assertEqual(r['_items'][0]['hosts_up_hard'], 1)
        self.assertEqual(r['_items'][0]['hosts_up_soft'], 0)
        self.assertEqual(r['_items'][0]['hosts_down_hard'], 0)
        self.assertEqual(r['_items'][0]['hosts_down_soft'], 0)
        self.assertEqual(r['_items'][0]['hosts_unreachable_hard'], 0)
        self.assertEqual(r['_items'][0]['hosts_unreachable_soft'], 0)
        self.assertEqual(r['_items'][0]['hosts_acknowledged'], 0)
        self.assertEqual(r['_items'][0]['services_total'], 2)
        self.assertEqual(r['_items'][0]['services_ok_hard'], 2)
        self.assertEqual(r['_items'][0]['services_ok_soft'], 0)
        self.assertEqual(r['_items'][0]['services_warning_hard'], 0)
        self.assertEqual(r['_items'][0]['services_warning_soft'], 0)
        self.assertEqual(r['_items'][0]['services_critical_hard'], 0)
        self.assertEqual(r['_items'][0]['services_critical_soft'], 0)
        self.assertEqual(r['_items'][0]['services_unknown_hard'], 0)
        self.assertEqual(r['_items'][0]['services_unknown_soft'], 0)

        # Add down host
        data = json.loads(open('cfg/brok_host_srv001_down.json').read())
        b = Brok({'data': data, 'type': 'host_check_result'}, False)
        b.prepare()
        self.brokmodule.manage_brok(b)

        items = self.backend.get('livestate')
        number = 0
        for index, item in enumerate(items['_items']):
            if item['service'] == None:
                self.assertEqual(item['last_state'], 'UP')
                self.assertEqual(item['state'], 'DOWN')
                self.assertEqual(item['last_state_type'], 'HARD')
                self.assertEqual(item['state_type'], 'SOFT')
                self.assertEqual(item['output'], 'CRITICAL - Plugin timed out after 10 seconds')
                self.assertEqual(item['perf_data'], '')
                number += 1
        self.assertEqual(1, number)

        r = self.backend.get('livestate')
        self.assertEqual(len(r['_items']), 3)

        r = self.backend.get('livesynthesis')
        self.assertEqual(len(r['_items']), 1)
        self.assertEqual(r['_items'][0]['hosts_total'], 1)
        self.assertEqual(r['_items'][0]['hosts_up_hard'], 0)
        self.assertEqual(r['_items'][0]['hosts_up_soft'], 0)
        self.assertEqual(r['_items'][0]['hosts_down_hard'], 0)
        self.assertEqual(r['_items'][0]['hosts_down_soft'], 1)
        self.assertEqual(r['_items'][0]['hosts_unreachable_hard'], 0)
        self.assertEqual(r['_items'][0]['hosts_unreachable_soft'], 0)
        self.assertEqual(r['_items'][0]['hosts_acknowledged'], 0)
        self.assertEqual(r['_items'][0]['services_total'], 2)
        self.assertEqual(r['_items'][0]['services_ok_hard'], 2)
        self.assertEqual(r['_items'][0]['services_ok_soft'], 0)
        self.assertEqual(r['_items'][0]['services_warning_hard'], 0)
        self.assertEqual(r['_items'][0]['services_warning_soft'], 0)
        self.assertEqual(r['_items'][0]['services_critical_hard'], 0)
        self.assertEqual(r['_items'][0]['services_critical_soft'], 0)
        self.assertEqual(r['_items'][0]['services_unknown_hard'], 0)
        self.assertEqual(r['_items'][0]['services_unknown_soft'], 0)
