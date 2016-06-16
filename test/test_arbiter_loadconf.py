#!/usr/bin/env python
# -*- coding: utf-8 -*-

import ujson
import unittest2
import time
import shlex
import subprocess
import json
from alignak_module_backend.arbiter.module import AlignakBackendArbit
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

        # Delete used mongo DBs
        exit_code = subprocess.call(
            shlex.split(
                'mongo %s --eval "db.dropDatabase()"' % 'alignak-backend')
        )
        assert exit_code == 0

        cls.p = subprocess.Popen(['uwsgi', '-w', 'alignakbackend:app', '--socket', '0.0.0.0:5000',
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
        # add host template
        data = json.loads(open('cfg/host_srvtemplate.json').read())
        data['check_command'] = data_cmd_ping['_id']
        data['realm'] = cls.realm_all
        cls.data_host = cls.backend.post("host", data)

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

        # Add hostgroup
        data = {'name': 'allmyhosts', 'realm': cls.realm_all, 'hosts': [cls.data_host['_id']]}
        cls.backend.post("hostgroup", data)

        data = json.loads(open('cfg/service_srv001_http.json').read())
        data['host'] = cls.data_host['_id']
        data['check_command'] = data_cmd_http['_id']
        data['_realm'] = cls.realm_all
        cls.data_srv_http = cls.backend.post("service", data)

        # Add some realms
        data = {
            'name': 'All.A',
            '_parent': cls.realm_all
        }
        realm_a = cls.backend.post("realm", data)
        data = {
            'name': 'All.B',
            '_parent': cls.realm_all
        }
        cls.backend.post("realm", data)
        data = {
            'name': 'All.A.1',
            '_parent': realm_a['_id']
        }
        cls.backend.post("realm", data)

        # Start broker module
        modconf = Module()
        modconf.module_alias = "alignakbackendarbit"
        modconf.username = "admin"
        modconf.password = "admin"
        modconf.api_url = 'http://127.0.0.1:5000'
        cls.arbmodule = AlignakBackendArbit(modconf)
        cls.objects = cls.arbmodule.get_objects()

    @classmethod
    def tearDownClass(cls):
        """
        Kill uwsgi

        :return: None
        """
        subprocess.call(['uwsgi', '--stop', '/tmp/uwsgi.pid'])
        time.sleep(2)

    def test_servicedependencies(self):
        reference = []
        self.assertEqual(reference, self.objects['servicedependencies'])

    def test_commands(self):
        reference = [
            {
                u'definition_order': 100,
                u'poller_tag': u'None',
                u'command_line': u'check_ping -H $HOSTADDRESS$',
                u'reactionner_tag': u'None',
                u'module_type': u'fork',
                u'imported_from': u'alignakbackend',
                u'timeout': -1,
                u'enable_environment_macros': False,
                'command_name': u'ping'
            },
            {
                u'definition_order': 100,
                u'poller_tag': u'None',
                u'command_line': u'check_http -H $HOSTADDRESS$',
                u'reactionner_tag': u'None',
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
                'contact_name': u'admin',
                'service_notification_commands': '',
                u'expert': False,
                u'service_notification_options': 'w,u,c,r,f,s',
                u'definition_order': 100,
                u'address1': u'',
                u'address2': u'',
                u'address3': u'',
                u'address4': u'',
                u'address5': u'',
                u'address6': u'',
                u'is_admin': False,
                u'password':  self.objects['contacts'][0]['password'],
                u'pager': u'',
                u'imported_from': u'alignakbackend',
                u'notificationways': '',
                u'host_notification_period': u'24x7',
                u'host_notifications_enabled': True,
                'host_notification_commands': '',
                u'service_notification_period': u'24x7',
                u'min_business_impact': 0,
                u'email': u'',
                u'alias': u'',
                u'host_notification_options': 'd,u,r,f,s'
            }
        ]
        self.assertEqual(reference, self.objects['contacts'])
        for cont in self.objects['contacts']:
            for key, value in cont.iteritems():
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
                u'alias': u'',
                u'definition_order': 100,
                'hostgroup_members': '',
                'hostgroup_name': u'allmyhosts',
                u'imported_from': u'alignakbackend',
                u'members': 'srv001',
                u'notes': u'',
                u'notes_url': u'',
                u'realm': u'All'
            }
        ]
        self.assertEqual(reference, self.objects['hostgroups'])
        for hostgrp in self.objects['hostgroups']:
            for key, value in hostgrp.iteritems():
                # problem in alignak because not defined
                if key not in ['hostgroup_members']:
                    self.assertTrue(Hostgroup.properties[key])

    def test_contactgroups(self):
        reference = []
        self.assertEqual(reference, self.objects['contactgroups'])

    def test_hosts(self):
        reference = [
            {
                u'active_checks_enabled': True,
                u'icon_image_alt': u'',
                u'business_impact_modulations': '',
                u'retry_interval': 0,
                u'reactionner_tag': u'None',
                'parents': '',
                u'action_url': u'',
                u'notes_url': u'',
                u'snapshot_enabled': False,
                u'low_flap_threshold': 25,
                u'process_perf_data': True,
                u'icon_image': u'',
                u'service_overrides': '',
                u'snapshot_interval': 5,
                u'realm': u'All',
                u'notification_interval': 60,
                u'trending_policies': '',
                u'failure_prediction_enabled': False,
                u'flap_detection_options': 'o,d,u',
                u'resultmodulations': '',
                u'business_rule_downtime_as_ack': False,
                u'stalking_options': '',
                u'event_handler_enabled': False,
                u'notes': u'',
                u'macromodulations': '',
                'host_name': u'srv001',
                u'escalations': '',
                u'trigger_broker_raise_enabled': False,
                u'first_notification_delay': 0,
                u'flap_detection_enabled': True,
                u'business_rule_host_notification_options': 'd,u,r,f,s',
                u'passive_checks_enabled': True,
                u'service_includes': '',
                u'icon_set': u'',
                u'definition_order': 100,
                u'snapshot_criteria': 'd,u',
                u'notifications_enabled': True,
                u'business_rule_smart_notifications': False,
                u'vrml_image': u'',
                u'freshness_threshold': 0,
                u'custom_views': '',
                u'address': u'192.168.0.2',
                u'display_name': u'',
                u'service_excludes': '',
                u'imported_from': u'alignakbackend',
                u'3d_coords': u'',
                u'time_to_orphanage': 300,
                u'initial_state': u'u',
                u'statusmap_image': u'',
                u'2d_coords': u'',
                u'check_command': u'ping',
                u'checkmodulations': '',
                u'notification_options': 'd,u,r,f,s',
                u'labels': '',
                u'poller_tag': u'None',
                u'obsess_over_host': False,
                u'high_flap_threshold': 50,
                u'check_interval': 5,
                u'business_impact': 2,
                u'max_check_attempts': 1,
                u'business_rule_output_template': u'',
                u'business_rule_service_notification_options': 'w,u,c,r,f,s',
                u'check_freshness': False
            }
        ]
        self.assertEqual(reference, self.objects['hosts'])
        for host in self.objects['hosts']:
            for key, value in host.iteritems():
                self.assertTrue(Host.properties[key])

    def test_realms(self):
        reference = [
            {
                u'default': False,
                'realm_name': u'All.A',
                'realm_members': [],
                u'definition_order': 100,
                u'imported_from': u'alignakbackend'
            },
            {
                u'default': True,
                'realm_name': u'All',
                'realm_members': [],
                u'definition_order': 100,
                u'imported_from': u'alignakbackend'
            },
            {
                u'default': False,
                'realm_name': u'All.B',
                'realm_members': [],
                u'definition_order': 100,
                u'imported_from': u'alignakbackend'
            },
            {
                u'default': False,
                'realm_name': u'All.A.1',
                'realm_members': [],
                u'definition_order': 100,
                u'imported_from': u'alignakbackend'
            },
        ]
        self.assertEqual(reference, self.objects['realms'])
        for realm in self.objects['realms']:
            for key, value in realm.iteritems():
                self.assertTrue(Realm.properties[key])

    def test_services(self):
        reference = [
            {
                u'hostgroup_name': '',
                u'active_checks_enabled': True,
                u'icon_image_alt': u'',
                u'business_impact_modulations': '',
                u'retry_interval': 0,
                u'checkmodulations': '',
                u'obsess_over_service': False,
                u'action_url': u'',
                u'is_volatile': False,
                u'snapshot_enabled': False,
                u'low_flap_threshold': -1,
                u'process_perf_data': True,
                u'icon_image': u'',
                u'snapshot_interval': 5,
                u'default_value': u'',
                u'business_rule_service_notification_options': '',
                u'display_name': u'',
                u'notification_interval': 60,
                u'trending_policies': '',
                u'failure_prediction_enabled': False,
                u'flap_detection_options': 'o,w,c,u',
                u'resultmodulations': '',
                u'business_rule_downtime_as_ack': False,
                u'stalking_options': '',
                u'event_handler_enabled': False,
                u'macromodulations': '',
                u'initial_state': u'o',
                u'first_notification_delay': 0,
                u'flap_detection_enabled': True,
                u'business_rule_host_notification_options': '',
                u'passive_checks_enabled': True,
                u'host_dependency_enabled': True,
                u'labels': '',
                u'icon_set': u'',
                u'definition_order': 100,
                u'parallelize_check': True,
                u'snapshot_criteria': 'w,c,u',
                u'notifications_enabled': True,
                u'aggregation': u'',
                u'business_rule_smart_notifications': False,
                'host_name': u'srv001',
                u'reactionner_tag': u'None',
                'service_description': u'ping',
                u'imported_from': u'alignakbackend',
                'service_dependencies': '',
                u'time_to_orphanage': 300,
                u'trigger_broker_raise_enabled': False,
                u'custom_views': '',
                u'check_command': u'ping!',
                u'duplicate_foreach': u'',
                u'notification_options': 'w,u,c,r,f,s',
                u'notes_url': u'',
                u'poller_tag': u'None',
                'merge_host_contacts': False,
                u'high_flap_threshold': -1,
                u'check_interval': 5,
                u'business_impact': 2,
                u'max_check_attempts': 1,
                u'notes': u'',
                u'freshness_threshold': 0,
                u'check_freshness': False
            },
            {
                u'hostgroup_name': '',
                u'active_checks_enabled': True,
                u'icon_image_alt': u'',
                u'business_impact_modulations': '',
                u'retry_interval': 0,
                u'checkmodulations': '',
                u'obsess_over_service': False,
                u'action_url': u'',
                u'is_volatile': False,
                u'snapshot_enabled': False,
                u'low_flap_threshold': -1,
                u'process_perf_data': True,
                u'icon_image': u'',
                u'snapshot_interval': 5,
                u'default_value': u'',
                u'business_rule_service_notification_options': '',
                u'display_name': u'',
                u'notification_interval': 60,
                u'trending_policies': '',
                u'failure_prediction_enabled': False,
                u'flap_detection_options': 'o,w,c,u',
                u'resultmodulations': '',
                u'business_rule_downtime_as_ack': False,
                u'stalking_options': '',
                u'event_handler_enabled': False,
                u'macromodulations': '',
                u'initial_state': u'o',
                u'first_notification_delay': 0,
                u'flap_detection_enabled': True,
                u'business_rule_host_notification_options': '',
                u'passive_checks_enabled': True,
                u'host_dependency_enabled': True,
                u'labels': '',
                u'icon_set': u'',
                u'definition_order': 100,
                u'parallelize_check': True,
                u'snapshot_criteria': 'w,c,u',
                u'notifications_enabled': True,
                u'aggregation': u'',
                u'business_rule_smart_notifications': False,
                'host_name': u'srv001',
                u'reactionner_tag': u'None',
                'service_description': u'http toto.com',
                u'imported_from': u'alignakbackend',
                'service_dependencies': '',
                u'time_to_orphanage': 300,
                u'trigger_broker_raise_enabled': False,
                u'custom_views': '',
                u'check_command': u'check_http!',
                u'duplicate_foreach': u'',
                u'notification_options': 'w,u,c,r,f,s',
                u'notes_url': u'',
                u'poller_tag': u'None',
                'merge_host_contacts': False,
                u'high_flap_threshold': -1,
                u'check_interval': 5,
                u'business_impact': 2,
                u'max_check_attempts': 1,
                u'notes': u'',
                u'freshness_threshold': 0,
                u'check_freshness': False
            }
        ]
        self.assertEqual(reference, self.objects['services'])
        for serv in self.objects['services']:
            for key, value in serv.iteritems():
                self.assertTrue(Service.properties[key])

    def test_servicegroups(self):
        reference = []
        self.assertEqual(reference, self.objects['servicegroups'])

    def test_triggers(self):
        reference = []
        self.assertEqual(reference, self.objects['triggers'])

    def test_hostdependencies(self):
        reference = []
        self.assertEqual(reference, self.objects['hostdependencies'])
