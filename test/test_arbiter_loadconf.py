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


class TestArbiterLoadConfiguration(unittest2.TestCase):

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
        data = {
            'name': 'jeronimo',
            'customs': {'_OS': 'linux', 'licence': 'free ;)'},
            'host_notification_period': timeperiods_id,
            'service_notification_period': timeperiods_id,
            '_realm': cls.realm_all
        }
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
        data['customs'] = {'_OS': 'linux', 'licence': 'free ;)'}
        data['users'] = [data_user_jeronimo['_id']]
        data['usergroups'] = [data_usergroup['_id']]
        cls.data_host = cls.backend.post("host", data)

        # Add hostgroup
        data = {'name': 'allmyhosts', '_realm': cls.realm_all, 'hosts': [cls.data_host['_id']]}
        cls.data_hostgroup = cls.backend.post("hostgroup", data)

        # add service ping
        data = json.loads(open('cfg/service_srv001_ping.json').read())
        data['host'] = cls.data_host['_id']
        data['check_command'] = data_cmd_ping['_id']
        data['_realm'] = cls.realm_all
        data['users'] = [data_user_jeronimo['_id']]
        data['usergroups'] = [data_usergroup['_id']]
        cls.data_srv_ping = cls.backend.post("service", data)

        # add service pong
        data = json.loads(open('cfg/service_srv001_pong.json').read())
        data['host'] = cls.data_host['_id']
        data['check_command'] = data_cmd_ping['_id']
        data['_realm'] = cls.realm_all
        data['users'] = [data_user_jeronimo['_id']]
        data['usergroups'] = [data_usergroup['_id']]
        data['hostgroups'] = [cls.data_hostgroup['_id']]
        cls.data_srv_pong = cls.backend.post("service", data)

        # add service http
        data = json.loads(open('cfg/service_srv001_http.json').read())
        data['host'] = cls.data_host['_id']
        data['check_command'] = data_cmd_http['_id']
        data['_realm'] = cls.realm_all
        data['customs'] = {'_OS': 'linux', 'licence': 'free ;)'}
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

        # Start arbiter backend module
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

    def test_commands(self):
        # Note that empty poller_tag is not provided by the arbiter module
        reference = [
            {
                'command_line': '_internal_host_up',
                'command_name': '_internal_host_up',
                'definition_order': 50,
                'enable_environment_macros': False,
                'imported_from': 'alignak-backend',
                'module_type': 'fork',
                # u'poller_tag': u'',
                'reactionner_tag': '',
                'timeout': -1
            },
            {
                'command_line': '_echo',
                'command_name': '_echo',
                'definition_order': 50,
                'enable_environment_macros': False,
                'imported_from': 'alignak-backend',
                'module_type': 'fork',
                # u'poller_tag': u'',
                'reactionner_tag': '',
                'timeout': -1
            },
            {
                'definition_order': 50,
                # u'poller_tag': u'',
                'command_line': 'check_ping -H $HOSTADDRESS$',
                'reactionner_tag': '',
                'module_type': 'fork',
                'imported_from': 'alignak-backend',
                'timeout': -1,
                'enable_environment_macros': False,
                'command_name': 'ping'
            },
            {
                'definition_order': 50,
                # u'poller_tag': u'',
                'command_line': 'check_http -H $HOSTADDRESS$',
                'reactionner_tag': '',
                'module_type': 'fork',
                'imported_from': 'alignak-backend',
                'timeout': -1,
                'enable_environment_macros': False,
                'command_name': 'check_http'
            }
        ]
        self.assertEqual(reference, self.objects['commands'])
        for comm in self.objects['commands']:
            for key, value in comm.items():
                self.assertTrue(Command.properties[key])

    def test_hostescalations(self):
        reference = []
        self.assertEqual(reference, self.objects['hostescalations'])

    def test_contacts(self):
        reference = [
            # the default admin user has notifications disabled
            {
                'definition_order': 50,
                'service_notifications_enabled': False,
                'can_submit_commands': True,
                # u'can_update_livestate': True,
                'contact_name': 'admin',
                'service_notification_commands': '',
                'service_notification_options': 'w,u,c,r,f,s',
                'address1': '',
                'address2': '',
                'address3': '',
                'address4': '',
                'address5': '',
                'address6': '',
                'is_admin': True,
                'password': self.objects['contacts'][0]['password'],
                'pager': '',
                'imported_from': 'alignak-backend',
                'notificationways': '',
                'host_notification_period': '24x7',
                'host_notifications_enabled': False,
                'host_notification_commands': '',
                'service_notification_period': '24x7',
                'min_business_impact': 0,
                'email': '',
                'alias': 'Administrator',
                'host_notification_options': 'd,u,r,f,s',
                # u'skill_level': 2,
                'webui_visible': True
            },
            # the test created user has default notifications (eg. enabled)
            {
                # Variables defined in customs properties are prefixed with _ and uppercased!
                '_OS': 'linux',
                '_LICENCE': 'free ;)',
                # Other properties are as is
                'definition_order': 50,
                'service_notifications_enabled': False,
                'can_submit_commands': False,
                # u'can_update_livestate': False,
                'contact_name': 'jeronimo',
                'service_notification_commands': '',
                'service_notification_options': 'w,u,c,r,f,s',
                'address1': '',
                'address2': '',
                'address3': '',
                'address4': '',
                'address5': '',
                'address6': '',
                'is_admin': False,
                'password': self.objects['contacts'][1]['password'],
                'pager': '',
                'imported_from': 'alignak-backend',
                'notificationways': '',
                'host_notification_period': '24x7',
                'host_notifications_enabled': False,
                'host_notification_commands': '',
                'service_notification_period': '24x7',
                'min_business_impact': 0,
                'email': '',
                'alias': 'jeronimo',
                'host_notification_options': 'd,u,r,f,s',
                # u'skill_level': 0,
                'webui_visible': True
            }
        ]
        self.assertItemsEqual(reference, self.objects['contacts'])
        for cont in self.objects['contacts']:
            for key, value in cont.items():
                # problem in alignak because not defined
                if key not in ['can_update_livestate', 'skill_level', 'webui_visible'] \
                        and not key.startswith('_'):
                    self.assertTrue(Contact.properties[key])

    def test_timeperiods(self):
        reference = [
            {
                'definition_order': 50,
                'tuesday': '00:00-24:00',
                'friday': '00:00-24:00',
                'is_active': True,
                'wednesday': '00:00-24:00',
                'thursday': '00:00-24:00',
                'saturday': '00:00-24:00',
                'alias': 'All time default 24x7',
                'sunday': '00:00-24:00',
                'imported_from': 'alignak-backend',
                'exclude': '',
                'monday': '00:00-24:00',
                'timeperiod_name': '24x7'

            },
            {
                'definition_order': 50,
                'is_active': True,
                'alias': 'No time is a good time',
                'imported_from': 'alignak-backend',
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
                'action_url': '',
                'alias': 'All hosts',
                'definition_order': 50,
                'hostgroup_members': '',
                'hostgroup_name': 'All',
                'imported_from': 'alignak-backend',
                'members': '',
                'notes': '',
                'notes_url': ''
            },
            {
                'action_url': '',
                'alias': 'allmyhosts',
                'definition_order': 50,
                'hostgroup_members': '',
                'hostgroup_name': 'allmyhosts',
                'imported_from': 'alignak-backend',
                'members': 'srv001',
                'notes': '',
                'notes_url': ''
            }
        ]
        self.assertEqual(reference, self.objects['hostgroups'])
        for hostgrp in self.objects['hostgroups']:
            for key, value in hostgrp.items():
                # problem in alignak because not defined
                if key not in ['hostgroup_members']:
                    self.assertTrue(Hostgroup.properties[key])

    def test_contactgroups(self):
        reference = [
            {
                'contactgroup_name': 'admins',
                'imported_from': 'alignak-backend',
                'definition_order': 50,
                'alias': 'admins',
                'contactgroup_members': '',
                'members': 'jeronimo'
            },
            {
                'contactgroup_name': 'All',
                'imported_from': 'alignak-backend',
                'definition_order': 50,
                'alias': 'All users',
                'contactgroup_members': '',
                'members': ''
            },
        ]
        self.assertItemsEqual(reference, self.objects['contactgroups'])

    def test_hosts(self):
        reference = [
            {
                # Variables defined in customs properties are prefixed with _ and uppercased!
                '_OS': 'linux',
                '_LICENCE': 'free ;)',
                # Other properties are as is
                'realm': 'All',
                'active_checks_enabled': True,
                'icon_image_alt': '',
                'business_impact_modulations': '',
                'retry_interval': 0,
                'parents': '',
                'action_url': '',
                'notes_url': '',
                'snapshot_enabled': False,
                'snapshot_period': 'Never',
                'maintenance_period': 'Never',
                'low_flap_threshold': 25,
                'process_perf_data': True,
                'icon_image': '',
                'service_overrides': '',
                'snapshot_interval': 5,
                'notification_interval': 60,
                'trending_policies': '',
                'flap_detection_options': 'o,d,x',
                'resultmodulations': '',
                'business_rule_downtime_as_ack': False,
                'stalking_options': '',
                'event_handler_enabled': False,
                'event_handler': '',
                'notes': '',
                'macromodulations': '',
                'host_name': 'srv001',
                'alias': 'srv001',
                'trigger_name': '',
                'trigger_broker_raise_enabled': False,
                'first_notification_delay': 0,
                'flap_detection_enabled': True,
                'business_rule_host_notification_options': 'd,u,r,f,s',
                'passive_checks_enabled': True,
                'service_includes': '',
                'icon_set': '',
                'definition_order': 50,
                'snapshot_criteria': 'd,x',
                'notifications_enabled': True,
                'business_rule_smart_notifications': False,
                'vrml_image': '',
                'custom_views': '',
                'address': '192.168.0.2',
                'address6': '',
                'display_name': '',
                'service_excludes': '',
                'imported_from': 'alignak-backend',
                '3d_coords': '',
                'time_to_orphanage': 300,
                'initial_state': 'x',
                'statusmap_image': '',
                '2d_coords': '',
                'check_command': 'ping',
                'checkmodulations': '',
                'notification_options': 'd,x,r,f,s',
                'notification_period': '24x7',
                'labels': '',
                'poller_tag': 'None',
                'reactionner_tag': 'None',
                'high_flap_threshold': 50,
                'check_interval': 5,
                'business_impact': 2,
                'max_check_attempts': 1,
                'business_rule_output_template': '',
                'business_rule_service_notification_options': 'w,u,c,r,f,s',
                'check_freshness': False,
                'freshness_threshold': 0,
                'freshness_state': 'x',
                'contacts': 'jeronimo',
                'contact_groups': 'admins',
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
            for key, value in host.items():
                print(("Got: %s = %s" % (key, value)))
                if not key.startswith('ls_') and not key.startswith('_') \
                        and not key.startswith('trigger'):
                    self.assertTrue(Host.properties[key])

        self.assertEqual(reference, self.objects['hosts'])

    def test_realms(self):
        # Note that realm members list is converted to a string
        reference = [
            {
                'default': True,
                'realm_name': 'All',
                'realm_members': 'All-A,All-B',
                'definition_order': 50,
                'imported_from': 'alignak-backend'
            },
            {
                'default': False,
                'realm_name': 'All-A',
                'realm_members': 'All-A-1',
                'definition_order': 50,
                'imported_from': 'alignak-backend'
            },
            {
                'default': False,
                'realm_name': 'All-B',
                'realm_members': '',
                'definition_order': 50,
                'imported_from': 'alignak-backend'
            },
            {
                'default': False,
                'realm_name': 'All-A-1',
                'realm_members': '',
                'definition_order': 50,
                'imported_from': 'alignak-backend'
            },
        ]
        self.assertItemsEqual(reference, self.objects['realms'])
        for realm in self.objects['realms']:
            for key, value in realm.items():
                self.assertTrue(Realm.properties[key])

    def test_services(self):
        self.maxDiff = None
        reference = [
            {
                # Variables defined in customs properties are prefixed with _ and uppercased!
                '_OS': 'linux',
                '_LICENCE': 'free ;)',
                # Other properties are as is
                'hostgroup_name': '',
                'active_checks_enabled': True,
                'icon_image_alt': '',
                'business_impact_modulations': '',
                'retry_interval': 0,
                'checkmodulations': '',
                'action_url': '',
                'is_volatile': False,
                'snapshot_enabled': False,
                'low_flap_threshold': 25,
                'process_perf_data': True,
                'icon_image': '',
                'snapshot_interval': 5,
                'snapshot_period': 'Never',
                'maintenance_period': 'Never',
                'default_value': '',
                'business_rule_service_notification_options': 'w,u,c,r,f,s',
                'business_rule_output_template': '',
                'display_name': '',
                'notification_interval': 60,
                'trending_policies': '',
                'flap_detection_options': 'o,w,c,u,x',
                'resultmodulations': '',
                'business_rule_downtime_as_ack': False,
                'stalking_options': '',
                'event_handler_enabled': False,
                'event_handler': '',
                'macromodulations': '',
                'initial_state': 'x',
                'first_notification_delay': 0,
                'flap_detection_enabled': True,
                'business_rule_host_notification_options': 'd,u,r,f,s',
                'passive_checks_enabled': True,
                'host_dependency_enabled': True,
                'labels': '',
                'icon_set': '',
                'definition_order': 50,
                'parallelize_check': True,
                'snapshot_criteria': 'w,c,x',
                'notifications_enabled': True,
                'aggregation': '',
                'business_rule_smart_notifications': False,
                'host_name': 'srv001',
                'poller_tag': 'None',
                'reactionner_tag': 'None',
                'service_description': 'http toto.com',
                'alias': 'http toto.com',
                'imported_from': 'alignak-backend',
                'service_dependencies': '',
                'time_to_orphanage': 300,
                'trigger_name': '',
                'trigger_broker_raise_enabled': False,
                'custom_views': '',
                'check_command': 'check_http',
                'notification_options': 'w,u,c,r,f,s,x',
                'notification_period': '24x7',
                'notes_url': '',
                'merge_host_contacts': False,
                'high_flap_threshold': 50,
                'check_interval': 5,
                'business_impact': 2,
                'max_check_attempts': 1,
                'notes': '',
                'freshness_threshold': 0,
                'check_freshness': False,
                'freshness_state': 'x',
                'contacts': 'jeronimo',
                'contact_groups': 'admins',
            },
            {
                'hostgroup_name': '',
                'active_checks_enabled': True,
                'icon_image_alt': '',
                'business_impact_modulations': '',
                'retry_interval': 0,
                'checkmodulations': '',
                'action_url': '',
                'is_volatile': False,
                'snapshot_enabled': False,
                'low_flap_threshold': 25,
                'process_perf_data': True,
                'icon_image': '',
                'snapshot_interval': 5,
                'snapshot_period': 'Never',
                'maintenance_period': 'Never',
                'default_value': '',
                'business_rule_service_notification_options': 'w,u,c,r,f,s',
                'business_rule_output_template': '',
                'display_name': '',
                'notification_interval': 60,
                'trending_policies': '',
                'flap_detection_options': 'o,w,c,u,x',
                'resultmodulations': '',
                'business_rule_downtime_as_ack': False,
                'stalking_options': '',
                'event_handler_enabled': False,
                'event_handler': '',
                'macromodulations': '',
                'initial_state': 'x',
                'first_notification_delay': 0,
                'flap_detection_enabled': True,
                'business_rule_host_notification_options': 'd,u,r,f,s',
                'passive_checks_enabled': True,
                'host_dependency_enabled': True,
                'labels': '',
                'icon_set': '',
                'definition_order': 50,
                'parallelize_check': True,
                'snapshot_criteria': 'w,c,x',
                'notifications_enabled': True,
                'aggregation': '',
                'business_rule_smart_notifications': False,
                'host_name': 'srv001',
                'poller_tag': 'None',
                'reactionner_tag': 'None',
                'service_description': 'ping',
                'alias': 'ping',
                'imported_from': 'alignak-backend',
                'service_dependencies': '',
                'time_to_orphanage': 300,
                'trigger_name': '',
                'trigger_broker_raise_enabled': False,
                'custom_views': '',
                'check_command': 'ping',
                'notification_options': 'w,u,c,r,f,s,x',
                'notification_period': '24x7',
                'notes_url': '',
                'merge_host_contacts': False,
                'high_flap_threshold': 50,
                'check_interval': 5,
                'business_impact': 2,
                'max_check_attempts': 1,
                'notes': '',
                'freshness_threshold': 0,
                'check_freshness': False,
                'freshness_state': 'x',
                'contacts': 'jeronimo',
                'contact_groups': 'admins',
            },
            {
                'hostgroup_name': 'allmyhosts',
                'active_checks_enabled': True,
                'icon_image_alt': '',
                'business_impact_modulations': '',
                'retry_interval': 0,
                'checkmodulations': '',
                'action_url': '',
                'is_volatile': False,
                'snapshot_enabled': False,
                'low_flap_threshold': 25,
                'process_perf_data': True,
                'icon_image': '',
                'snapshot_interval': 5,
                'snapshot_period': 'Never',
                'maintenance_period': 'Never',
                'default_value': '',
                'business_rule_service_notification_options': 'w,u,c,r,f,s',
                'business_rule_output_template': '',
                'display_name': '',
                'notification_interval': 60,
                'trending_policies': '',
                'flap_detection_options': 'o,w,c,u,x',
                'resultmodulations': '',
                'business_rule_downtime_as_ack': False,
                'stalking_options': '',
                'event_handler_enabled': False,
                'event_handler': '',
                'macromodulations': '',
                'initial_state': 'x',
                'first_notification_delay': 0,
                'flap_detection_enabled': True,
                'business_rule_host_notification_options': 'd,u,r,f,s',
                'passive_checks_enabled': True,
                'host_dependency_enabled': True,
                'labels': '',
                'icon_set': '',
                'definition_order': 50,
                'parallelize_check': True,
                'snapshot_criteria': 'w,c,x',
                'notifications_enabled': True,
                'aggregation': '',
                'business_rule_smart_notifications': False,
                'host_name': 'srv001',
                'poller_tag': 'None',
                'reactionner_tag': 'None',
                'service_description': 'pong',
                'alias': 'pong',
                'imported_from': 'alignak-backend',
                'service_dependencies': '',
                'time_to_orphanage': 300,
                'trigger_name': '',
                'trigger_broker_raise_enabled': False,
                'custom_views': '',
                'check_command': 'ping',
                'notification_options': 'w,u,c,r,f,s,x',
                'notification_period': '24x7',
                'notes_url': '',
                'merge_host_contacts': False,
                'high_flap_threshold': 50,
                'check_interval': 5,
                'business_impact': 2,
                'max_check_attempts': 1,
                'notes': '',
                'freshness_threshold': 0,
                'check_freshness': False,
                'freshness_state': 'x',
                'contacts': 'jeronimo',
                'contact_groups': 'admins',
            },
        ]
        self.assertEqual(len(self.objects['services']), 3)
        sorted_reference = sorted(reference, key=lambda k: k["service_description"])
        sorted_list = sorted(self.objects['services'], key=lambda k: k["service_description"])
        self.assertEqual(sorted_reference, sorted_list)
        for serv in self.objects['services']:
            for key, value in serv.items():
                if not key.startswith('ls_') and not key.startswith('_') and \
                        not key.startswith('trigger'):
                    self.assertTrue(Service.properties[key])

    def test_servicegroups(self):
        reference = [
            {
                'action_url': '',
                'alias': 'All services',
                'definition_order': 50,
                'servicegroup_members': '',
                'servicegroup_name': 'All',
                'imported_from': 'alignak-backend',
                'members': '',
                'notes': '',
                'notes_url': ''
            },
        ]
        self.assertEqual(reference, self.objects['servicegroups'])

    def test_hostdependencies(self):
        reference = []
        print(("Host dependencies: %s" % self.objects['hostdependencies']))
        self.assertEqual(reference, self.objects['hostdependencies'])

    def test_servicedependencies(self):
        reference = []
        self.assertEqual(reference, self.objects['servicedependencies'])
