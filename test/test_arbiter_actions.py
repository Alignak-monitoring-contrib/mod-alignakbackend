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
This file is used to test the arbiter module actions
"""
import os
import shlex
import time
import subprocess
import json
import unittest2
from calendar import timegm
from datetime import datetime, timedelta

from alignak_module_backend.arbiter.module import AlignakBackendArbiter
from alignak.objects.module import Module
from alignak_backend_client.client import Backend


class TestArbiterActions(unittest2.TestCase):

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

        # Get admin user
        users = cls.backend.get_all('user')
        for user in users['_items']:
            if user['name'] == 'admin':
                cls.user_admin = user

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

        # Start arbiter module
        modconf = Module()
        modconf.module_alias = "backend_arbiter"
        modconf.username = "admin"
        modconf.password = "admin"
        modconf.api_url = 'http://127.0.0.1:5000'
        cls.arbmodule = AlignakBackendArbiter(modconf)
        cls.objects = cls.arbmodule.get_objects()

    @classmethod
    def tearDownClass(cls):
        cls.p.kill()

    def test_acknowledges(self):
        """Test acknowledge management"""

        # ---
        # Add acknowledges into the backend
        # acknowledge an host
        data = {
            "action": "add",
            "user": self.user_admin['_id'],
            "host": self.data_host['_id'],
            "service": None,
            "sticky": True,
            "persistent": True,
            "notify": True,
            "comment": "User comment host",
        }
        self.backend.post("actionacknowledge", data)
        # acknowledge a service
        data = {
            "action": "add",
            "user": self.user_admin['_id'],
            "host": self.data_host['_id'],
            "service": self.data_srv_ping['_id'],
            "sticky": False,
            "persistent": False,
            "notify": False,
            "comment": "User comment service",
        }
        self.backend.post("actionacknowledge", data)
        # delete an host acknowledge
        data = {
            "action": "delete",
            "user": self.user_admin['_id'],
            "host": self.data_host['_id'],
            "service": None,
        }
        self.backend.post("actionacknowledge", data)
        # delete a service acknowledge
        data = {
            "action": "delete",
            "user": self.user_admin['_id'],
            "host": self.data_host['_id'],
            "service": self.data_srv_ping['_id'],
        }
        self.backend.post("actionacknowledge", data)

        # Get acknowledges (all are to be processed)
        acks = self.backend.get_all('actionacknowledge')
        self.assertEqual(len(acks['_items']), 4)
        for ack in acks['_items']:
            self.assertIs(ack['processed'], False)

        # Fake arbiter
        class Arbiter(object):
            external_commands = []
        arbiter = Arbiter()

        self.arbmodule.get_acknowledge(arbiter)

        # Got external commands
        self.assertEqual(len(arbiter.external_commands), 4)
        ext_cmd = arbiter.external_commands[0]
        self.assertIn('ACKNOWLEDGE_HOST_PROBLEM;srv001;'
                      '2;1;1;admin;User comment host', ext_cmd.cmd_line)
        ext_cmd = arbiter.external_commands[1]
        self.assertIn('ACKNOWLEDGE_SVC_PROBLEM;srv001;ping;'
                      '1;0;1;admin;User comment service', ext_cmd.cmd_line)
        ext_cmd = arbiter.external_commands[2]
        self.assertIn('REMOVE_HOST_ACKNOWLEDGEMENT;srv001', ext_cmd.cmd_line)
        ext_cmd = arbiter.external_commands[3]
        self.assertIn('REMOVE_SVC_ACKNOWLEDGEMENT;srv001;ping', ext_cmd.cmd_line)

        # Get acknowledges (all are processed now!)
        acks = self.backend.get_all('actionacknowledge')
        self.assertEqual(len(acks['_items']), 4)
        for ack in acks['_items']:
            self.assertIs(ack['processed'], True)

    def test_downtimes(self):
        """Test downtime management"""

        now = datetime.utcnow()
        later = now + timedelta(days=2, hours=4, minutes=3, seconds=12)
        now = timegm(now.timetuple())
        later = timegm(later.timetuple())

        # ---
        # Add downtimes into the backend
        # downtime an host
        data = {
            "action": "add",
            "user": self.user_admin['_id'],
            "host": self.data_host['_id'],
            "service": None,
            "start_time": now,
            "end_time": later,
            "fixed": False,
            'duration': 86400,
            "comment": "User comment host",
        }
        self.backend.post("actiondowntime", data)
        # downtime a service
        data = {
            "action": "add",
            "user": self.user_admin['_id'],
            "host": self.data_host['_id'],
            "service": self.data_srv_ping['_id'],
            "start_time": now,
            "end_time": later,
            "fixed": False,
            'duration': 86400,
            "comment": "User comment service",
        }
        self.backend.post("actiondowntime", data)
        # delete an host downtime
        data = {
            "action": "delete",
            "user": self.user_admin['_id'],
            "host": self.data_host['_id'],
            "service": None,
        }
        self.backend.post("actiondowntime", data)
        # delete a service downtime
        data = {
            "action": "delete",
            "user": self.user_admin['_id'],
            "host": self.data_host['_id'],
            "service": self.data_srv_ping['_id'],
        }
        self.backend.post("actiondowntime", data)

        # Get downtimes (all are to be processed)
        acks = self.backend.get_all('actiondowntime')
        self.assertEqual(len(acks['_items']), 4)
        for ack in acks['_items']:
            self.assertIs(ack['processed'], False)

        # Fake arbiter
        class Arbiter(object):
            external_commands = []
        arbiter = Arbiter()

        self.arbmodule.get_downtime(arbiter)

        # Got external commands
        self.assertEqual(len(arbiter.external_commands), 4)
        ext_cmd = arbiter.external_commands[0]
        self.assertIn('SCHEDULE_HOST_DOWNTIME;srv001;'
                      '%s;%s;0;0;86400;admin;User comment host' % (now, later),
                      ext_cmd.cmd_line)
        ext_cmd = arbiter.external_commands[1]
        self.assertIn('SCHEDULE_SVC_DOWNTIME;srv001;ping;'
                      '%s;%s;0;0;86400;admin;User comment service' % (now, later),
                      ext_cmd.cmd_line)
        ext_cmd = arbiter.external_commands[2]
        self.assertIn('DEL_ALL_HOST_DOWNTIMES;srv001', ext_cmd.cmd_line)
        ext_cmd = arbiter.external_commands[3]
        self.assertIn('DEL_ALL_SVC_DOWNTIMES;srv001;ping', ext_cmd.cmd_line)

        # Get downtimes (all are processed now!)
        acks = self.backend.get_all('actiondowntime')
        self.assertEqual(len(acks['_items']), 4)
        for ack in acks['_items']:
            self.assertIs(ack['processed'], True)

    def test_force_checks(self):
        """Test foced checks management"""

        # ---
        # Add recheck into the backend
        # recheck an host
        data = {
            "user": self.user_admin['_id'],
            "host": self.data_host['_id'],
            "service": None,
            "comment": "User comment host",
        }
        self.backend.post("actionforcecheck", data)
        # recheck a service
        data = {
            "user": self.user_admin['_id'],
            "host": self.data_host['_id'],
            "service": self.data_srv_ping['_id'],
            "comment": "User comment service",
        }
        self.backend.post("actionforcecheck", data)

        # Get recheck (all are to be processed)
        acks = self.backend.get_all('actionforcecheck')
        self.assertEqual(len(acks['_items']), 2)
        for ack in acks['_items']:
            self.assertIs(ack['processed'], False)

        # Fake arbiter
        class Arbiter(object):
            external_commands = []
        arbiter = Arbiter()

        self.arbmodule.get_forcecheck(arbiter)

        # Got external commands
        self.assertEqual(len(arbiter.external_commands), 2)
        ext_cmd = arbiter.external_commands[0]
        self.assertIn('SCHEDULE_FORCED_HOST_CHECK;srv001', ext_cmd.cmd_line)
        ext_cmd = arbiter.external_commands[1]
        self.assertIn('SCHEDULE_FORCED_SVC_CHECK;srv001;ping;', ext_cmd.cmd_line)

        # Get recheck (all are processed now!)
        acks = self.backend.get_all('actionforcecheck')
        self.assertEqual(len(acks['_items']), 2)
        for ack in acks['_items']:
            self.assertIs(ack['processed'], True)

