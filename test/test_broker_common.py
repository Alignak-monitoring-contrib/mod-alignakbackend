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
import logging
import unittest2

# Configure logger
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)8s - %(message)s')
# Name the logger to get the backend client logs
# logger = logging.getLogger('host-simulator')
# logger.setLevel('INFO')

from alignak_module_backend.broker.module import AlignakBackendBroker
from alignak.objects.module import Module
from alignak.brok import Brok
from alignak_backend_client.client import Backend
#
# # Set the module log to DEBUG level
# logging.getLogger("alignak.module.backend_broker").setLevel(logging.DEBUG).setLevel('DEBUG')


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
        print(("Created a new user: %s" % resp))

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

        self.assertTrue(broker_module.backend_connection())
        self.assertTrue(broker_module.logged_in)

    def test_01_connection_refused(self):
        # Start broker module with not allowed user
        modconf = Module()
        modconf.module_alias = "backend_broker"
        modconf.username = "test"
        modconf.password = "test"
        modconf.api_url = 'http://127.0.0.1:5000'
        broker_module = AlignakBackendBroker(modconf)

        self.assertFalse(broker_module.backend_connection())
        self.assertFalse(broker_module.logged_in)

    def test_02_connection_accepted(self):
        # Start broker module with admin user token
        modconf = Module()
        modconf.module_alias = "backend_broker"
        # modconf.username = "admin"
        # modconf.password = "admin"
        modconf.token = self.user_admin["token"]
        modconf.api_url = 'http://127.0.0.1:5000'
        broker_module = AlignakBackendBroker(modconf)

        self.assertTrue(broker_module.backend_connection())
        self.assertTrue(broker_module.logged_in)


