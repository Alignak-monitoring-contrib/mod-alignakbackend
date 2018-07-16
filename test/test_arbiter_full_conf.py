#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import shlex
import subprocess
import json
import unittest2
from alignak_module_backend.arbiter.module import AlignakBackendArbiter
from alignak_module_backend.broker.module import AlignakBackendBroker

from alignak.objects.module import Module
from alignak.objects.realm import Realm
from alignak.objects.command import Command
from alignak.objects.timeperiod import Timeperiod
from alignak.objects.contact import Contact
from alignak.objects.contactgroup import Contactgroup
from alignak.objects.host import Host
from alignak.objects.hostgroup import Hostgroup
from alignak.objects.hostdependency import Hostdependency
from alignak.objects.hostescalation import Hostescalation
from alignak.objects.service import Service
from alignak.objects.servicegroup import Servicegroup
from alignak.objects.servicedependency import Servicedependency
from alignak.objects.serviceescalation import Serviceescalation
from alignak_backend_client.client import Backend

from alignak.brok import Brok

class Arbiter():
    """Fake Arbiter class, only for tests..."""
    def __init__(self, verify_only=False, arbiter_name=None):
        self.verify_only = verify_only
        self.arbiter_name = arbiter_name


class TestArbiterFullConfiguration(unittest2.TestCase):

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

        test_dir = os.path.dirname(os.path.realpath(__file__))
        print(("Current test directory: %s" % test_dir))

        print(("Feeding Alignak backend... %s" % test_dir))
        exit_code = subprocess.call(
            shlex.split(
                'alignak-backend-import --delete %s/cfg/default/_main.cfg' % test_dir)
        )
        assert exit_code == 0

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
        """
        Kill uwsgi

        :return: None
        """
        subprocess.call(['uwsgi', '--stop', '/tmp/uwsgi.pid'])
        time.sleep(2)

    def test_alignak_configuration(self):
        """Test alignak configuration reading

        :return:
        """
        # Start broker module
        modconf = Module()
        modconf.module_alias = "backend_broker"
        modconf.username = "admin"
        modconf.password = "admin"
        modconf.api_url = 'http://127.0.0.1:5000'
        self.brokmodule = AlignakBackendBroker(modconf)

        # Get a program status brok
        brok_data = {
            # Some general information
            'alignak_name': 'my_alignak',
            'instance_id': '176064a1b30741d39452415097807ab0',
            'instance_name': 'scheduler-master',

            # Some running information
            'program_start': 1493969754,
            'daemon_mode': 1,
            'pid': 68989,
            'last_alive': 1493970641,
            'last_command_check': 1493970641,
            'last_log_rotation': 1493970641,
            'is_running': 1,

            # Some configuration parameters
            'process_performance_data': True,
            'passive_service_checks_enabled': True,
            'event_handlers_enabled': True,
            'command_file': '',
            'global_host_event_handler': None,
            'interval_length': 60,
            'modified_host_attributes': 0,
            'check_external_commands': True,
            'modified_service_attributes': 0,
            'passive_host_checks_enabled': True,
            'global_service_event_handler': None,
            'notifications_enabled': True,
            'check_service_freshness': True,
            'check_host_freshness': True,
            'flap_detection_enabled': True,
            'active_service_checks_enabled': True,
            'active_host_checks_enabled': True
        }
        brok = Brok({'type': 'update_program_status', 'data': brok_data})
        brok.prepare()

        # -------
        # Configure to manage this brok (default is to ignore...) !
        self.brokmodule.manage_update_program_status = True

        # Send program status brok
        self.brokmodule.manage_brok(brok)
        # This has created an `alignak` resource...

        # Now we call the Arbiter hook function to get this created configuration
        # Will get all the `alignak` resources because no arbiter name is defined ...
        fake_arb = Arbiter()
        self.arbmodule.hook_read_configuration(fake_arb)
        configuration = self.arbmodule.get_alignak_configuration()
        print(("Configuration: %s" % configuration))
        expected = brok_data.copy()
        print(("Expected: %s" % expected))
        expected['name'] = expected.pop('alignak_name')
        # Some fields are valued as default by the backend
        configuration.pop('_created')
        configuration.pop('_updated')
        configuration.pop('_id')
        configuration.pop('_etag')
        configuration.pop('_realm')
        configuration.pop('_sub_realm')
        configuration.pop('_links')
        configuration.pop('schema_version')
        # TODO need add this new fields in alignak brok creation
        for field_name in ['use_timezone',
                           'illegal_macro_output_chars', 'illegal_object_name_chars',
                           'cleaning_queues_interval', 'max_plugins_output_length',
                           'enable_environment_macros', 'log_initial_states', 'log_active_checks',
                           'log_host_retries', 'log_service_retries', 'log_passive_checks',
                           'log_notifications', 'log_event_handlers', 'log_external_commands',
                           'log_flappings', 'log_snapshots', 'enable_notifications',
                           'notification_timeout', 'timeout_exit_status', 'execute_host_checks',
                           'max_host_check_spread', 'host_check_timeout',
                           'check_for_orphaned_hosts', 'execute_service_checks',
                           'max_service_check_spread', 'service_check_timeout',
                           'check_for_orphaned_services', 'flap_history', 'low_host_flap_threshold',
                           'high_host_flap_threshold', 'low_service_flap_threshold',
                           'high_service_flap_threshold', 'event_handler_timeout',
                           'no_event_handlers_during_downtimes', 'host_perfdata_command',
                           'service_perfdata_command', 'accept_passive_host_checks',
                           'host_freshness_check_interval', 'accept_passive_service_checks',
                           'service_freshness_check_interval', 'additional_freshness_latency']:
            configuration.pop(field_name)
        expected['alias'] = expected['name']
        expected['notes'] = ''
        expected['notes_url'] = ''
        expected['global_host_event_handler'] = str(expected['global_host_event_handler'])
        expected['global_service_event_handler'] = 'None'
        self.assertEqual(configuration, expected)

        # Get another program status brok
        brok_data = {
            # Some general information
            'alignak_name': 'my_alignak_2',
            'instance_id': '176064a1b30741d39452415097807ab0',
            'instance_name': 'scheduler-master',

            # Some running information
            'program_start': 1493969754,
            'daemon_mode': 1,
            'pid': 68989,
            'last_alive': 1493970641,
            'last_command_check': 1493970641,
            'last_log_rotation': 1493970641,
            'is_running': 1,

            # Some configuration parameters
            'process_performance_data': True,
            'passive_service_checks_enabled': True,
            'event_handlers_enabled': True,
            'command_file': '',
            'global_host_event_handler': 'None',
            'interval_length': 60,
            'modified_host_attributes': 0,
            'check_external_commands': True,
            'modified_service_attributes': 0,
            'passive_host_checks_enabled': True,
            'global_service_event_handler': 'None',
            'notifications_enabled': True,
            'check_service_freshness': True,
            'check_host_freshness': True,
            'flap_detection_enabled': True,
            'active_service_checks_enabled': True,
            'active_host_checks_enabled': True
        }
        brok = Brok({'type': 'update_program_status', 'data': brok_data})
        brok.prepare()

        # Send program status brok
        self.brokmodule.manage_brok(brok)
        # This has created an `alignak` resource...

        # Now we call the Arbiter hook function to get this created configuration
        # Get the configuration for a specific arbiter / alignak
        # It will be the first one created
        fake_arb = Arbiter(arbiter_name='my_alignak')
        self.arbmodule.hook_read_configuration(fake_arb)
        configuration = self.arbmodule.get_alignak_configuration()
        # Some fields are valued as default by the backend
        configuration.pop('_created')
        configuration.pop('_updated')
        configuration.pop('_id')
        configuration.pop('_etag')
        configuration.pop('_realm')
        configuration.pop('_sub_realm')
        configuration.pop('_links')
        configuration.pop('schema_version')
        # TODO need add this new fields in alignak brok creation
        for field_name in ['use_timezone',
                           'illegal_macro_output_chars', 'illegal_object_name_chars',
                           'cleaning_queues_interval', 'max_plugins_output_length',
                           'enable_environment_macros', 'log_initial_states', 'log_active_checks',
                           'log_host_retries', 'log_service_retries', 'log_passive_checks',
                           'log_notifications', 'log_event_handlers', 'log_external_commands',
                           'log_flappings', 'log_snapshots', 'enable_notifications',
                           'notification_timeout', 'timeout_exit_status', 'execute_host_checks',
                           'max_host_check_spread', 'host_check_timeout',
                           'check_for_orphaned_hosts', 'execute_service_checks',
                           'max_service_check_spread', 'service_check_timeout',
                           'check_for_orphaned_services', 'flap_history', 'low_host_flap_threshold',
                           'high_host_flap_threshold', 'low_service_flap_threshold',
                           'high_service_flap_threshold', 'event_handler_timeout',
                           'no_event_handlers_during_downtimes', 'host_perfdata_command',
                           'service_perfdata_command', 'accept_passive_host_checks',
                           'host_freshness_check_interval', 'accept_passive_service_checks',
                           'service_freshness_check_interval', 'additional_freshness_latency']:
            configuration.pop(field_name)
        self.assertEqual(configuration, expected)

    def test_commands(self):
        self.assertEqual(len(self.objects['commands']), 107)
        for comm in self.objects['commands']:
            for key, value in comm.items():
                self.assertTrue(Command.properties[key])

    def test_hostescalations(self):
        self.assertEqual(len(self.objects['hostescalations']), 2)
        for item in self.objects['hostescalations']:
            for key, value in item.items():
                self.assertTrue(Hostescalation.properties[key])

    def test_contacts(self):
        self.assertEqual(len(self.objects['contacts']), 8)
        for cont in self.objects['contacts']:
            for key, value in cont.items():
                # problem in alignak because not defined
                if key not in ['can_update_livestate', 'skill_level', 'webui_visible'] \
                        and not key.startswith('_'):
                    self.assertTrue(Contact.properties[key])

    def test_timeperiods(self):
        self.assertEqual(len(self.objects['timeperiods']), 4)
        # for item in self.objects['timeperiods']:
        #     for key, value in item.iteritems():
        #         self.assertTrue(Timeperiod.properties[key])

    def test_serviceescalations(self):
        self.assertEqual(len(self.objects['serviceescalations']), 3)
        for item in self.objects['serviceescalations']:
            for key, value in item.items():
                self.assertTrue(Serviceescalation.properties[key])

    def test_hostgroups(self):
        self.assertEqual(len(self.objects['hostgroups']), 9)
        for hostgrp in self.objects['hostgroups']:
            for key, value in hostgrp.items():
                # problem in alignak because not defined
                if key not in ['hostgroup_members']:
                    self.assertTrue(Hostgroup.properties[key])

    def test_contactgroups(self):
        self.assertEqual(len(self.objects['contactgroups']), 4)
        for contact in self.objects['contactgroups']:
            for key, value in contact.items():
                # problem in alignak because not defined
                if key not in ['contactgroup_members', 'notes']:
                    self.assertTrue(Contactgroup.properties[key])

    def test_hosts(self):
        self.assertEqual(len(self.objects['hosts']), 13)
        for host in self.objects['hosts']:
            print(("Got host: %s" % host))
            for key, value in host.items():
                if not key.startswith('ls_') and \
                        not key.startswith('_') and \
                        not key.startswith('trigger'):
                    self.assertTrue(Host.properties[key])

    def test_realms(self):
        self.assertEqual(len(self.objects['realms']), 5)
        for realm in self.objects['realms']:
            print(("Got realm: %s" % realm))
            for key, value in realm.items():
                self.assertTrue(Realm.properties[key])
            if realm['realm_name'] == 'All':
                members = realm['realm_members'].split(',')
                print(("Realm All members: %s", members))
                self.assertEqual(len(members), 2)
                for member in members:
                    self.assertIn(member, ['Europe', 'US'])
            if realm['realm_name'] == 'Europe':
                members = realm['realm_members'].split(',')
                print(("Realm Europe members: %s", members))
                self.assertEqual(len(members), 2)
                for member in members:
                    self.assertIn(member, ['Italy', 'France'])

    def test_services(self):
        # As of #80, ... 94
        self.assertEqual(len(self.objects['services']), 94)
        for serv in self.objects['services']:
            print(("Got service: %s" % serv))
            for key, value in serv.items():
                if not key.startswith('ls_') and \
                        not key.startswith('_') and \
                        not key in ['alias'] and \
                        not key.startswith('trigger'):
                    self.assertTrue(Service.properties[key])

    def test_servicegroups(self):
        self.assertEqual(len(self.objects['servicegroups']), 6)
        for grp in self.objects['servicegroups']:
            for key, value in grp.items():
                # problem in alignak because not defined
                if key not in ['servicegroup_members']:
                    self.assertTrue(Servicegroup.properties[key])

    def test_hostdependencies(self):
        self.assertEqual(len(self.objects['hostdependencies']), 3)
        for grp in self.objects['hostdependencies']:
            for key, value in grp.items():
                # Do not exist in Alignak, but do not disturb...
                if key not in ['notes', 'alias']:
                    self.assertTrue(Hostdependency.properties[key])

    def test_servicedependencies(self):
        self.assertEqual(len(self.objects['servicedependencies']), 1)
        for grp in self.objects['servicedependencies']:
            for key, value in grp.items():
                # Do not exist in Alignak, but do not disturb...
                if key not in ['notes', 'alias']:
                    self.assertTrue(Servicedependency.properties[key])
