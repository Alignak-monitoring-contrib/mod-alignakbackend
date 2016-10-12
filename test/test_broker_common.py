# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2016: Alignak contrib team, see AUTHORS.txt file for contributors
#
# This file is part of Alignak contrib projet.
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

import os
import shlex
import time
import requests
import subprocess
import json
import unittest2
from alignak_module_backend.broker.module import AlignakBackendBroker
from alignak.objects.module import Module
from alignak.brok import Brok
from alignak_backend_client.client import Backend


class TestBrokerConnection(unittest2.TestCase):

    @classmethod
    def setUpClass(cls):

        # Set test mode for alignak backend
        os.environ['TEST_ALIGNAK_BACKEND'] = '1'
        os.environ['ALIGNAK_BACKEND_MONGO_DBNAME'] = 'alignak-module-backend-test'

        # Delete used mongo DBs
        print ("Deleting Alignak backend DB...")
        exit_code = subprocess.call(
            shlex.split(
                'mongo %s --eval "db.dropDatabase()"' % os.environ['ALIGNAK_BACKEND_MONGO_DBNAME'])
        )
        assert exit_code == 0

        cls.p = subprocess.Popen(['uwsgi', '--plugin', 'python', '-w', 'alignakbackend:app',
                                  '--socket', '0.0.0.0:5000',
                                  '--protocol=http', '--enable-threads', '--pidfile',
                                  '/tmp/uwsgi.pid'])
        time.sleep(3)

        endpoint = 'http://127.0.0.1:5000'

        # Backend authentication
        headers = {'Content-Type': 'application/json'}
        params = {'username': 'admin', 'password': 'admin', 'action': 'generate'}
        # Get admin user token (force regenerate)
        response = requests.post(endpoint + '/login', json=params, headers=headers)
        resp = response.json()
        cls.token = resp['token']
        cls.auth = requests.auth.HTTPBasicAuth(cls.token, '')

        # Get admin user
        response = requests.get(endpoint + '/user', auth=cls.auth)
        resp = response.json()
        cls.user_admin = resp['_items'][0]

        # Get realms
        response = requests.get(endpoint + '/realm', auth=cls.auth)
        resp = response.json()
        cls.realmAll_id = resp['_items'][0]['_id']

        # Add a user
        data = {'name': 'test', 'password': 'test', 'back_role_super_admin': False,
                'host_notification_period': cls.user_admin['host_notification_period'],
                'service_notification_period': cls.user_admin['service_notification_period'],
                '_realm': cls.realmAll_id}
        response = requests.post(endpoint + '/user', json=data, headers=headers,
                                 auth=cls.auth)
        resp = response.json()
        print("Created a new user: %s" % resp)

    @classmethod
    def tearDownClass(cls):
        cls.p.kill()

    def test_00_connection_accepted(self):
        # Start broker module with admin user
        modconf = Module()
        modconf.module_alias = "backend_broker"
        modconf.username = "admin"
        modconf.password = "admin"
        modconf.api_url = 'http://127.0.0.1:5000'
        broker_module = AlignakBackendBroker(modconf)

        self.assertTrue(broker_module.backendConnection())
        self.assertTrue(broker_module.logged_in)

    def test_01_connection_refused(self):
        # Start broker module with not allowed user
        modconf = Module()
        modconf.module_alias = "backend_broker"
        modconf.username = "test"
        modconf.password = "test"
        modconf.api_url = 'http://127.0.0.1:5000'
        broker_module = AlignakBackendBroker(modconf)

        self.assertFalse(broker_module.backendConnection())
        self.assertFalse(broker_module.logged_in)


