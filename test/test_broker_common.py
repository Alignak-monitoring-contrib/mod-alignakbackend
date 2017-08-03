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

    def test_02_connection_accepted(self):
        # Start broker module with admin user token
        modconf = Module()
        modconf.module_alias = "backend_broker"
        # modconf.username = "admin"
        # modconf.password = "admin"
        modconf.token = self.user_admin["token"]
        modconf.api_url = 'http://127.0.0.1:5000'
        broker_module = AlignakBackendBroker(modconf)

        self.assertTrue(broker_module.backendConnection())
        self.assertTrue(broker_module.logged_in)


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
        modconf.module_alias = "backend_broker"
        modconf.username = "admin"
        modconf.password = "admin"
        modconf.api_url = 'http://127.0.0.1:5000'
        cls.brokmodule = AlignakBackendBroker(modconf)

    @classmethod
    def tearDownClass(cls):
        cls.p.kill()

    def test_01_get_refs_host(self):
        """Get hosts references"""
        # Default reload protection delay
        self.assertEqual(self.brokmodule.load_protect_delay, 300)

        now = int(time.time())
        # First call loads the corresponding objects
        self.brokmodule.get_refs('livestate_host')
        # Stored loaded hosts timestamp
        self.assertEqual(self.brokmodule.loaded_hosts, now)

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

        # A call some seconds later the first one do not reload the objects
        time.sleep(3)
        self.brokmodule.get_refs('livestate_host')
        # Stored loaded host timestamp did not changed
        self.assertEqual(self.brokmodule.loaded_hosts, now)

    def test_02_get_refs_service(self):
        """Get services references"""
        # Default reload protection delay
        self.assertEqual(self.brokmodule.load_protect_delay, 300)

        now = int(time.time())
        # First call loads the corresponding objects
        self.brokmodule.get_refs('livestate_service')
        # Stored loaded services timestamp
        self.assertEqual(self.brokmodule.loaded_services, now)

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

        # A call some seconds later the first one do not reload the objects
        time.sleep(3)
        self.brokmodule.get_refs('livestate_service')
        # Stored loaded host timestamp did not changed
        self.assertEqual(self.brokmodule.loaded_services, now)

    def test_03_get_refs_users(self):
        """Get users references"""
        # Default reload protection delay
        self.assertEqual(self.brokmodule.load_protect_delay, 300)

        now = int(time.time())
        # First call loads the corresponding objects
        self.brokmodule.get_refs('livestate_user')
        # Stored loaded users timestamp
        self.assertEqual(self.brokmodule.loaded_users, now)

        self.assertEqual(len(self.brokmodule.ref_live['user']), 1)
        self.assertEqual(
            self.brokmodule.ref_live['user'][self.admin_user['_id']]['_realm'],
            self.admin_user['_realm']
        )

        ref = {'admin': self.admin_user['_id']}
        self.assertEqual(self.brokmodule.mapping['user'], ref)

        # A call some seconds later the first one do not reload the objects
        time.sleep(3)
        self.brokmodule.get_refs('livestate_user')
        # Stored loaded host timestamp did not changed
        self.assertEqual(self.brokmodule.loaded_users, now)

    def test_03_1_manage_brok_host(self):
        """Test host livestate is updated with an alignak brok"""
        self.brokmodule.get_refs('livestate_host')
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

            self.assertEqual(item['ls_impact'], 0)

            self.assertEqual(item['ls_last_check'], 0)
            self.assertEqual(item['ls_last_state'], 'UNREACHABLE')
            self.assertEqual(item['ls_last_state_type'], 'HARD')
            self.assertEqual(item['ls_last_state_changed'], 0)
            self.assertEqual(item['ls_next_check'], 0)

            self.assertEqual(item['ls_output'], '')
            self.assertEqual(item['ls_long_output'], '')
            self.assertEqual(item['ls_perf_data'], '')

            self.assertEqual(item['ls_current_attempt'], 0)
            self.assertEqual(item['ls_attempt'], 0)
            self.assertEqual(item['ls_max_attempts'], 0)
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
        b.prepare()
        assert self.brokmodule.manage_brok(b) is True

        params = {'where': '{"name": "srv001"}'}
        r = self.backend.get('host', params)
        self.assertEqual(len(r['_items']), 1)
        number = 0
        updated = 0
        for index, item in enumerate(r['_items']):
            self.assertEqual(item['ls_state'], 'UP')
            self.assertEqual(item['ls_state_id'], 1)
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
        print("Updated: %s" % updated)

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
            self.assertEqual(item['ls_state_id'], 1)
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
        print("Updated: %s" % new_updated)
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
        b.prepare()
        assert self.brokmodule.manage_brok(b) is True

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
        print("Updated: %s" % new_updated)
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

    def test_03_2_manage_brok_host(self):
        """Test host livestate is updated with an alignak brok (from real broks)"""
        self.brokmodule.get_refs('livestate_host')
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

            self.assertEqual(item['ls_impact'], 0)

            self.assertEqual(item['ls_last_check'], 1444427104)
            self.assertEqual(item['ls_last_state'], 'UP')
            self.assertEqual(item['ls_last_state_type'], 'HARD')
            self.assertEqual(item['ls_last_state_changed'], 1444427108)
            self.assertEqual(item['ls_next_check'], 1444428104)

            self.assertEqual(item['ls_output'], 'CRITICAL - Plugin timed out after 10 seconds')
            self.assertEqual(item['ls_long_output'], '')
            self.assertEqual(item['ls_perf_data'], '')

            self.assertEqual(item['ls_current_attempt'], 0)
            self.assertEqual(item['ls_attempt'], 0)
            self.assertEqual(item['ls_max_attempts'], 0)
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
            u'last_time_unreachable': 0, u'last_problem_id': 0, u'retry_interval': 0,
            u'last_event_id': 0, u'problem_has_been_acknowledged': False,
            u'command_name': u'_internal_host_up', u'last_state': u'UNREACHABLE',
            u'latency': 0.9299669266, u'last_state_type': u'HARD',
            u'last_hard_state_change': 1496234084, u'last_time_up': 1496234084,
            u'percent_state_change': 0.0, u'state': u'UP', u'last_chk': 1496234083,
            u'last_state_id': 0, u'end_time': 0, u'timeout': 0, u'current_event_id': 17,
            u'execution_time': 0, u'start_time': 0, u'return_code': 0, u'state_type': u'HARD',
            u'state_id': 0, u'in_checking': False, u'early_timeout': 0,
            u'in_scheduled_downtime': False, u'attempt': 1, u'state_type_id': 1,
            u'acknowledgement_type': 1, u'last_state_change': 1496234084.930904,
            u'last_time_down': 0, 'instance_id': u'7de9f30b2e9649dd98d5d5be8ebe6e3b',
            u'long_output': u'Host assumed to be UP', u'current_problem_id': 0,
            u'host_name': u'srv001', u'check_interval': 5, u'output': u'Host assumed to be UP',
            u'has_been_checked': 1, u'perf_data': u''
        }
        b = Brok({'data': data, 'type': 'host_check_result'}, False)
        b.prepare()
        assert self.brokmodule.manage_brok(b) is True

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

            self.assertEqual(item['ls_impact'], 0)

            self.assertEqual(item['ls_last_check'], 1496234083)         # !
            self.assertEqual(item['ls_last_state'], 'UNREACHABLE')      # !
            self.assertEqual(item['ls_last_state_type'], 'HARD')
            self.assertEqual(item['ls_last_state_changed'], 1496234084) # !
            self.assertEqual(item['ls_next_check'], 1444428104)

            self.assertEqual(item['ls_output'], 'Host assumed to be UP')
            self.assertEqual(item['ls_long_output'], 'Host assumed to be UP')
            self.assertEqual(item['ls_perf_data'], '')

            self.assertEqual(item['ls_current_attempt'], 0)
            self.assertEqual(item['ls_attempt'], 1)                     # !
            self.assertEqual(item['ls_max_attempts'], 0)
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
        print("Updated: %s" % new_updated)
        # The item do not have its _updated field changed!
        self.assertEqual(updated, new_updated)

        # --- #2 - Post a real host UP brok
        data = {
            u'last_time_unreachable': 0, u'last_problem_id': 0, u'retry_interval': 0,
            u'last_event_id': 0, u'problem_has_been_acknowledged': False,
            u'command_name': u'_internal_host_up', u'last_state': u'UP', u'latency': 0.8838100433,
            u'last_state_type': u'HARD', u'last_hard_state_change': 1496234084,
            u'last_time_up': 1496237384, u'percent_state_change': 0.0, u'state': u'UP',
            u'last_chk': 1496237383, u'last_state_id': 0, u'end_time': 0, u'timeout': 0,
            u'current_event_id': 17, u'execution_time': 0, u'start_time': 0, u'return_code': 0,
            u'state_type': u'HARD', u'state_id': 0, u'in_checking': False, u'early_timeout': 0,
            u'in_scheduled_downtime': False, u'attempt': 1, u'state_type_id': 1,
            u'acknowledgement_type': 1, u'last_state_change': 1496234084.930904,
            u'last_time_down': 0, 'instance_id': u'7de9f30b2e9649dd98d5d5be8ebe6e3b',
            u'long_output': u'Host assumed to be UP', u'current_problem_id': 0,
            u'host_name': u'srv001', u'check_interval': 5, u'output': u'Host assumed to be UP',
            u'has_been_checked': 1, u'perf_data': u''
        }
        b = Brok({'data': data, 'type': 'host_check_result'}, False)
        b.prepare()
        assert self.brokmodule.manage_brok(b) is True

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

            self.assertEqual(item['ls_impact'], 0)

            self.assertEqual(item['ls_last_check'], 1496237383)         # !
            self.assertEqual(item['ls_last_state'], 'UP')               # !
            self.assertEqual(item['ls_last_state_type'], 'HARD')
            self.assertEqual(item['ls_last_state_changed'], 1496234084) # !
            self.assertEqual(item['ls_next_check'], 1444428104)

            self.assertEqual(item['ls_output'], 'Host assumed to be UP')
            self.assertEqual(item['ls_long_output'], 'Host assumed to be UP')
            self.assertEqual(item['ls_perf_data'], '')

            self.assertEqual(item['ls_current_attempt'], 0)
            self.assertEqual(item['ls_attempt'], 1)                     # !
            self.assertEqual(item['ls_max_attempts'], 0)
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
        print("Updated: %s" % new_updated)
        # The item do not have its _updated field changed!
        self.assertEqual(updated, new_updated)

        # --- #3 - Post a real host UP brok
        data = {
            u'last_time_unreachable': 0, u'last_problem_id': 0, u'retry_interval': 0,
            u'last_event_id': 0, u'problem_has_been_acknowledged': False,
            u'command_name': u'_internal_host_up', u'last_state': u'UP', u'latency': 0.8838100433,
            u'last_state_type': u'HARD', u'last_hard_state_change': 1496234084,
            u'last_time_up': 1496237384, u'percent_state_change': 0.0, u'state': u'UP',
            u'last_chk': 1496237383, u'last_state_id': 0, u'end_time': 0, u'timeout': 0,
            u'current_event_id': 17, u'execution_time': 0, u'start_time': 0, u'return_code': 0,
            u'state_type': u'HARD', u'state_id': 0, u'in_checking': False, u'early_timeout': 0,
            u'in_scheduled_downtime': False, u'attempt': 1, u'state_type_id': 1,
            u'acknowledgement_type': 1, u'last_state_change': 1496234084.930904,
            u'last_time_down': 0, 'instance_id': u'7de9f30b2e9649dd98d5d5be8ebe6e3b',
            u'long_output': u'Host assumed to be UP', u'current_problem_id': 0,
            u'host_name': u'srv001', u'check_interval': 5, u'output': u'Host assumed to be UP',
            u'has_been_checked': 1, u'perf_data': u''
        }
        b = Brok({'data': data, 'type': 'host_check_result'}, False)
        b.prepare()
        assert self.brokmodule.manage_brok(b) is True

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

            self.assertEqual(item['ls_impact'], 0)

            self.assertEqual(item['ls_last_check'], 1496237383)         # !
            self.assertEqual(item['ls_last_state'], 'UP')               # !
            self.assertEqual(item['ls_last_state_type'], 'HARD')
            self.assertEqual(item['ls_last_state_changed'], 1496234084) # !
            self.assertEqual(item['ls_next_check'], 1444428104)

            self.assertEqual(item['ls_output'], 'Host assumed to be UP')
            self.assertEqual(item['ls_long_output'], 'Host assumed to be UP')
            self.assertEqual(item['ls_perf_data'], '')

            self.assertEqual(item['ls_current_attempt'], 0)
            self.assertEqual(item['ls_attempt'], 1)                     # !
            self.assertEqual(item['ls_max_attempts'], 0)
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
        print("Updated: %s" % new_updated)
        # The item do not have its _updated field changed!
        self.assertEqual(updated, new_updated)

        # --- #4 - Post a real host DOWN brok
        data = {
            u'last_time_unreachable': 0, u'last_problem_id': 0, u'retry_interval': 0,
            u'last_event_id': 0, u'problem_has_been_acknowledged': False,
            u'command_name': u'check_nrpe_alive', u'last_state': u'UP',
            u'latency': 1.491920948, u'last_state_type': u'HARD',
            u'last_hard_state_change': 1496240268, u'last_time_up': 0, u'percent_state_change': 4.1,
            u'state': u'DOWN', u'last_chk': 1496240268, u'last_state_id': 0, u'end_time': 0,
            u'timeout': 0, u'current_event_id': 31, u'execution_time': 0.1163659096,
            u'start_time': 0, u'return_code': 3, u'state_type': u'HARD', u'state_id': 1,
            u'in_checking': False, u'early_timeout': 0, u'in_scheduled_downtime': False,
            u'attempt': 0, u'state_type_id': 1, u'acknowledgement_type': 1,
            u'last_state_change': 1496234084.0, u'last_time_down': 1496240268,
            'instance_id': u'16d0a854a3a5479fbfe0c9155392ca64',
            u'long_output': u'Host is DOWN', u'current_problem_id': 0, u'host_name': u'srv001',
            u'check_interval': 5, u'output': u'Host is DOWN', u'has_been_checked': 1,
            u'perf_data': u''
        }
        b = Brok({'data': data, 'type': 'host_check_result'}, False)
        b.prepare()
        assert self.brokmodule.manage_brok(b) is True

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

            self.assertEqual(item['ls_impact'], 0)

            self.assertEqual(item['ls_last_check'], 1496240268)         # !
            self.assertEqual(item['ls_last_state'], 'UP')               # !
            self.assertEqual(item['ls_last_state_type'], 'HARD')
            self.assertEqual(item['ls_last_state_changed'], 1496234084) # !
            self.assertEqual(item['ls_next_check'], 1444428104)

            self.assertEqual(item['ls_output'], 'Host is DOWN')
            self.assertEqual(item['ls_long_output'], 'Host is DOWN')
            self.assertEqual(item['ls_perf_data'], '')

            self.assertEqual(item['ls_current_attempt'], 0)
            self.assertEqual(item['ls_attempt'], 0)                     # !
            self.assertEqual(item['ls_max_attempts'], 0)
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
        print("Updated: %s" % new_updated)
        # The item do not have its _updated field changed!
        self.assertEqual(updated, new_updated)

    def test_04_manage_brok_service(self):
        """Test service livestate is updated with an alignak brok"""
        self.brokmodule.get_refs('livestate_host')
        self.assertEqual(len(self.brokmodule.ref_live['host']), 1)
        self.brokmodule.get_refs('livestate_service')
        self.assertEqual(len(self.brokmodule.ref_live['service']), 2)

        # Simulate a service OK brok
        data = json.loads(open('cfg/brok_service_ping_ok.json').read())
        b = Brok({'data': data, 'type': 'service_check_result'}, False)
        b.prepare()
        assert self.brokmodule.manage_brok(b) is True

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
        print("Updated: %s" % updated)

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
        print("Updated: %s" % new_updated)
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
            data = {            u'last_time_unreachable': 1498188961, u'last_problem_id': 2, u'retry_interval': 0,
                u'last_event_id': 2, u'problem_has_been_acknowledged': False, u'last_time_critical': 0,
                u'last_time_warning': 1498132868, u'command_name': u'_echo', u'last_state': u'OK',
                u'latency': 0, u'current_event_id': 11, u'last_state_type': u'HARD',
                u'last_hard_state_change': 1498190476, u'percent_state_change': 34.3, u'state': u'OK',
                u'last_chk': 1498191517, u'last_state_id': 0, u'host_name': u'srv001',
                u'timeout': 0, u'last_time_unknown': 0, u'execution_time': 0.0, u'start_time': 0,
                u'return_code': 0, u'state_type': u'HARD', u'state_id': 0,
                u'service_description': u'ping', u'in_checking': False, u'early_timeout': 0,
                u'in_scheduled_downtime': False, u'attempt': 1, u'state_type_id': 1,
                u'acknowledgement_type': 1, u'last_state_change': 1498190476.866557,
                'instance_id': u'936d0f5e6c10471f8d23fbe62a384f24', u'long_output': u'',
                u'current_problem_id': 0, u'last_time_ok': 1498191518, u'check_interval': 5,
                u'output': u'OK: uptime: 16:42h, boot: 2017-06-22 11:35:44 (UTC)',
                u'has_been_checked': 1, u'perf_data': u"'uptime'=60173s;2100;90000", u'end_time': 0
            }
            b = Brok({'data': data, 'type': 'service_check_result'}, False)
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
                self.assertEqual(item['ls_next_check'], 1473598375)
                new_updated = item['_updated']
                number += 1
            self.assertEqual(1, number)
            print("Updated: %s" % new_updated)
            # The item do not have its _updated field changed!
            self.assertEqual(updated, new_updated)

        # --- Post a real service next check brok
        for i in range(0,9):
            data = {
                'instance_id': u'c54d19e52f5d46fb976d373ee4bae3c9',
                u'service_description': u'ping', u'next_chk': 1498197600,
                u'in_checking': True, u'host_name': u'srv001'
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
            print("Updated: %s" % new_updated)
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
