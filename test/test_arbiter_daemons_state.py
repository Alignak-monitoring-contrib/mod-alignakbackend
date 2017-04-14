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
"""
This file tests the configuration loading from the backend
"""

import os
import time
import shlex
import subprocess
import json
import copy
import unittest2
from alignak_module_backend.arbiter.module import AlignakBackendArbiter
from alignak.objects.config import Config
from alignak.objects.module import Module
from alignak.objects.command import Command
from alignak.objects.contact import Contact
from alignak.objects.host import Host
from alignak.objects.hostgroup import Hostgroup
from alignak.objects.realm import Realm
from alignak.objects.service import Service
from alignak_backend_client.client import Backend


class TestArbiterDaemonsState(unittest2.TestCase):

    maxDiff = None

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
        cls.backend = Backend('http://127.0.0.1:5000')
        cls.backend.login("admin", "admin", "force")
        realms = cls.backend.get_all('realm')
        for cont in realms['_items']:
            cls.realm_all = cont['_id']

        timeperiods = cls.backend.get_all('timeperiod')
        for tp in timeperiods['_items']:
            if tp['name'] == '24x7':
                timeperiods_id = tp['_id']

        # add commands
        data = json.loads(open('cfg/command_ping.json').read())
        data['_realm'] = cls.realm_all
        data_cmd_ping = cls.backend.post("command", data)
        data = json.loads(open('cfg/command_http.json').read())
        data['_realm'] = cls.realm_all
        data_cmd_http = cls.backend.post("command", data)

        # Add some realms
        data = {
            'name': 'All-A',
            '_parent': cls.realm_all
        }
        realm_a = cls.backend.post("realm", data)
        cls.realm_all_a = realm_a['_id']
        data = {
            'name': 'All-B',
            '_parent': cls.realm_all
        }
        cls.backend.post("realm", data)
        data = {
            'name': 'All-A-1',
            '_parent': realm_a['_id']
        }
        cls.backend.post("realm", data)

        # Get admin user
        resp = cls.backend.get_all('user')
        cls.user_admin = resp['_items'][0]

        # Add user
        # User 1
        data = {'name': 'user1', 'password': 'test', 'back_role_super_admin': False,
                'host_notification_period': cls.user_admin['host_notification_period'],
                'service_notification_period': cls.user_admin['service_notification_period'],
                '_realm': realm_a['_id'], '_sub_realm': False}
        user1 = cls.backend.post('user', data)

        data = {'user': user1['_id'], 'realm': realm_a['_id'], 'resource': '*',
                'crud': ['create', 'read', 'update', 'delete']}
        cls.backend.post('userrestrictrole', data)

        # Start arbiter backend module
        modconf = Module()
        modconf.module_alias = "backend_arbiter"
        modconf.username = "admin"
        modconf.password = "admin"
        modconf.api_url = 'http://127.0.0.1:5000'
        cls.arbmodule = AlignakBackendArbiter(modconf)

        modconf2 = Module()
        modconf2.module_alias = "backend_arbiter"
        modconf2.username = "user1"
        modconf2.password = "test"
        modconf2.api_url = 'http://127.0.0.1:5000'
        cls.arbmodule2 = AlignakBackendArbiter(modconf2)

    @classmethod
    def tearDownClass(cls):
        """Kill uwsgi

        :return: None
        """
        subprocess.call(['uwsgi', '--stop', '/tmp/uwsgi.pid'])
        time.sleep(2)

    @classmethod
    def tearDown(cls):
        """
        Delete resources after each test

        :return: None
        """
        cls.backend.delete('alignakdaemon', {})

    def test_daemons_state_all_realms(self):
        """Test when add/update daemons state in the backend

        :return: None
        """
        class Arbiter(object):
            conf = Config()

        arb = Arbiter()
        arb.conf.arbiters = []
        arb.conf.schedulers = []
        arb.conf.pollers = []
        arb.conf.brokers = []
        arb.conf.receivers = []
        arb.conf.reactionners = []

        now = int(time.time())

        a = lambda: None
        setattr(a, 'arbiter_name', 'arbiter-master')
        setattr(a, 'last_check', 0)
        setattr(a, 'address', '127.0.0.1')
        setattr(a, 'port', 7770)
        setattr(a, 'alive', True)
        setattr(a, 'reachable', True)
        setattr(a, 'passive', False)
        setattr(a, 'spare', False)
        setattr(a, 'realm_name', '')
        setattr(a, 'manage_sub_realms', False)
        arb.conf.arbiters.append(copy.copy(a))

        a = lambda: None
        setattr(a, 'arbiter_name', 'arbiter-spare')
        setattr(a, 'last_check', 1485286855.808687)
        setattr(a, 'address', '127.0.0.1')
        setattr(a, 'port', 17770)
        setattr(a, 'alive', True)
        setattr(a, 'reachable', True)
        setattr(a, 'passive', False)
        setattr(a, 'spare', False)
        setattr(a, 'realm_name', '')
        setattr(a, 'manage_sub_realms', False)
        arb.conf.arbiters.append(copy.copy(a))

        a = lambda: None
        setattr(a, 'reactionner_name', 'reactionner-master')
        setattr(a, 'last_check', 1485286855.808687)
        setattr(a, 'address', '127.0.0.1')
        setattr(a, 'port', 7769)
        setattr(a, 'alive', True)
        setattr(a, 'reachable', True)
        setattr(a, 'passive', False)
        setattr(a, 'spare', False)
        setattr(a, 'realm_name', 'All')
        setattr(a, 'manage_sub_realms', False)
        arb.conf.reactionners.append(copy.copy(a))

        a = lambda: None
        setattr(a, 'broker_name', 'broker-master')
        setattr(a, 'last_check', 1485286855.808687)
        setattr(a, 'address', '127.0.0.1')
        setattr(a, 'port', 7772)
        setattr(a, 'alive', True)
        setattr(a, 'reachable', True)
        setattr(a, 'passive', False)
        setattr(a, 'spare', False)
        setattr(a, 'realm_name', 'All')
        setattr(a, 'manage_sub_realms', False)
        arb.conf.brokers.append(copy.copy(a))

        a = lambda: None
        setattr(a, 'scheduler_name', 'scheduler-master')
        setattr(a, 'last_check', 1485286855.808687)
        setattr(a, 'address', '127.0.0.1')
        setattr(a, 'port', 7768)
        setattr(a, 'alive', True)
        setattr(a, 'reachable', True)
        setattr(a, 'passive', False)
        setattr(a, 'spare', False)
        setattr(a, 'realm_name', 'All')
        setattr(a, 'manage_sub_realms', False)
        arb.conf.schedulers.append(copy.copy(a))

        a = lambda: None
        setattr(a, 'receiver_name', 'receiver-master')
        setattr(a, 'last_check', 1485286855.808687)
        setattr(a, 'address', '127.0.0.1')
        setattr(a, 'port', 7773)
        setattr(a, 'alive', True)
        setattr(a, 'reachable', True)
        setattr(a, 'passive', False)
        setattr(a, 'spare', False)
        setattr(a, 'realm_name', 'All')
        setattr(a, 'manage_sub_realms', True)
        arb.conf.receivers.append(copy.copy(a))

        a = lambda: None
        setattr(a, 'poller_name', 'poller-master')
        setattr(a, 'last_check', 1485286855.808687)
        setattr(a, 'address', '127.0.0.1')
        setattr(a, 'port', 7771)
        setattr(a, 'alive', True)
        setattr(a, 'reachable', True)
        setattr(a, 'passive', False)
        setattr(a, 'spare', False)
        setattr(a, 'realm_name', 'All')
        setattr(a, 'manage_sub_realms', False)
        arb.conf.pollers.append(copy.copy(a))

        self.arbmodule.get_objects()
        self.arbmodule.update_daemons_state(arb)

        aldae = self.backend.get_all('alignakdaemon')
        self.assertEqual(len(aldae['_items']), 7)

        self.assertEqual(aldae['_items'][0]['type'], 'arbiter')
        self.assertEqual(aldae['_items'][0]['name'], 'arbiter-master')
        self.assertGreaterEqual(aldae['_items'][0]['last_check'], now)

        self.assertEqual(aldae['_items'][1]['type'], 'arbiter')
        self.assertEqual(aldae['_items'][1]['name'], 'arbiter-spare')
        self.assertEqual(aldae['_items'][1]['last_check'], 1485286855)


    def test_daemons_state_sub_realms(self):
        """Test when add/update daemons state in the backend

        :return: None
        """
        class Arbiter(object):
            conf = Config()

        arb = Arbiter()
        arb.conf.arbiters = []
        arb.conf.schedulers = []
        arb.conf.pollers = []
        arb.conf.brokers = []
        arb.conf.receivers = []
        arb.conf.reactionners = []

        now = int(time.time())

        a = lambda: None
        setattr(a, 'arbiter_name', 'arbiter-master')
        setattr(a, 'last_check', 0)
        setattr(a, 'address', '127.0.0.1')
        setattr(a, 'port', 7770)
        setattr(a, 'alive', True)
        setattr(a, 'reachable', True)
        setattr(a, 'passive', False)
        setattr(a, 'spare', False)
        setattr(a, 'realm_name', '')
        setattr(a, 'manage_sub_realms', False)
        arb.conf.arbiters.append(copy.copy(a))

        a = lambda: None
        setattr(a, 'reactionner_name', 'reactionner-master')
        setattr(a, 'last_check', 1485286855.808687)
        setattr(a, 'address', '127.0.0.1')
        setattr(a, 'port', 7769)
        setattr(a, 'alive', True)
        setattr(a, 'reachable', True)
        setattr(a, 'passive', False)
        setattr(a, 'spare', False)
        setattr(a, 'realm_name', 'All-A')
        setattr(a, 'manage_sub_realms', False)
        arb.conf.reactionners.append(copy.copy(a))

        a = lambda: None
        setattr(a, 'broker_name', 'broker-master')
        setattr(a, 'last_check', 1485286855.808687)
        setattr(a, 'address', '127.0.0.1')
        setattr(a, 'port', 7772)
        setattr(a, 'alive', True)
        setattr(a, 'reachable', True)
        setattr(a, 'passive', False)
        setattr(a, 'spare', False)
        setattr(a, 'realm_name', 'All-A')
        setattr(a, 'manage_sub_realms', False)
        arb.conf.brokers.append(copy.copy(a))

        a = lambda: None
        setattr(a, 'scheduler_name', 'scheduler-master')
        setattr(a, 'last_check', 1485286855.808687)
        setattr(a, 'address', '127.0.0.1')
        setattr(a, 'port', 7768)
        setattr(a, 'alive', True)
        setattr(a, 'reachable', True)
        setattr(a, 'passive', False)
        setattr(a, 'spare', False)
        setattr(a, 'realm_name', 'All-A')
        setattr(a, 'manage_sub_realms', False)
        arb.conf.schedulers.append(copy.copy(a))

        a = lambda: None
        setattr(a, 'receiver_name', 'receiver-master')
        setattr(a, 'last_check', 1485286855.808687)
        setattr(a, 'address', '127.0.0.1')
        setattr(a, 'port', 7773)
        setattr(a, 'alive', True)
        setattr(a, 'reachable', True)
        setattr(a, 'passive', False)
        setattr(a, 'spare', False)
        setattr(a, 'realm_name', 'All-A')
        setattr(a, 'manage_sub_realms', True)
        arb.conf.receivers.append(copy.copy(a))

        a = lambda: None
        setattr(a, 'poller_name', 'poller-master')
        setattr(a, 'last_check', 1485286855.808687)
        setattr(a, 'address', '127.0.0.1')
        setattr(a, 'port', 7771)
        setattr(a, 'alive', True)
        setattr(a, 'reachable', True)
        setattr(a, 'passive', False)
        setattr(a, 'spare', False)
        setattr(a, 'realm_name', 'All-A')
        setattr(a, 'manage_sub_realms', False)
        arb.conf.pollers.append(copy.copy(a))


        self.arbmodule2.get_objects()
        self.arbmodule2.update_daemons_state(arb)

        aldae = self.backend.get_all('alignakdaemon')
        self.assertEqual(len(aldae['_items']), 6)

        self.assertEqual(aldae['_items'][0]['type'], 'arbiter')
        self.assertEqual(aldae['_items'][0]['name'], 'arbiter-master')
        self.assertEqual(aldae['_items'][0]['_realm'], self.realm_all_a)
        self.assertGreaterEqual(aldae['_items'][0]['last_check'], now)

        self.assertEqual(aldae['_items'][1]['type'], 'scheduler')
        self.assertEqual(aldae['_items'][1]['name'], 'scheduler-master')
        self.assertEqual(aldae['_items'][1]['last_check'], 1485286855)
        self.assertEqual(aldae['_items'][1]['_realm'], self.realm_all_a)