class TestBrokerCommon(unittest2.TestCase):

    @classmethod
    def setUpClass(cls):
        # Set test mode for alignak backend
        os.environ['TEST_ALIGNAK_BACKEND'] = '1'
        os.environ['ALIGNAK_BACKEND_MONGO_DBNAME'] = 'alignak-module-backend-test'

        # Delete used mongo DBs
        print ("Deleting Alignak backend DB...")
        exit_code = subprocess.call(
            shlex.split(
                'mongo %s --eval "db.dropDatabase()"' % os.environ[
                    'ALIGNAK_BACKEND_MONGO_DBNAME'])
        )
        assert exit_code == 0

        cls.p = subprocess.Popen(['uwsgi', '--plugin', 'python', '-w', 'alignakbackend:app',
                                  '--socket', '0.0.0.0:5000',
                                  '--protocol=http', '--enable-threads', '--pidfile',
                                  '/tmp/uwsgi.pid'])
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
        del data['realm']
        data['_realm'] = cls.realm_all
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
        modconf.module_alias = "backend_broker"
        modconf.username = "admin"
        modconf.password = "admin"
        modconf.api_url = 'http://127.0.0.1:5000'
        cls.brokmodule = AlignakBackendBroker(modconf)

    @classmethod
    def tearDownClass(cls):
        cls.p.kill()

    def test_01_get_refs_host(self):
        self.brokmodule.get_refs('livestate_host')

        self.assertEqual(len(self.brokmodule.ref_live['host']), 1)
        self.assertEqual(
            self.brokmodule.ref_live['host'][self.data_host['_id']]['initial_state'],'UNREACHABLE'
        )
        self.assertEqual(
            self.brokmodule.ref_live['host'][self.data_host['_id']]['initial_state_type'], 'HARD'
        )

        ref = {'srv001': self.data_host['_id']}
        self.assertEqual(self.brokmodule.mapping['host'], ref)

        params = {
            'where': '{"name": "srv001"}'
        }
        r = self.backend.get('host', params)
        self.assertEqual(len(r['_items']), 1)

    def test_02_get_refs_service(self):
        self.brokmodule.get_refs('livestate_service')

        self.assertEqual(len(self.brokmodule.ref_live['service']), 2)
        self.assertEqual(
            self.brokmodule.ref_live['service'][self.data_srv_ping['_id']]['initial_state'],
            'UNKNOWN'
        )
        self.assertEqual(
            self.brokmodule.ref_live['service'][self.data_srv_ping['_id']]['initial_state_type'],
            'HARD'
        )

        self.assertEqual(
            self.brokmodule.ref_live['service'][self.data_srv_http['_id']]['initial_state'],
            'UNKNOWN'
        )
        self.assertEqual(
            self.brokmodule.ref_live['service'][self.data_srv_http['_id']]['initial_state_type'],
            'HARD'
        )

        ref = {'srv001ping': self.data_srv_ping['_id'],
               'srv001http toto.com': self.data_srv_http['_id']}
        self.assertEqual(self.brokmodule.mapping['service'], ref)

    def test_03_manage_brok_host(self):

        data = json.loads(open('cfg/brok_host_srv001_up.json').read())
        b = Brok({'data': data, 'type': 'host_check_result'}, False)
        b.prepare()
        self.brokmodule.manage_brok(b)

        params = {'where': '{"name": "srv001"}'}
        r = self.backend.get('host', params)
        self.assertEqual(len(r['_items']), 1)
        number = 0
        for index, item in enumerate(r['_items']):
            self.assertEqual(item['ls_last_state'], 'UNREACHABLE')
            self.assertEqual(item['ls_state'], 'UP')
            self.assertEqual(item['ls_last_state_type'], 'HARD')
            self.assertEqual(item['ls_state_type'], 'HARD')
            self.assertEqual(item['ls_output'], 'PING OK - Packet loss = 0%, RTA = 0.05 ms')
            self.assertEqual(item['ls_perf_data'],
                             'rta=0.049000ms;2.000000;3.000000;0.000000 pl=0%;50;80;0')
            number += 1
        self.assertEqual(1, number)

        r = self.backend.get('service')
        self.assertEqual(len(r['_items']), 2)

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
        self.assertEqual(r['_items'][0]['hosts_in_downtime'], 0)
        self.assertEqual(r['_items'][0]['services_total'], 2)
        self.assertEqual(r['_items'][0]['services_ok_hard'], 0)
        self.assertEqual(r['_items'][0]['services_ok_soft'], 0)
        self.assertEqual(r['_items'][0]['services_warning_hard'], 0)
        self.assertEqual(r['_items'][0]['services_warning_soft'], 0)
        self.assertEqual(r['_items'][0]['services_critical_hard'], 0)
        self.assertEqual(r['_items'][0]['services_critical_soft'], 0)
        self.assertEqual(r['_items'][0]['services_unknown_hard'], 2)
        self.assertEqual(r['_items'][0]['services_unknown_soft'], 0)
        self.assertEqual(r['_items'][0]['services_acknowledged'], 0)
        self.assertEqual(r['_items'][0]['services_in_downtime'], 0)

        # Add down host
        data = json.loads(open('cfg/brok_host_srv001_down.json').read())
        b = Brok({'data': data, 'type': 'host_check_result'}, False)
        b.prepare()
        self.brokmodule.manage_brok(b)

        params = {'where': '{"name": "srv001"}'}
        r = self.backend.get('host', params)
        self.assertEqual(len(r['_items']), 1)
        number = 0
        for index, item in enumerate(r['_items']):
            self.assertEqual(item['ls_last_state'], 'UP')
            self.assertEqual(item['ls_state'], 'DOWN')
            self.assertEqual(item['ls_last_state_type'], 'HARD')
            self.assertEqual(item['ls_state_type'], 'SOFT')
            self.assertEqual(item['ls_output'], 'CRITICAL - Plugin timed out after 10 seconds')
            self.assertEqual(item['ls_perf_data'], '')
            number += 1
        self.assertEqual(1, number)

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
        self.assertEqual(r['_items'][0]['hosts_in_downtime'], 0)
        self.assertEqual(r['_items'][0]['services_total'], 2)
        self.assertEqual(r['_items'][0]['services_ok_hard'], 0)
        self.assertEqual(r['_items'][0]['services_ok_soft'], 0)
        self.assertEqual(r['_items'][0]['services_warning_hard'], 0)
        self.assertEqual(r['_items'][0]['services_warning_soft'], 0)
        self.assertEqual(r['_items'][0]['services_critical_hard'], 0)
        self.assertEqual(r['_items'][0]['services_critical_soft'], 0)
        self.assertEqual(r['_items'][0]['services_unknown_hard'], 2)
        self.assertEqual(r['_items'][0]['services_unknown_soft'], 0)
        self.assertEqual(r['_items'][0]['services_acknowledged'], 0)
        self.assertEqual(r['_items'][0]['services_in_downtime'], 0)
