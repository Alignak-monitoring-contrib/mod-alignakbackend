#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import shlex
import subprocess
import json
import unittest2
from alignak_module_backend.arbiter.module import AlignakBackendArbiter
from alignak.objects.module import Module
from alignak.objects.command import Command
from alignak.objects.contact import Contact
from alignak.objects.host import Host
from alignak.objects.hostgroup import Hostgroup
from alignak.objects.realm import Realm
from alignak.objects.service import Service
from alignak_backend_client.client import Backend


class TestArbiterLoadconf(unittest2.TestCase):

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

        # add user
        data = {'name': 'jeronimo', 'host_notification_period': timeperiods_id,
                'service_notification_period': timeperiods_id, '_realm': cls.realm_all}
        data_user_jeronimo = cls.backend.post("user", data)

        # add usergroup
        data = {'name': 'admins', '_realm': cls.realm_all, 'users': [data_user_jeronimo['_id']]}
        data_usergroup = cls.backend.post("usergroup", data)

        # add host template
        data = json.loads(open('cfg/host_srvtemplate.json').read())
        data['check_command'] = data_cmd_ping['_id']
        del data['realm']
        data['_realm'] = cls.realm_all
        cls.data_host = cls.backend.post("host", data)

        # add host
        data = json.loads(open('cfg/host_srv001.json').read())
        data['check_command'] = data_cmd_ping['_id']
        del data['realm']
        data['_realm'] = cls.realm_all
        data['users'] = [data_user_jeronimo['_id']]
        data['usergroups'] = [data_usergroup['_id']]
        cls.data_host = cls.backend.post("host", data)

        # add service ping
        data = json.loads(open('cfg/service_srv001_ping.json').read())
        data['host'] = cls.data_host['_id']
        data['check_command'] = data_cmd_ping['_id']
        data['_realm'] = cls.realm_all
        data['users'] = [data_user_jeronimo['_id']]
        data['usergroups'] = [data_usergroup['_id']]
        cls.data_srv_ping = cls.backend.post("service", data)

        # Add hostgroup
        data = {'name': 'allmyhosts', '_realm': cls.realm_all, 'hosts': [cls.data_host['_id']]}
        cls.backend.post("hostgroup", data)

        # add service http
        data = json.loads(open('cfg/service_srv001_http.json').read())
        data['host'] = cls.data_host['_id']
        data['check_command'] = data_cmd_http['_id']
        data['_realm'] = cls.realm_all
        data['users'] = [data_user_jeronimo['_id']]
        data['usergroups'] = [data_usergroup['_id']]
        cls.data_srv_http = cls.backend.post("service", data)

        # Add some realms
        data = {
            'name': 'All-A',
            '_parent': cls.realm_all
        }
        realm_a = cls.backend.post("realm", data)
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

        # Start broker module
        modconf = Module()
        modconf.module_alias = "alignakbackendarbit"
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

    def test_commands(self):
        reference = [
            {   u'reactionner_tag': u'', 'command_name': u'_internal_host_up',
                u'command_line': u'_internal_host_up', u'enable_environment_macros': False,
                u'definition_order': 100, u'module_type': u'fork',
                u'imported_from': u'alignakbackend',
                u'poller_tag': u'', u'timeout': -1
            },
            {   u'reactionner_tag': u'', 'command_name': u'_echo', u'command_line': u'_echo',
                u'enable_environment_macros': False, u'definition_order': 100,
                u'module_type': u'fork',
                u'imported_from': u'alignakbackend', u'poller_tag': u'', u'timeout': -1
            },
            {
                u'command_line': u'_internal_host_up',
                u'command_name': u'_internal_host_up',
                u'definition_order': 100,
                u'enable_environment_macros': False,
                u'imported_from': u'alignakbackend',
                u'module_type': u'fork',
                u'poller_tag': u'',
                u'reactionner_tag': u'',
                u'timeout': -1
            },
            {
                u'command_line': u'_echo',
                u'command_name': u'_echo',
                u'definition_order': 100,
                u'enable_environment_macros': False,
                u'imported_from': u'alignakbackend',
                u'module_type': u'fork',
                u'poller_tag': u'',
                u'reactionner_tag': u'',
                u'timeout': -1
            },
            {
                u'definition_order': 100,
                u'poller_tag': u'',
                u'command_line': u'check_ping -H $HOSTADDRESS$',
                u'reactionner_tag': u'',
                u'module_type': u'fork',
                u'imported_from': u'alignakbackend',
                u'timeout': -1,
                u'enable_environment_macros': False,
                'command_name': u'ping'
            },
            {
                u'definition_order': 100,
                u'poller_tag': u'',
                u'command_line': u'check_http -H $HOSTADDRESS$',
                u'reactionner_tag': u'',
                u'module_type': u'fork',
                u'imported_from': u'alignakbackend',
                u'timeout': -1,
                u'enable_environment_macros': False,
                'command_name': u'check_http'
            }
        ]
        self.assertEqual(reference, self.objects['commands'])
        for comm in self.objects['commands']:
            for key, value in comm.iteritems():
                self.assertTrue(Command.properties[key])

    def test_hostescalations(self):
        reference = []
        self.assertEqual(reference, self.objects['hostescalations'])

    def test_contacts(self):
        reference = [
            {
                u'definition_order': 100,
                u'service_notifications_enabled': True,
                u'can_submit_commands': False,
                u'can_update_livestate': True,
                'contact_name': u'admin',
                'service_notification_commands': '',
                u'service_notification_options': u'w,u,c,r,f,s',
                u'definition_order': 100,
                u'address1': u'',
                u'address2': u'',
                u'address3': u'',
                u'address4': u'',
                u'address5': u'',
                u'address6': u'',
                u'is_admin': False,
                u'password': self.objects['contacts'][0]['password'],
                u'pager': u'',
                u'imported_from': u'alignakbackend',
                u'notificationways': u'',
                u'host_notification_period': u'24x7',
                u'host_notifications_enabled': True,
                'host_notification_commands': '',
                u'service_notification_period': u'24x7',
                u'min_business_impact': 0,
                u'email': u'',
                u'alias': u'Administrator',
                u'host_notification_options': u'd,u,r,f,s'
            },
            {
                u'definition_order': 100,
                u'service_notifications_enabled': True,
                u'can_submit_commands': False,
                u'can_update_livestate': False,
                'contact_name': u'jeronimo',
                'service_notification_commands': '',
                u'service_notification_options': u'w,u,c,r,f,s',
                u'definition_order': 100,
                u'address1': u'',
                u'address2': u'',
                u'address3': u'',
                u'address4': u'',
                u'address5': u'',
                u'address6': u'',
                u'is_admin': False,
                u'password': self.objects['contacts'][1]['password'],
                u'pager': u'',
                u'imported_from': u'alignakbackend',
                u'notificationways': u'',
                u'host_notification_period': u'24x7',
                u'host_notifications_enabled': True,
                'host_notification_commands': '',
                u'service_notification_period': u'24x7',
                u'min_business_impact': 0,
                u'email': u'',
                u'alias': u'',
                u'host_notification_options': u'd,u,r,f,s'
            }
        ]
        self.assertItemsEqual(reference, self.objects['contacts'])
        for cont in self.objects['contacts']:
            for key, value in cont.iteritems():
                # problem in alignak because not defined
                if key not in ['can_update_livestate']:
                    self.assertTrue(Contact.properties[key])

    def test_timeperiods(self):
        reference = [
            {
                'definition_order': 100,
                'tuesday': '00:00-24:00',
                'friday': '00:00-24:00',
                'is_active': True,
                'wednesday': '00:00-24:00',
                'thursday': '00:00-24:00',
                'saturday': '00:00-24:00',
                'alias': 'All time default 24x7',
                'sunday': '00:00-24:00',
                'imported_from': u'alignakbackend',
                'exclude': '',
                'monday': '00:00-24:00',
                'timeperiod_name': '24x7'

            },
            {
                'definition_order': 100,
                'is_active': True,
                'alias': 'No time is a good time',
                'imported_from': u'alignakbackend',
                'exclude': '',
                'timeperiod_name': 'Never'

            }
        ]
        self.assertEqual(reference, self.objects['timeperiods'])

    def test_serviceescalations(self):
        reference = []
        self.assertEqual(reference, self.objects['serviceescalations'])

    def test_hostgroups(self):
        reference = [
            {
                u'action_url': u'',
                u'alias': u'All hosts',
                u'definition_order': 100,
                u'hostgroup_members': u'',
                u'hostgroup_name': u'All',
                u'imported_from': u'alignakbackend',
                u'members': u'',
                u'notes': u'',
                u'notes_url': u''
            },
            {
                u'action_url': u'',
                u'alias': u'',
                u'definition_order': 100,
                u'hostgroup_members': u'',
                u'hostgroup_name': u'allmyhosts',
                u'imported_from': u'alignakbackend',
                u'members': u'srv001',
                u'notes': u'',
                u'notes_url': u''
            }
        ]
        self.assertEqual(reference, self.objects['hostgroups'])
        for hostgrp in self.objects['hostgroups']:
            for key, value in hostgrp.iteritems():
                # problem in alignak because not defined
                if key not in ['hostgroup_members']:
                    self.assertTrue(Hostgroup.properties[key])

    def test_contactgroups(self):
        reference = [
            {
                u'contactgroup_name': u'admins',
                u'imported_from': u'alignakbackend',
                u'definition_order': 100,
                u'alias': u'',
                u'contactgroup_members': '',
                u'members': u'jeronimo'
            },
            {
                u'contactgroup_name': u'All',
                u'imported_from': u'alignakbackend',
                u'definition_order': 100,
                u'alias': u'All users',
                u'contactgroup_members': '',
                u'members': u''
            },
        ]
        self.assertItemsEqual(reference, self.objects['contactgroups'])

    def test_hosts(self):
        reference = [
            {
                'realm': 'All',
                u'active_checks_enabled': True,
                u'icon_image_alt': u'',
                u'business_impact_modulations': u'',
                u'retry_interval': 0,
                u'reactionner_tag': u'',
                u'parents': '',
                u'action_url': u'',
                u'notes_url': u'',
                u'snapshot_enabled': False,
                u'low_flap_threshold': 25,
                u'process_perf_data': True,
                u'icon_image': u'',
                u'service_overrides': u'',
                u'snapshot_interval': 5,
                u'notification_interval': 60,
                u'trending_policies': u'',
                u'failure_prediction_enabled': False,
                u'flap_detection_options': u'o,d,u',
                u'resultmodulations': u'',
                u'business_rule_downtime_as_ack': False,
                u'stalking_options': u'',
                u'event_handler_enabled': False,
                u'notes': u'',
                u'macromodulations': u'',
                u'host_name': u'srv001',
                u'trigger': u'',
                u'trigger_broker_raise_enabled': False,
                u'first_notification_delay': 0,
                u'flap_detection_enabled': True,
                u'business_rule_host_notification_options': u'd,u,r,f,s',
                u'passive_checks_enabled': True,
                u'service_includes': u'',
                u'icon_set': u'',
                u'definition_order': 100,
                u'snapshot_criteria': u'd,u',
                u'notifications_enabled': True,
                u'business_rule_smart_notifications': False,
                u'vrml_image': u'',
                u'custom_views': u'',
                u'address': u'192.168.0.2',
                u'display_name': u'',
                u'service_excludes': u'',
                u'imported_from': u'alignakbackend',
                u'3d_coords': u'',
                u'time_to_orphanage': 300,
                u'initial_state': u'u',
                u'statusmap_image': u'',
                u'2d_coords': u'',
                u'check_command': u'ping',
                u'checkmodulations': u'',
                u'notification_options': u'd,u,r,f,s',
                u'labels': u'',
                u'poller_tag': u'',
                u'obsess_over_host': False,
                u'high_flap_threshold': 50,
                u'check_interval': 5,
                u'business_impact': 2,
                u'max_check_attempts': 1,
                u'business_rule_output_template': u'',
                u'business_rule_service_notification_options': u'w,u,c,r,f,s',
                u'check_freshness': False,
                u'freshness_threshold': 0,
                u'freshness_state': u'u',
                u'contacts': u'jeronimo',
                u'contact_groups': u'admins',
                # u'ls_acknowledged': False,
                # u'ls_current_attempt': 0,
                # u'ls_downtimed': False,
                # u'ls_execution_time': 0.0,
                # u'ls_grafana': False,
                # u'ls_grafana_panelid': 0,
                # u'ls_impact': False,
                # u'ls_last_check': 0,
                # u'ls_last_state': u'OK',
                # u'ls_last_state_changed': 0,
                # u'ls_last_state_type': u'HARD',
                # u'ls_latency': 0.0,
                # u'ls_long_output': u'',
                # u'ls_max_attempts': 0,
                # u'ls_next_check': 0,
                # u'ls_output': u'',
                # u'ls_perf_data': u'',
                # u'ls_state': u'UNREACHABLE',
                # u'ls_state_id': 0,
                # u'ls_state_type': u'HARD',
            }
        ]
        self.assertEqual(len(self.objects['hosts']), 1)
        for host in self.objects['hosts']:
            for key, value in host.iteritems():
                if not key.startswith('ls_'):
                    self.assertTrue(Host.properties[key])

        self.assertEqual(reference, self.objects['hosts'])

    def test_realms(self):
        reference = [
            {
                u'default': True,
                'realm_name': u'All',
                'realm_members': [],
                u'definition_order': 100,
                u'imported_from': u'alignakbackend'
            },
            {
                u'default': False,
                'realm_name': u'All-A',
                'realm_members': [],
                u'definition_order': 100,
                u'imported_from': u'alignakbackend'
            },
            {
                u'default': False,
                'realm_name': u'All-B',
                'realm_members': [],
                u'definition_order': 100,
                u'imported_from': u'alignakbackend'
            },
            {
                u'default': False,
                'realm_name': u'All-A-1',
                'realm_members': [],
                u'definition_order': 100,
                u'imported_from': u'alignakbackend'
            },
        ]
        self.assertItemsEqual(reference, self.objects['realms'])
        for realm in self.objects['realms']:
            for key, value in realm.iteritems():
                self.assertTrue(Realm.properties[key])

    def test_services(self):
        reference = [
            {
                'hostgroup_name': u'',
                u'active_checks_enabled': True,
                u'icon_image_alt': u'',
                u'business_impact_modulations': u'',
                u'retry_interval': 0,
                u'checkmodulations': u'',
                u'obsess_over_service': False,
                u'action_url': u'',
                u'is_volatile': False,
                u'snapshot_enabled': False,
                u'low_flap_threshold': -1,
                u'process_perf_data': True,
                u'icon_image': u'',
                u'snapshot_interval': 5,
                u'default_value': u'',
                u'business_rule_service_notification_options': u'',
                u'display_name': u'',
                u'notification_interval': 60,
                u'trending_policies': u'',
                u'failure_prediction_enabled': False,
                u'flap_detection_options': u'o,w,c,u',
                u'resultmodulations': u'',
                u'business_rule_downtime_as_ack': False,
                u'stalking_options': u'',
                u'event_handler_enabled': False,
                u'macromodulations': u'',
                u'initial_state': u'u',
                u'first_notification_delay': 0,
                u'flap_detection_enabled': True,
                u'business_rule_host_notification_options': u'',
                u'passive_checks_enabled': True,
                u'host_dependency_enabled': True,
                u'labels': u'',
                u'icon_set': u'',
                u'definition_order': 100,
                u'parallelize_check': True,
                u'snapshot_criteria': u'w,c,u',
                u'notifications_enabled': True,
                u'aggregation': u'',
                u'business_rule_smart_notifications': False,
                'host_name': u'srv001',
                u'reactionner_tag': u'',
                'service_description': u'ping',
                u'imported_from': u'alignakbackend',
                'service_dependencies': u'',
                u'time_to_orphanage': 300,
                u'trigger': u'',
                u'trigger_broker_raise_enabled': False,
                u'custom_views': u'',
                u'check_command': u'ping!',
                u'notification_options': u'w,u,c,r,f,s',
                u'notes_url': u'',
                u'poller_tag': u'',
                'merge_host_contacts': False,
                u'high_flap_threshold': -1,
                u'check_interval': 5,
                u'business_impact': 2,
                u'max_check_attempts': 1,
                u'notes': u'',
                u'freshness_threshold': 0,
                u'check_freshness': False,
                u'freshness_state': u'o',
                u'contacts': u'jeronimo',
                u'contact_groups': u'admins',
                u'escalations': u'',
                # u'ls_acknowledged': False,
                # u'ls_current_attempt': 0,
                # u'ls_downtimed': False,
                # u'ls_execution_time': 0.0,
                # u'ls_grafana': False,
                # u'ls_grafana_panelid': 0,
                # u'ls_impact': False,
                # u'ls_last_check': 0,
                # u'ls_last_state': u'OK',
                # u'ls_last_state_changed': 0,
                # u'ls_last_state_type': u'HARD',
                # u'ls_latency': 0.0,
                # u'ls_long_output': u'',
                # u'ls_max_attempts': 0,
                # u'ls_next_check': 0,
                # u'ls_output': u'',
                # u'ls_perf_data': u'',
                # u'ls_state': u'UNKNOWN',
                # u'ls_state_id': 0,
                # u'ls_state_type': u'HARD',
            },
            {
                'hostgroup_name': u'',
                u'active_checks_enabled': True,
                u'icon_image_alt': u'',
                u'business_impact_modulations': u'',
                u'retry_interval': 0,
                u'checkmodulations': u'',
                u'obsess_over_service': False,
                u'action_url': u'',
                u'is_volatile': False,
                u'snapshot_enabled': False,
                u'low_flap_threshold': -1,
                u'process_perf_data': True,
                u'icon_image': u'',
                u'snapshot_interval': 5,
                u'default_value': u'',
                u'business_rule_service_notification_options': u'',
                u'display_name': u'',
                u'notification_interval': 60,
                u'trending_policies': u'',
                u'failure_prediction_enabled': False,
                u'flap_detection_options': u'o,w,c,u',
                u'resultmodulations': u'',
                u'business_rule_downtime_as_ack': False,
                u'stalking_options': u'',
                u'event_handler_enabled': False,
                u'macromodulations': u'',
                u'initial_state': u'u',
                u'first_notification_delay': 0,
                u'flap_detection_enabled': True,
                u'business_rule_host_notification_options': u'',
                u'passive_checks_enabled': True,
                u'host_dependency_enabled': True,
                u'labels': u'',
                u'icon_set': u'',
                u'definition_order': 100,
                u'parallelize_check': True,
                u'snapshot_criteria': u'w,c,u',
                u'notifications_enabled': True,
                u'aggregation': u'',
                u'business_rule_smart_notifications': False,
                'host_name': u'srv001',
                u'reactionner_tag': u'',
                'service_description': u'http toto.com',
                u'imported_from': u'alignakbackend',
                'service_dependencies': u'',
                u'time_to_orphanage': 300,
                u'trigger': u'',
                u'trigger_broker_raise_enabled': False,
                u'custom_views': u'',
                u'check_command': u'check_http!',
                u'notification_options': u'w,u,c,r,f,s',
                u'notes_url': u'',
                u'poller_tag': u'',
                'merge_host_contacts': False,
                u'high_flap_threshold': -1,
                u'check_interval': 5,
                u'business_impact': 2,
                u'max_check_attempts': 1,
                u'notes': u'',
                u'freshness_threshold': 0,
                u'check_freshness': False,
                u'freshness_state': u'o',
                u'contacts': u'jeronimo',
                u'contact_groups': u'admins',
                u'escalations': u'',
                # u'ls_acknowledged': False,
                # u'ls_current_attempt': 0,
                # u'ls_downtimed': False,
                # u'ls_execution_time': 0.0,
                # u'ls_grafana': False,
                # u'ls_grafana_panelid': 0,
                # u'ls_impact': False,
                # u'ls_last_check': 0,
                # u'ls_last_state': u'OK',
                # u'ls_last_state_changed': 0,
                # u'ls_last_state_type': u'HARD',
                # u'ls_latency': 0.0,
                # u'ls_long_output': u'',
                # u'ls_max_attempts': 0,
                # u'ls_next_check': 0,
                # u'ls_output': u'',
                # u'ls_perf_data': u'',
                # u'ls_state': u'UNKNOWN',
                # u'ls_state_id': 0,
                # u'ls_state_type': u'HARD',
            }
        ]
        self.assertEqual(len(self.objects['services']), 2)
        self.assertEqual(reference, self.objects['services'])
        for serv in self.objects['services']:
            for key, value in serv.iteritems():
                if not key.startswith('ls_'):
                    self.assertTrue(Service.properties[key])

    def test_servicegroups(self):
        reference = [
            {
                u'action_url': u'',
                u'alias': u'All services',
                u'definition_order': 100,
                u'servicegroup_members': u'',
                u'servicegroup_name': u'All',
                u'imported_from': u'alignakbackend',
                u'members': u'',
                u'notes': u'',
                u'notes_url': u''
            },
        ]
        self.assertEqual(reference, self.objects['servicegroups'])

    def test_triggers(self):
        reference = []
        self.assertEqual(reference, self.objects['triggers'])

    def test_hostdependencies(self):
        reference = []
        print("Host dependencies: %s" % self.objects['hostdependencies'])
        self.assertEqual(reference, self.objects['hostdependencies'])

    def test_servicedependencies(self):
        reference = []
        self.assertEqual(reference, self.objects['servicedependencies'])