class TestBrokerCommon(unittest2.TestCase):

    @classmethod
    def setUpClass(cls):
        # Set test mode for alignak backend
        os.environ['TEST_ALIGNAK_BACKEND'] = '1'
        os.environ['ALIGNAK_BACKEND_MONGO_DBNAME'] = 'alignak-module-backend-test'
        os.environ['ALIGNAK_BACKEND_CONFIGURATION_FILE'] = './cfg/settings/settings.json'

        if os.path.exists('/tmp/alignak-backend_alignak-module-backend-test.log'):
            os.remove('/tmp/alignak-backend_alignak-module-backend-test.log')

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

        cls.backend = Backend('http://127.0.0.1:5000')
        cls.backend.login("admin", "admin", "force")
        realms = cls.backend.get_all('realm')
        for cont in realms['_items']:
            cls.realm_all = cont['_id']

        users = cls.backend.get_all('user')
        for user in users['_items']:
            if user['name'] == 'admin':
                cls.admin_user = user

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
        modconf.python_name = "alignak_module_backend.broker"
        modconf.module_alias = "backend_broker"
        modconf.username = "admin"
        modconf.password = "admin"
        modconf.api_url = 'http://127.0.0.1:5000'
        modconf.log_level = "DEBUG"
        cls.brokmodule = AlignakBackendBroker(modconf)

    @classmethod
    def tearDownClass(cls):
        cls.p.kill()

    def test_01_get_refs(self):
        """Get hosts, services and users references"""
        # Default reload protection delay
        self.assertEqual(self.brokmodule.load_protect_delay, 300)

        now = int(time.time())
        # First call loads the corresponding objects
        self.brokmodule.get_refs()
        # Stored loaded hosts timestamp
        self.assertEqual(self.brokmodule.last_load, now)

        # Hosts
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

        # Services
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

        ref = {'srv001__ping': self.data_srv_ping['_id'],
               'srv001__http toto.com': self.data_srv_http['_id']}
        self.assertEqual(self.brokmodule.mapping['service'], ref)

        # Users
        self.assertEqual(len(self.brokmodule.ref_live['user']), 1)
        self.assertEqual(
            self.brokmodule.ref_live['user'][self.admin_user['_id']]['_realm'],
            self.admin_user['_realm']
        )

        ref = {'admin': self.admin_user['_id']}
        self.assertEqual(self.brokmodule.mapping['user'], ref)

        # A call some seconds later the first one do not reload the objects
        time.sleep(3)
        self.brokmodule.get_refs()
        # Stored loaded host timestamp did not changed
        self.assertEqual(self.brokmodule.last_load, now)

    def test_03_1_manage_brok_host(self):
        """Test host livestate is updated with an alignak brok"""
        self.brokmodule.get_refs()
        self.assertEqual(len(self.brokmodule.ref_live['host']), 1)

        # Initial host state as created in the backend
        # ------
        params = {'where': '{"name": "srv001"}'}
        r = self.backend.get('host', params)
        self.assertEqual(len(r['_items']), 1)
        number = 0
        for index, item in enumerate(r['_items']):
            self.assertEqual(item['ls_state'], 'UNREACHABLE')
            self.assertEqual(item['ls_state_type'], 'HARD')
            self.assertEqual(item['ls_state_id'], 3)

            self.assertEqual(item['ls_acknowledged'], False)
            self.assertEqual(item['ls_acknowledgement_type'], 1)
            self.assertEqual(item['ls_downtimed'], False)

            self.assertEqual(item['ls_last_check'], 0)
            self.assertEqual(item['ls_last_state'], 'UNREACHABLE')
            self.assertEqual(item['ls_last_state_type'], 'HARD')
            self.assertEqual(item['ls_last_state_changed'], 0)
            self.assertEqual(item['ls_next_check'], 0)

            self.assertEqual(item['ls_output'], '')
            self.assertEqual(item['ls_long_output'], '')
            self.assertEqual(item['ls_perf_data'], '')

            self.assertEqual(item['ls_current_attempt'], 0)
            # self.assertEqual(item['ls_max_attempts'], 0)
            self.assertEqual(item['ls_latency'], 0.0)
            self.assertEqual(item['ls_execution_time'], 0.0)

            self.assertEqual(item['ls_passive_check'], False)

            self.assertEqual(item['ls_last_hard_state_changed'], 0)

            self.assertEqual(item['ls_last_time_up'], 0)
            self.assertEqual(item['ls_last_time_down'], 0)
            self.assertEqual(item['ls_last_time_unknown'], 0)
            self.assertEqual(item['ls_last_time_unreachable'], 0)
            number += 1
        self.assertEqual(1, number)

        # Simulate an host UP brok
        data = json.loads(open('cfg/brok_host_srv001_up.json').read())
        b = Brok({'data': data, 'type': 'host_check_result'}, False)
        # Simulate the main module function
        b.prepare()
        self.brokmodule.manage_brok(b)
        # Check the log check results prepared list
        assert len(self.brokmodule.logcheckresults) == 1
        print(("LCR: %s" % self.brokmodule.logcheckresults[0]))
        # Send data to the backend
        self.brokmodule.send_to_backend('lcrs', '', '')

        params = {'where': '{"name": "srv001"}'}
        r = self.backend.get('host', params)
        self.assertEqual(len(r['_items']), 1)
        number = 0
        updated = 0
        for index, item in enumerate(r['_items']):
            print(("Item: %s is %s" % (item['name'], item['ls_state'])))
            self.assertEqual(item['ls_state'], 'UP')
            self.assertEqual(item['ls_state_id'], 0)
            self.assertEqual(item['ls_state_type'], 'HARD')
            self.assertEqual(item['ls_last_check'], 1444427104)
            self.assertEqual(item['ls_last_state'], 'UNREACHABLE')
            self.assertEqual(item['ls_last_state_type'], 'HARD')
            self.assertEqual(item['ls_last_state_changed'], 1444427108)
            self.assertEqual(item['ls_output'], 'PING OK - Packet loss = 0%, RTA = 0.05 ms')
            self.assertEqual(item['ls_long_output'], 'Long output ...')
            self.assertEqual(item['ls_perf_data'],
                             'rta=0.049000ms;2.000000;3.000000;0.000000 pl=0%;50;80;0')
            self.assertEqual(item['ls_acknowledged'], False)
            self.assertEqual(item['ls_downtimed'], False)
            self.assertEqual(item['ls_execution_time'], 3.1496069431000002)
            self.assertEqual(item['ls_latency'], 0.2317881584)
            updated = item['_updated']
            number += 1
        self.assertEqual(1, number)

        # Simulate an host next check brok
        data = json.loads(open('cfg/brok_host_srv001_next_check.json').read())
        b = Brok({'data': data, 'type': 'host_next_schedule'}, False)
        b.prepare()
        assert self.brokmodule.manage_brok(b) is True

        params = {'where': '{"name": "srv001"}'}
        r = self.backend.get('host', params)
        self.assertEqual(len(r['_items']), 1)
        number = 0
        new_updated = 0
        for index, item in enumerate(r['_items']):
            self.assertEqual(item['ls_state'], 'UP')
            self.assertEqual(item['ls_state_id'], 0)
            self.assertEqual(item['ls_state_type'], 'HARD')
            self.assertEqual(item['ls_last_check'], 1444427104)
            self.assertEqual(item['ls_last_state'], 'UNREACHABLE')
            self.assertEqual(item['ls_last_state_type'], 'HARD')
            self.assertEqual(item['ls_last_state_changed'], 1444427108)
            self.assertEqual(item['ls_output'], 'PING OK - Packet loss = 0%, RTA = 0.05 ms')
            self.assertEqual(item['ls_long_output'], 'Long output ...')
            self.assertEqual(item['ls_perf_data'],
                             'rta=0.049000ms;2.000000;3.000000;0.000000 pl=0%;50;80;0')
            self.assertEqual(item['ls_acknowledged'], False)
            self.assertEqual(item['ls_downtimed'], False)
            self.assertEqual(item['ls_execution_time'], 3.1496069431000002)
            self.assertEqual(item['ls_latency'], 0.2317881584)
            # Next check !
            self.assertEqual(item['ls_next_check'], 1444428104)
            new_updated = item['_updated']
            number += 1
        self.assertEqual(1, number)
        # The item do not have its _updated field changed!
        self.assertEqual(updated, new_updated)

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

        # Simulate an host DOWN brok
        data = json.loads(open('cfg/brok_host_srv001_down.json').read())
        b = Brok({'data': data, 'type': 'host_check_result'}, False)
        # Simulate the main module function
        b.prepare()
        self.brokmodule.manage_brok(b)
        # Check the log check results prepared list
        assert len(self.brokmodule.logcheckresults) == 1
        # Send data to the backend
        self.brokmodule.send_to_backend('lcrs', '', '')

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
            new_updated = item['_updated']
            number += 1
        self.assertEqual(1, number)
        print(("Updated: %s" % new_updated))
        # The item do not have its _updated field changed!
        self.assertEqual(updated, new_updated)

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

        # Got two broks
        # Simulate an host UP brok
        data = json.loads(open('cfg/brok_host_srv001_up.json').read())
        b = Brok({'data': data, 'type': 'host_check_result'}, False)
        # Simulate the main module function
        b.prepare()
        self.brokmodule.manage_brok(b)
        # Check the log check results prepared list
        assert len(self.brokmodule.logcheckresults) == 1

        # Simulate an host DOWN brok
        data = json.loads(open('cfg/brok_host_srv001_down.json').read())
        b = Brok({'data': data, 'type': 'host_check_result'}, False)
        # Simulate the main module function
        b.prepare()
        self.brokmodule.manage_brok(b)
        # Check the log check results prepared list
        assert len(self.brokmodule.logcheckresults) == 2
        # Send data to the backend
        self.brokmodule.send_to_backend('lcrs', '', '')

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
            new_updated = item['_updated']
            number += 1
        self.assertEqual(1, number)
        print(("Updated: %s" % new_updated))
        # The item do not have its _updated field changed!
        self.assertEqual(updated, new_updated)

    def test_03_2_manage_brok_host(self):
        """Test host livestate is updated with an alignak brok (from real broks)"""
        self.brokmodule.get_refs()
        self.assertEqual(len(self.brokmodule.ref_live['host']), 1)

        # Initial host state as left by the former test
        # ------
        params = {'where': '{"name": "srv001"}'}
        r = self.backend.get('host', params)
        self.assertEqual(len(r['_items']), 1)
        number = 0
        updated = 0
        for index, item in enumerate(r['_items']):
            self.assertEqual(item['ls_state'], 'DOWN')
            self.assertEqual(item['ls_state_type'], 'SOFT')
            self.assertEqual(item['ls_state_id'], 2)

            self.assertEqual(item['ls_acknowledged'], False)
            self.assertEqual(item['ls_acknowledgement_type'], 1)
            self.assertEqual(item['ls_downtimed'], False)

            self.assertEqual(item['ls_last_check'], 1444427104)
            self.assertEqual(item['ls_last_state'], 'UP')
            self.assertEqual(item['ls_last_state_type'], 'HARD')
            self.assertEqual(item['ls_last_state_changed'], 1444427108)
            self.assertEqual(item['ls_next_check'], 1444428104)

            self.assertEqual(item['ls_output'], 'CRITICAL - Plugin timed out after 10 seconds')
            self.assertEqual(item['ls_long_output'], '')
            self.assertEqual(item['ls_perf_data'], '')

            self.assertEqual(item['ls_current_attempt'], 0)
            # self.assertEqual(item['ls_max_attempts'], 0)
            self.assertEqual(item['ls_latency'], 0.2317881584)
            self.assertEqual(item['ls_execution_time'], 3.1496069431000002)

            self.assertEqual(item['ls_passive_check'], False)

            self.assertEqual(item['ls_last_hard_state_changed'], 1444427108)

            self.assertEqual(item['ls_last_time_up'], 0)
            self.assertEqual(item['ls_last_time_down'], 1444427108)
            self.assertEqual(item['ls_last_time_unknown'], 0)
            self.assertEqual(item['ls_last_time_unreachable'], 0)
            updated = item['_updated']
            number += 1
        self.assertEqual(1, number)

        # --- #1 - Post a real host UP brok
        data = {
            'last_time_unreachable': 0, 'last_problem_id': 0, 'retry_interval': 0,
            'last_event_id': 0, 'problem_has_been_acknowledged': False,
            'command_name': '_internal_host_up', 'last_state': 'UNREACHABLE',
            'latency': 0.9299669266, 'last_state_type': 'HARD',
            'last_hard_state_change': 1496234084, 'last_time_up': 1496234084,
            'percent_state_change': 0.0, 'state': 'UP', 'last_chk': 1496234083,
            'last_state_id': 0, 'end_time': 0, 'timeout': 0, 'current_event_id': 17,
            'execution_time': 0, 'start_time': 0, 'return_code': 0, 'state_type': 'HARD',
            'state_id': 0, 'in_checking': False, 'early_timeout': 0,
            'in_scheduled_downtime': False, 'attempt': 1, 'state_type_id': 1,
            'acknowledgement_type': 1, 'last_state_change': 1496234084.930904,
            'last_time_down': 0, 'instance_id': '7de9f30b2e9649dd98d5d5be8ebe6e3b',
            'long_output': 'Host assumed to be UP', 'current_problem_id': 0,
            'host_name': 'srv001', 'check_interval': 5, 'output': 'Host assumed to be UP',
            'has_been_checked': 1, 'perf_data': ''
        }
        b = Brok({'data': data, 'type': 'host_check_result'}, False)
        # Simulate the main module function
        b.prepare()
        self.brokmodule.manage_brok(b)
        # Check the log check results prepared list
        assert len(self.brokmodule.logcheckresults) == 1
        # Send data to the backend
        self.brokmodule.send_to_backend('lcrs', '', '')

        # Updated host state
        params = {'where': '{"name": "srv001"}'}
        r = self.backend.get('host', params)
        self.assertEqual(len(r['_items']), 1)
        number = 0
        new_updated = 0
        for index, item in enumerate(r['_items']):
            self.assertEqual(item['ls_state'], 'UP')                    # !
            self.assertEqual(item['ls_state_type'], 'HARD')
            self.assertEqual(item['ls_state_id'], 0)                    # !

            self.assertEqual(item['ls_acknowledged'], False)
            self.assertEqual(item['ls_acknowledgement_type'], 1)
            self.assertEqual(item['ls_downtimed'], False)

            self.assertEqual(item['ls_last_check'], 1496234083)         # !
            self.assertEqual(item['ls_last_state'], 'UNREACHABLE')      # !
            self.assertEqual(item['ls_last_state_type'], 'HARD')
            self.assertEqual(item['ls_last_state_changed'], 1496234084) # !
            self.assertEqual(item['ls_next_check'], 1444428104)

            self.assertEqual(item['ls_output'], 'Host assumed to be UP')
            self.assertEqual(item['ls_long_output'], 'Host assumed to be UP')
            self.assertEqual(item['ls_perf_data'], '')

            self.assertEqual(item['ls_current_attempt'], 1)
            # self.assertEqual(item['ls_max_attempts'], 0)
            self.assertEqual(item['ls_latency'], 0.9299669266)          # !
            self.assertEqual(item['ls_execution_time'], 0.0)

            self.assertEqual(item['ls_passive_check'], False)

            self.assertEqual(item['ls_last_hard_state_changed'], 1496234084)    # !

            self.assertEqual(item['ls_last_time_up'], 1496234084)               # !
            self.assertEqual(item['ls_last_time_down'], 0)
            self.assertEqual(item['ls_last_time_unknown'], 0)
            self.assertEqual(item['ls_last_time_unreachable'], 0)
            new_updated = item['_updated']
            number += 1
        self.assertEqual(1, number)
        print(("Updated: %s" % new_updated))
        # The item do not have its _updated field changed!
        self.assertEqual(updated, new_updated)

        # --- #2 - Post a real host UP brok
        data = {
            'last_time_unreachable': 0, 'last_problem_id': 0, 'retry_interval': 0,
            'last_event_id': 0, 'problem_has_been_acknowledged': False,
            'command_name': '_internal_host_up', 'last_state': 'UP', 'latency': 0.8838100433,
            'last_state_type': 'HARD', 'last_hard_state_change': 1496234084,
            'last_time_up': 1496237384, 'percent_state_change': 0.0, 'state': 'UP',
            'last_chk': 1496237383, 'last_state_id': 0, 'end_time': 0, 'timeout': 0,
            'current_event_id': 17, 'execution_time': 0, 'start_time': 0, 'return_code': 0,
            'state_type': 'HARD', 'state_id': 0, 'in_checking': False, 'early_timeout': 0,
            'in_scheduled_downtime': False, 'attempt': 1, 'state_type_id': 1,
            'acknowledgement_type': 1, 'last_state_change': 1496234084.930904,
            'last_time_down': 0, 'instance_id': '7de9f30b2e9649dd98d5d5be8ebe6e3b',
            'long_output': 'Host assumed to be UP', 'current_problem_id': 0,
            'host_name': 'srv001', 'check_interval': 5, 'output': 'Host assumed to be UP',
            'has_been_checked': 1, 'perf_data': ''
        }
        b = Brok({'data': data, 'type': 'host_check_result'}, False)
        # Simulate the main module function
        b.prepare()
        self.brokmodule.manage_brok(b)
        # Check the log check results prepared list
        assert len(self.brokmodule.logcheckresults) == 1
        # Send data to the backend
        self.brokmodule.send_to_backend('lcrs', '', '')

        # Updated host state
        params = {'where': '{"name": "srv001"}'}
        r = self.backend.get('host', params)
        self.assertEqual(len(r['_items']), 1)
        number = 0
        for index, item in enumerate(r['_items']):
            self.assertEqual(item['ls_state'], 'UP')
            self.assertEqual(item['ls_state_type'], 'HARD')
            self.assertEqual(item['ls_state_id'], 0)

            self.assertEqual(item['ls_acknowledged'], False)
            self.assertEqual(item['ls_acknowledgement_type'], 1)
            self.assertEqual(item['ls_downtimed'], False)

            self.assertEqual(item['ls_last_check'], 1496237383)         # !
            self.assertEqual(item['ls_last_state'], 'UP')               # !
            self.assertEqual(item['ls_last_state_type'], 'HARD')
            self.assertEqual(item['ls_last_state_changed'], 1496234084) # !
            self.assertEqual(item['ls_next_check'], 1444428104)

            self.assertEqual(item['ls_output'], 'Host assumed to be UP')
            self.assertEqual(item['ls_long_output'], 'Host assumed to be UP')
            self.assertEqual(item['ls_perf_data'], '')

            self.assertEqual(item['ls_current_attempt'], 1)
            # self.assertEqual(item['ls_max_attempts'], 0)
            self.assertEqual(item['ls_latency'], 0.8838100433)          # !
            self.assertEqual(item['ls_execution_time'], 0.0)

            self.assertEqual(item['ls_passive_check'], False)

            self.assertEqual(item['ls_last_hard_state_changed'], 1496234084)    # !

            self.assertEqual(item['ls_last_time_up'], 1496237384)               # !
            self.assertEqual(item['ls_last_time_down'], 0)
            self.assertEqual(item['ls_last_time_unknown'], 0)
            self.assertEqual(item['ls_last_time_unreachable'], 0)
            new_updated = item['_updated']
            number += 1
        self.assertEqual(1, number)
        print(("Updated: %s" % new_updated))
        # The item do not have its _updated field changed!
        self.assertEqual(updated, new_updated)

        # --- #3 - Post a real host UP brok
        data = {
            'last_time_unreachable': 0, 'last_problem_id': 0, 'retry_interval': 0,
            'last_event_id': 0, 'problem_has_been_acknowledged': False,
            'command_name': '_internal_host_up', 'last_state': 'UP', 'latency': 0.8838100433,
            'last_state_type': 'HARD', 'last_hard_state_change': 1496234084,
            'last_time_up': 1496237384, 'percent_state_change': 0.0, 'state': 'UP',
            'last_chk': 1496237383, 'last_state_id': 0, 'end_time': 0, 'timeout': 0,
            'current_event_id': 17, 'execution_time': 0, 'start_time': 0, 'return_code': 0,
            'state_type': 'HARD', 'state_id': 0, 'in_checking': False, 'early_timeout': 0,
            'in_scheduled_downtime': False, 'attempt': 1, 'state_type_id': 1,
            'acknowledgement_type': 1, 'last_state_change': 1496234084.930904,
            'last_time_down': 0, 'instance_id': '7de9f30b2e9649dd98d5d5be8ebe6e3b',
            'long_output': 'Host assumed to be UP', 'current_problem_id': 0,
            'host_name': 'srv001', 'check_interval': 5, 'output': 'Host assumed to be UP',
            'has_been_checked': 1, 'perf_data': ''
        }
        b = Brok({'data': data, 'type': 'host_check_result'}, False)
        # Simulate the main module function
        b.prepare()
        self.brokmodule.manage_brok(b)
        # Check the log check results prepared list
        assert len(self.brokmodule.logcheckresults) == 1
        # Send data to the backend
        self.brokmodule.send_to_backend('lcrs', '', '')

        # Updated host state
        params = {'where': '{"name": "srv001"}'}
        r = self.backend.get('host', params)
        self.assertEqual(len(r['_items']), 1)
        number = 0
        for index, item in enumerate(r['_items']):
            self.assertEqual(item['ls_state'], 'UP')
            self.assertEqual(item['ls_state_type'], 'HARD')
            self.assertEqual(item['ls_state_id'], 0)

            self.assertEqual(item['ls_acknowledged'], False)
            self.assertEqual(item['ls_acknowledgement_type'], 1)
            self.assertEqual(item['ls_downtimed'], False)

            self.assertEqual(item['ls_last_check'], 1496237383)         # !
            self.assertEqual(item['ls_last_state'], 'UP')               # !
            self.assertEqual(item['ls_last_state_type'], 'HARD')
            self.assertEqual(item['ls_last_state_changed'], 1496234084) # !
            self.assertEqual(item['ls_next_check'], 1444428104)

            self.assertEqual(item['ls_output'], 'Host assumed to be UP')
            self.assertEqual(item['ls_long_output'], 'Host assumed to be UP')
            self.assertEqual(item['ls_perf_data'], '')

            self.assertEqual(item['ls_current_attempt'], 1)
            # self.assertEqual(item['ls_max_attempts'], 0)
            self.assertEqual(item['ls_latency'], 0.8838100433)          # !
            self.assertEqual(item['ls_execution_time'], 0.0)

            self.assertEqual(item['ls_passive_check'], False)

            self.assertEqual(item['ls_last_hard_state_changed'], 1496234084)    # !

            self.assertEqual(item['ls_last_time_up'], 1496237384)               # !
            self.assertEqual(item['ls_last_time_down'], 0)
            self.assertEqual(item['ls_last_time_unknown'], 0)
            self.assertEqual(item['ls_last_time_unreachable'], 0)
            new_updated = item['_updated']
            number += 1
        self.assertEqual(1, number)
        print(("Updated: %s" % new_updated))
        # The item do not have its _updated field changed!
        self.assertEqual(updated, new_updated)

        # --- #4 - Post a real host DOWN brok
        data = {
            'last_time_unreachable': 0, 'last_problem_id': 0, 'retry_interval': 0,
            'last_event_id': 0, 'problem_has_been_acknowledged': False,
            'command_name': 'check_nrpe_alive', 'last_state': 'UP',
            'latency': 1.491920948, 'last_state_type': 'HARD',
            'last_hard_state_change': 1496240268, 'last_time_up': 0, 'percent_state_change': 4.1,
            'state': 'DOWN', 'last_chk': 1496240268, 'last_state_id': 0, 'end_time': 0,
            'timeout': 0, 'current_event_id': 31, 'execution_time': 0.1163659096,
            'start_time': 0, 'return_code': 3, 'state_type': 'HARD', 'state_id': 1,
            'in_checking': False, 'early_timeout': 0, 'in_scheduled_downtime': False,
            'attempt': 0, 'state_type_id': 1, 'acknowledgement_type': 1,
            'last_state_change': 1496234084.0, 'last_time_down': 1496240268,
            'instance_id': '16d0a854a3a5479fbfe0c9155392ca64',
            'long_output': 'Host is DOWN', 'current_problem_id': 0, 'host_name': 'srv001',
            'check_interval': 5, 'output': 'Host is DOWN', 'has_been_checked': 1,
            'perf_data': ''
        }
        b = Brok({'data': data, 'type': 'host_check_result'}, False)
        # Simulate the main module function
        b.prepare()
        self.brokmodule.manage_brok(b)
        # Check the log check results prepared list
        assert len(self.brokmodule.logcheckresults) == 1
        # Send data to the backend
        self.brokmodule.send_to_backend('lcrs', '', '')

        # Updated host state
        params = {'where': '{"name": "srv001"}'}
        r = self.backend.get('host', params)
        self.assertEqual(len(r['_items']), 1)
        number = 0
        for index, item in enumerate(r['_items']):
            self.assertEqual(item['ls_state'], 'DOWN')                  # !
            self.assertEqual(item['ls_state_type'], 'HARD')
            self.assertEqual(item['ls_state_id'], 1)

            self.assertEqual(item['ls_acknowledged'], False)
            self.assertEqual(item['ls_acknowledgement_type'], 1)
            self.assertEqual(item['ls_downtimed'], False)

            self.assertEqual(item['ls_last_check'], 1496240268)         # !
            self.assertEqual(item['ls_last_state'], 'UP')               # !
            self.assertEqual(item['ls_last_state_type'], 'HARD')
            self.assertEqual(item['ls_last_state_changed'], 1496234084) # !
            self.assertEqual(item['ls_next_check'], 1444428104)

            self.assertEqual(item['ls_output'], 'Host is DOWN')
            self.assertEqual(item['ls_long_output'], 'Host is DOWN')
            self.assertEqual(item['ls_perf_data'], '')

            self.assertEqual(item['ls_current_attempt'], 0)
            # self.assertEqual(item['ls_max_attempts'], 0)
            self.assertEqual(item['ls_latency'], 1.491920948)          # !
            self.assertEqual(item['ls_execution_time'], 0.1163659096)

            self.assertEqual(item['ls_passive_check'], False)

            self.assertEqual(item['ls_last_hard_state_changed'], 1496240268)    # !

            self.assertEqual(item['ls_last_time_up'], 0)               # !
            self.assertEqual(item['ls_last_time_down'], 1496240268)
            self.assertEqual(item['ls_last_time_unknown'], 0)
            self.assertEqual(item['ls_last_time_unreachable'], 0)
            new_updated = item['_updated']
            number += 1
        self.assertEqual(1, number)
        print(("Updated: %s" % new_updated))
        # The item do not have its _updated field changed!
        self.assertEqual(updated, new_updated)

    def test_03_3_manage_brok_host(self):
        """Test posting many broks"""
        self.brokmodule.get_refs()
        self.assertEqual(len(self.brokmodule.ref_live['host']), 1)

        r = self.backend.delete('logcheckresult', {})

        # Simulate many host UP brok
        # ----------------------------
        data = json.loads(open('cfg/brok_host_srv001_up.json').read())
        b = Brok({'data': data, 'type': 'host_check_result'}, False)
        b.prepare()
        for x in range(0, 200):
            # Simulate the main module function
            self.brokmodule.manage_brok(b)
        # Check the log check results prepared list
        assert len(self.brokmodule.logcheckresults) == 200
        # Send LCRs data to the backend
        self.brokmodule.send_to_backend('lcrs', '', '')

        time.sleep(3)
        r = self.backend.get_all('logcheckresult')
        self.assertEqual(len(r['_items']), 200)

    def test_04_manage_brok_service(self):
        """Test service livestate is updated with an alignak brok"""
        self.brokmodule.get_refs()
        self.assertEqual(len(self.brokmodule.ref_live['host']), 1)
        self.assertEqual(len(self.brokmodule.ref_live['service']), 2)

        # Simulate a service OK brok
        data = json.loads(open('cfg/brok_service_ping_ok.json').read())
        b = Brok({'data': data, 'type': 'service_check_result'}, False)
        # Simulate the main module function
        b.prepare()
        self.brokmodule.manage_brok(b)
        # Check the log check results prepared list
        assert len(self.brokmodule.logcheckresults) == 1
        # Send data to the backend
        self.brokmodule.send_to_backend('lcrs', '', '')

        params = {'where': '{"name": "ping"}'}
        r = self.backend.get('service', params)
        self.assertEqual(len(r['_items']), 1)
        number = 0
        updated = 0
        for index, item in enumerate(r['_items']):
            self.assertEqual(item['ls_state'], 'OK')
            self.assertEqual(item['ls_state_id'], 0)
            self.assertEqual(item['ls_state_type'], 'HARD')
            self.assertEqual(item['ls_last_check'], 1473597375)
            self.assertEqual(item['ls_last_state'], 'UNKNOWN')
            self.assertEqual(item['ls_last_state_type'], 'HARD')
            self.assertEqual(item['ls_last_state_changed'], 1444427108)
            self.assertEqual(item['ls_output'], 'PING OK - Packet loss = 0%, RTA = 0.05 ms')
            self.assertEqual(item['ls_long_output'], 'Long output ...')
            self.assertEqual(item['ls_perf_data'],
                             'rta=0.049000ms;2.000000;3.000000;0.000000 pl=0%;50;80;0')
            self.assertEqual(item['ls_acknowledged'], False)
            self.assertEqual(item['ls_downtimed'], False)
            self.assertEqual(item['ls_execution_time'], 3.1496069431000002)
            self.assertEqual(item['ls_latency'], 0.2317881584)
            updated = item['_updated']
            number += 1
        self.assertEqual(1, number)
        print(("Updated: %s" % updated))

        # Simulate a service next scheduler brok
        data = json.loads(open('cfg/brok_service_ping_next_check.json').read())
        b = Brok({'data': data, 'type': 'service_next_schedule'}, False)
        b.prepare()
        assert self.brokmodule.manage_brok(b) is True

        params = {'where': '{"name": "ping"}'}
        r = self.backend.get('service', params)
        self.assertEqual(len(r['_items']), 1)
        number = 0
        new_updated = 0
        for index, item in enumerate(r['_items']):
            self.assertEqual(item['ls_state'], 'OK')
            self.assertEqual(item['ls_state_id'], 0)
            self.assertEqual(item['ls_state_type'], 'HARD')
            self.assertEqual(item['ls_last_check'], 1473597375)
            self.assertEqual(item['ls_last_state'], 'UNKNOWN')
            self.assertEqual(item['ls_last_state_type'], 'HARD')
            self.assertEqual(item['ls_last_state_changed'], 1444427108)
            self.assertEqual(item['ls_output'], 'PING OK - Packet loss = 0%, RTA = 0.05 ms')
            self.assertEqual(item['ls_long_output'], 'Long output ...')
            self.assertEqual(item['ls_perf_data'],
                             'rta=0.049000ms;2.000000;3.000000;0.000000 pl=0%;50;80;0')
            self.assertEqual(item['ls_acknowledged'], False)
            self.assertEqual(item['ls_downtimed'], False)
            self.assertEqual(item['ls_execution_time'], 3.1496069431000002)
            self.assertEqual(item['ls_latency'], 0.2317881584)
            # Next check !
            self.assertEqual(item['ls_next_check'], 1473598375)
            new_updated = item['_updated']
            number += 1
        self.assertEqual(1, number)
        print(("Updated: %s" % new_updated))
        # The item do not have its _updated field changed!
        self.assertEqual(updated, new_updated)

        r = self.backend.get('service')
        self.assertEqual(len(r['_items']), 2)

        r = self.backend.get('livesynthesis')
        self.assertEqual(len(r['_items']), 1)
        self.assertEqual(r['_items'][0]['services_total'], 2)
        self.assertEqual(r['_items'][0]['services_ok_hard'], 1)
        self.assertEqual(r['_items'][0]['services_ok_soft'], 0)
        self.assertEqual(r['_items'][0]['services_warning_hard'], 0)
        self.assertEqual(r['_items'][0]['services_warning_soft'], 0)
        self.assertEqual(r['_items'][0]['services_critical_hard'], 0)
        self.assertEqual(r['_items'][0]['services_critical_soft'], 0)
        self.assertEqual(r['_items'][0]['services_unknown_hard'], 1)
        self.assertEqual(r['_items'][0]['services_unknown_soft'], 0)
        self.assertEqual(r['_items'][0]['services_acknowledged'], 0)
        self.assertEqual(r['_items'][0]['services_in_downtime'], 0)

        # --- Post a real service check result brok
        for i in range(0,9):
            data = {            'last_time_unreachable': 1498188961, 'last_problem_id': 2, 'retry_interval': 0,
                'last_event_id': 2, 'problem_has_been_acknowledged': False, 'last_time_critical': 0,
                'last_time_warning': 1498132868, 'command_name': '_echo', 'last_state': 'OK',
                'latency': 0, 'current_event_id': 11, 'last_state_type': 'HARD',
                'last_hard_state_change': 1498190476, 'percent_state_change': 34.3, 'state': 'OK',
                'last_chk': 1498191517, 'last_state_id': 0, 'host_name': 'srv001',
                'timeout': 0, 'last_time_unknown': 0, 'execution_time': 0.0, 'start_time': 0,
                'return_code': 0, 'state_type': 'HARD', 'state_id': 0,
                'service_description': 'ping', 'in_checking': False, 'early_timeout': 0,
                'in_scheduled_downtime': False, 'attempt': 1, 'state_type_id': 1,
                'acknowledgement_type': 1, 'last_state_change': 1498190476.866557,
                'instance_id': '936d0f5e6c10471f8d23fbe62a384f24', 'long_output': '',
                'current_problem_id': 0, 'last_time_ok': 1498191518, 'check_interval': 5,
                'output': 'OK: uptime: 16:42h, boot: 2017-06-22 11:35:44 (UTC)',
                'has_been_checked': 1, 'perf_data': "'uptime'=60173s;2100;90000", 'end_time': 0
            }
            b = Brok({'data': data, 'type': 'service_check_result'}, False)
            # Simulate the main module function
            b.prepare()
            self.brokmodule.manage_brok(b)
            # Check the log check results prepared list
            assert len(self.brokmodule.logcheckresults) == 1
            # Send data to the backend
            self.brokmodule.send_to_backend('lcrs', '', '')

            params = {'where': '{"name": "ping"}'}
            r = self.backend.get('service', params)
            self.assertEqual(len(r['_items']), 1)
            number = 0
            new_updated = 0
            for index, item in enumerate(r['_items']):
                self.assertEqual(item['ls_state'], 'OK')
                self.assertEqual(item['ls_state_id'], 0)
                self.assertEqual(item['ls_state_type'], 'HARD')
                self.assertEqual(item['ls_last_check'], 1498191517)
                self.assertEqual(item['ls_last_state'], 'OK')
                self.assertEqual(item['ls_last_state_type'], 'HARD')
                self.assertEqual(item['ls_last_state_changed'], 1498190476)
                self.assertEqual(item['ls_output'], 'OK: uptime: 16:42h, boot: 2017-06-22 11:35:44 (UTC)')
                self.assertEqual(item['ls_long_output'], '')
                self.assertEqual(item['ls_perf_data'], "'uptime'=60173s;2100;90000")
                self.assertEqual(item['ls_acknowledged'], False)
                self.assertEqual(item['ls_downtimed'], False)
                self.assertEqual(item['ls_execution_time'], 0.0)
                self.assertEqual(item['ls_latency'], 0.0)
                # Next check !
                self.assertEqual(item['ls_next_check'], 1473598375)
                new_updated = item['_updated']
                number += 1
            self.assertEqual(1, number)
            print(("Updated: %s" % new_updated))
            # The item do not have its _updated field changed!
            self.assertEqual(updated, new_updated)

        # --- Post a real service next check brok
        for i in range(0,9):
            data = {
                'instance_id': 'c54d19e52f5d46fb976d373ee4bae3c9',
                'service_description': 'ping', 'next_chk': 1498197600,
                'in_checking': True, 'host_name': 'srv001'
            }
            b = Brok({'data': data, 'type': 'service_next_schedule'}, False)
            b.prepare()
            assert self.brokmodule.manage_brok(b) is True

            params = {'where': '{"name": "ping"}'}
            r = self.backend.get('service', params)
            self.assertEqual(len(r['_items']), 1)
            number = 0
            new_updated = 0
            for index, item in enumerate(r['_items']):
                self.assertEqual(item['ls_state'], 'OK')
                self.assertEqual(item['ls_state_id'], 0)
                self.assertEqual(item['ls_state_type'], 'HARD')
                self.assertEqual(item['ls_last_check'], 1498191517)
                self.assertEqual(item['ls_last_state'], 'OK')
                self.assertEqual(item['ls_last_state_type'], 'HARD')
                self.assertEqual(item['ls_last_state_changed'], 1498190476)
                self.assertEqual(item['ls_output'], 'OK: uptime: 16:42h, boot: 2017-06-22 11:35:44 (UTC)')
                self.assertEqual(item['ls_long_output'], '')
                self.assertEqual(item['ls_perf_data'], "'uptime'=60173s;2100;90000")
                self.assertEqual(item['ls_acknowledged'], False)
                self.assertEqual(item['ls_downtimed'], False)
                self.assertEqual(item['ls_execution_time'], 0.0)
                self.assertEqual(item['ls_latency'], 0.0)
                # Next check !
                self.assertEqual(item['ls_next_check'], 1498197600)
                new_updated = item['_updated']
                number += 1
            self.assertEqual(1, number)
            print(("Updated: %s" % new_updated))
            # The item do not have its _updated field changed!
            self.assertEqual(updated, new_updated)


class TestBrokerToken(unittest2.TestCase):
    """
    Same test class as the TestBrokerCommon, but the module is connecting
    with a user token rather than a user login.

    Only keep one test to confirm connection is really valid!
    """

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
        # admin user
        users = cls.backend.get_all('user')
        cls.user_admin = users['_items'][0]

        realms = cls.backend.get_all('realm')
        for realm in realms['_items']:
            cls.realm_all = realm['_id']

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
        # modconf.username = "admin"
        # modconf.password = "admin"
        modconf.token = cls.user_admin["token"]
        modconf.api_url = 'http://127.0.0.1:5000'
        cls.brokmodule = AlignakBackendBroker(modconf)

    @classmethod
    def tearDownClass(cls):
        cls.p.kill()

    def test_01_get_refs_host(self):
        """Get hosts references"""
        self.brokmodule.get_refs()

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
