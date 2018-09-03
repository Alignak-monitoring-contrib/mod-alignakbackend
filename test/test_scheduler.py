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
This file test the retention of scheduler in the backend
"""

import os
import shlex
import time
import subprocess
import json
import unittest2
from alignak_module_backend.scheduler.module import AlignakBackendScheduler
from alignak.objects.module import Module
from alignak_backend_client.client import Backend


class TestScheduler(unittest2.TestCase):
    """
    This class test the retention (load / save) of host and services in the scheduler
    """

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        """This method:
          * deletes mongodb database
          * starts the backend with uwsgi
          * logs in the backend and gets the token

        :return: None
        """
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
        data['name'] = 'other-ping'
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

        # Get admin user
        users = cls.backend.get_all('user')
        cls.user_id = users['_items'][0]['_id']

        # Start scheduler module
        modconf = Module()
        modconf.module_alias = "backend_scheduler"
        modconf.username = "admin"
        modconf.password = "admin"
        modconf.api_url = 'http://127.0.0.1:5000'
        cls.schedmodule = AlignakBackendScheduler(modconf)

        class scheduler(object):
            """
            Fake scheduler class used to save and load retention
            """

            def __init__(self):
                self.data = None

            def get_retention_data(self):
                """
                Get host and service data for save in backend

                :return: properties of host and services
                :rtype: dict
                """
                all_data = {'hosts': {}, 'services': {}}
                all_data['hosts']['srv001'] = {
                    'latency': 0,
                    'last_state_type': 'HARD',
                    'state': 'UP',
                    'last_chk': 0,
                }
                all_data['hosts']['srv002'] = {
                    'latency': 0,
                    'last_state_type': 'HARD',
                    'state': 'UP',
                    'last_chk': 0,
                }

                all_data['services'][('srv001', 'check_http')] = {
                    'latency': 0,
                    'last_state_type': 'HARD',
                    'state': 'OK',
                    'last_chk': 0,
                }
                all_data['services'][('srv002', 'check_https')] = {
                    'latency': 0,
                    'last_state_type': 'HARD',
                    'state': 'WARNING',
                    'last_chk': 0,
                }
                return all_data

            def restore_retention_data(self, data):
                """
                Load hoas and servcie from backend retention

                :param data: dict of hosts and service from retention backend
                :type data: dict
                """
                self.data = data

        cls.sched = scheduler()

    @classmethod
    def tearDownClass(cls):
        """
        Kill uwsgi

        :return: None
        """
        subprocess.call(['uwsgi', '--stop', '/tmp/uwsgi.pid'])
        time.sleep(2)

    @classmethod
    def tearDown(cls):
        """
        Delete resources in backend

        :return: None
        """
        headers = {'Content-Type': 'application/json'}
        for resource in ['alignakretention']:
            cls.backend.delete(resource, headers)

    def test_retention_host_save(self):
        """
        Test save in retention backend the host information

        :return: None
        """
        self.schedmodule.hook_save_retention(self.sched)
        hosts = self.backend.get_all('alignakretention', params={'sort': 'host'})
        reference = [
            {
                'latency': 0,
                'last_state_type': 'HARD',
                'state': 'UP',
                'last_chk': 0,
                'host': 'srv001',
                'retention_services': {
                    'check_http': {
                        'latency': 0,
                        'last_state_type': 'HARD',
                        'state': 'OK',
                        'last_chk': 0,
                    }
                }
            },
            {
                'latency': 0,
                'last_state_type': 'HARD',
                'state': 'UP',
                'last_chk': 0,
                'host': 'srv002',
                'retention_services': {
                    'check_https': {
                        'latency': 0,
                        'last_state_type': 'HARD',
                        'state': 'WARNING',
                        'last_chk': 0,
                    }
                }
            }
        ]

        for host in hosts['_items']:
            for key in ['_created', '_etag', '_id', '_links', '_updated', '_user',
                        'schema_version']:
                del host[key]

        self.assertEqual(2, len(hosts['_items']))
        self.assertDictEqual(hosts['_items'][0], reference[0])
        self.assertDictEqual(hosts['_items'][1], reference[1])

    def test_retention_host_service_save_previous_saved(self):
        """
        Test save in retention backend the host information but with previous data in the backend

        :return: None
        """

        # Add an host
        data = {
            'latency': 0,
            'last_state_type': 'SOFT',
            'state': 'UP',
            'last_chk': 1010101010101,
            'host': 'srv001',
            'retention_services': {
                'check_ssh': {
                    'latency': 0,
                    'last_state_type': 'HARD',
                    'state': 'OK',
                    'last_chk': 0,
                }
            }
        }
        self.backend.post('alignakretention', data)
        data['host'] = 'srv009'
        data['retention_services'] = {}
        self.backend.post('alignakretention', data)

        hosts = self.backend.get_all('alignakretention', params={'sort': 'host'})
        self.assertEqual(2, len(hosts['_items']))

        self.schedmodule.hook_save_retention(self.sched)

        hosts = self.backend.get_all('alignakretention', params={'sort': 'host'})
        reference = [
            {
                'latency': 0,
                'last_state_type': 'HARD',
                'state': 'UP',
                'last_chk': 0,
                'host': 'srv001',
                'retention_services': {
                    'check_http': {
                        'latency': 0,
                        'last_state_type': 'HARD',
                        'state': 'OK',
                        'last_chk': 0,
                    }
                }
            },
            {
                'latency': 0,
                'last_state_type': 'HARD',
                'state': 'UP',
                'last_chk': 0,
                'host': 'srv002',
                'retention_services': {
                    'check_https': {
                        'latency': 0,
                        'last_state_type': 'HARD',
                        'state': 'WARNING',
                        'last_chk': 0,
                    }
                }
            },
            {
                'latency': 0,
                'last_state_type': 'SOFT',
                'state': 'UP',
                'last_chk': 1010101010101,
                'host': 'srv009',
                'retention_services': {}
            }
        ]

        for host in hosts['_items']:
            for key in ['_created', '_etag', '_id', '_links', '_updated', '_user',
                        'schema_version']:
                del host[key]

        self.assertEqual(3, len(hosts['_items']))
        self.assertDictEqual(hosts['_items'][0], reference[0])
        self.assertDictEqual(hosts['_items'][1], reference[1])
        self.assertDictEqual(hosts['_items'][2], reference[2])

    def test_retention_load(self):
        """
        Test for load retention host and service from backend

        :return:
        """
        self.schedmodule.hook_save_retention(self.sched)
        self.schedmodule.hook_load_retention(self.sched)

        reference = {
            'srv001': {
                'latency': 0,
                'last_state_type': 'HARD',
                'state': 'UP',
                'last_chk': 0,
            },
            'srv002': {
                'latency': 0,
                'last_state_type': 'HARD',
                'state': 'UP',
                'last_chk': 0,
            }
        }
        self.assertDictEqual(self.sched.data['hosts'], reference)

        reference = {
            ('srv001', 'check_http'): {
                'latency': 0,
                'last_state_type': 'HARD',
                'state': 'OK',
                'last_chk': 0,
            },
            ('srv002', 'check_https'): {
                'latency': 0,
                'last_state_type': 'HARD',
                'state': 'WARNING',
                'last_chk': 0,
            }
        }
        self.assertDictEqual(self.sched.data['services'], reference)
