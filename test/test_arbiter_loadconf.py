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

        # Add hostgroup
        data = {'name': 'allmyhosts', 'realm': cls.realm_all}
        hostgroup = cls.backend.post("hostgroup", data)

        # add host
        data = json.loads(open('cfg/host_srv001.json').read())
        data['check_command'] = data_cmd_ping['_id']
        data['realm'] = cls.realm_all
        data['hostgroups'] = [hostgroup['_id']]
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
                'definition_order': 100,
                'poller_tag': 'None',
                'command_line': 'check_ping -H $HOSTADDRESS$',
                'reactionner_tag': 'None',
                'module_type': 'fork',
                'imported_from': 'alignakbackend',
                'timeout': -1,
                'enable_environment_macros': False,
                'command_name': 'ping'
            },
            {
                'definition_order': 100,
                'poller_tag': 'None',
                'command_line': 'check_http -H $HOSTADDRESS$',
                'reactionner_tag': 'None',
                'module_type': 'fork',
                'imported_from': 'alignakbackend',
                'timeout': -1,
                'enable_environment_macros': False,
                'command_name': 'check_http'
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
                'definition_order': 100,
                'service_notifications_enabled': True,
                'can_submit_commands': False,
                'contact_name': 'admin',
                'service_notification_commands': '',
                'expert': False,
                'service_notification_options': 'w,u,c,r,f,s',
                'definition_order': 100,
                'address1': '',
                'address2': '',
                'address3': '',
                'address4': '',
                'address5': '',
                'address6': '',
                'is_admin': False,
                'password':  self.objects['contacts'][0]['password'],
                'pager': '',
                'imported_from': 'alignakbackend',
                'notificationways': '',
                'host_notification_period': '24x7',
                'host_notifications_enabled': True,
                'host_notification_commands': '',
                'service_notification_period': '24x7',
                'min_business_impact': 0,
                'email': '',
                'alias': '',
                'host_notification_options': 'd,u,r,f,s'
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
                'imported_from': 'alignakbackend',
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
                'action_url': '',
                'alias': '',
                'definition_order': 100,
                'hostgroup_members': '',
                'hostgroup_name': 'allmyhosts',
                'imported_from': 'alignakbackend',
                'members': '',
                'notes': '',
                'notes_url': '',
                'realm': 'All'
            }
        ]
        self.assertEqual(reference, self.objects['hostgroups'])
        for hostgrp in self.objects['hostgroups']:
            for key, value in hostgrp.iteritems():
                # problem in alignak because not defined
                if key not in ['hostgroup_members']:
                    self.assertTrue(Hostgroup.properties[key])

    def test_serviceextinfos(self):
        reference = []
        self.assertEqual(reference, self.objects['serviceextinfo'])

    def test_hostextinfos(self):
        reference = []
        self.assertEqual(reference, self.objects['hostextinfo'])

    def test_contactgroups(self):
        reference = []
        self.assertEqual(reference, self.objects['contactgroups'])

    def test_hosts(self):
        reference = [
            {
                'active_checks_enabled': True,
                'icon_image_alt': '',
                'business_impact_modulations': '',
                'retry_interval': 0,
                'reactionner_tag': 'None',
                'parents': '',
                'action_url': '',
                'notes_url': '',
                'snapshot_enabled': False,
                'low_flap_threshold': 25,
                'process_perf_data': True,
                'hostgroups': 'allmyhosts',
                'icon_image': '',
                'service_overrides': '',
                'snapshot_interval': 5,
                'realm': 'All',
                'notification_interval': 60,
                'trending_policies': '',
                'failure_prediction_enabled': False,
                'flap_detection_options': 'o,d,u',
                'resultmodulations': '',
                'business_rule_downtime_as_ack': False,
                'stalking_options': '',
                'event_handler_enabled': False,
                'trigger': '',
                'notes': '',
                'macromodulations': '',
                'host_name': 'srv001',
                'escalations': '',
                'trigger_broker_raise_enabled': False,
                'first_notification_delay': 0,
                'flap_detection_enabled': True,
                'business_rule_host_notification_options': 'd,u,r,f,s',
                'passive_checks_enabled': True,
                'service_includes': '',
                'icon_set': '',
                'definition_order': 100,
                'snapshot_criteria': 'd,u',
                'notifications_enabled': True,
                'business_rule_smart_notifications': False,
                'vrml_image': '',
                'freshness_threshold': 0,
                'custom_views': '',
                'address': '192.168.0.2',
                'display_name': '',
                'trigger_name': '',
                'service_excludes': '',
                'imported_from': 'alignakbackend',
                '3d_coords': '',
                'time_to_orphanage': 300,
                'initial_state': 'u',
                'statusmap_image': '',
                '2d_coords': '',
                'check_command': 'ping',
                'checkmodulations': '',
                'notification_options': 'd,u,r,f,s',
                'labels': '',
                'poller_tag': 'None',
                'obsess_over_host': False,
                'high_flap_threshold': 50,
                'check_interval': 5,
                'business_impact': 2,
                'max_check_attempts': 1,
                'business_rule_output_template': '',
                'business_rule_service_notification_options': 'w,u,c,r,f,s',
                'check_freshness': False
            }
        ]
        self.assertEqual(reference, self.objects['hosts'])
        for host in self.objects['hosts']:
            for key, value in host.iteritems():
                self.assertTrue(Host.properties[key])

    def test_escalations(self):
        reference = []
        self.assertEqual(reference, self.objects['escalations'])

    def test_realms(self):
        reference = [
            {
                'default': False,
                'realm_name': 'All.A',
                'realm_members': [],
                'imported_from': 'alignakbackend'
            },
            {
                'default': True,
                'realm_name': 'All',
                'realm_members': [],
                'imported_from': 'alignakbackend'
            },
            {
                'default': False,
                'realm_name': 'All.B',
                'realm_members': [],
                'imported_from': 'alignakbackend'
            },
            {
                'default': False,
                'realm_name': 'All.A.1',
                'realm_members': [],
                'imported_from': 'alignakbackend'
            },
        ]
        self.assertEqual(reference, self.objects['realms'])
        for realm in self.objects['realms']:
            for key, value in realm.iteritems():
                self.assertTrue(Realm.properties[key])

    def test_services(self):
        reference = [
            {
                'hostgroup_name': '',
                'active_checks_enabled': True,
                'icon_image_alt': '',
                'business_impact_modulations': '',
                'retry_interval': 0,
                'checkmodulations': '',
                'obsess_over_service': False,
                'action_url': '',
                'is_volatile': False,
                'snapshot_enabled': False,
                'low_flap_threshold': -1,
                'process_perf_data': True,
                'icon_image': '',
                'snapshot_interval': 5,
                'default_value': '',
                'business_rule_service_notification_options': '',
                'display_name': '',
                'notification_interval': 60,
                'trending_policies': '',
                'failure_prediction_enabled': False,
                'flap_detection_options': 'o,w,c,u',
                'resultmodulations': '',
                'business_rule_downtime_as_ack': False,
                'stalking_options': '',
                'event_handler_enabled': False,
                'trigger': '',
                'macromodulations': '',
                'initial_state': 'o',
                'first_notification_delay': 0,
                'flap_detection_enabled': True,
                'business_rule_host_notification_options': '',
                'passive_checks_enabled': True,
                'host_dependency_enabled': True,
                'labels': '',
                'icon_set': '',
                'definition_order': 100,
                'parallelize_check': True,
                'snapshot_criteria': 'w,c,u',
                'notifications_enabled': True,
                'aggregation': '',
                'business_rule_smart_notifications': False,
                'host_name': 'srv001',
                'reactionner_tag': 'None',
                'service_description': 'ping',
                'trigger_name': '',
                'imported_from': 'alignakbackend',
                'service_dependencies': '',
                'time_to_orphanage': 300,
                'trigger_broker_raise_enabled': False,
                'custom_views': '',
                'check_command': 'ping!',
                'duplicate_foreach': '',
                'notification_options': 'w,u,c,r,f,s',
                'notes_url': '',
                'poller_tag': 'None',
                'merge_host_contacts': False,
                'high_flap_threshold': -1,
                'check_interval': 5,
                'business_impact': 2,
                'max_check_attempts': 1,
                'notes': '',
                'freshness_threshold': 0,
                'check_freshness': False
            },
            {
                'hostgroup_name': '',
                'active_checks_enabled': True,
                'icon_image_alt': '',
                'business_impact_modulations': '',
                'retry_interval': 0,
                'checkmodulations': '',
                'obsess_over_service': False,
                'action_url': '',
                'is_volatile': False,
                'snapshot_enabled': False,
                'low_flap_threshold': -1,
                'process_perf_data': True,
                'icon_image': '',
                'snapshot_interval': 5,
                'default_value': '',
                'business_rule_service_notification_options': '',
                'display_name': '',
                'notification_interval': 60,
                'trending_policies': '',
                'failure_prediction_enabled': False,
                'flap_detection_options': 'o,w,c,u',
                'resultmodulations': '',
                'business_rule_downtime_as_ack': False,
                'stalking_options': '',
                'event_handler_enabled': False,
                'trigger': '',
                'macromodulations': '',
                'initial_state': 'o',
                'first_notification_delay': 0,
                'flap_detection_enabled': True,
                'business_rule_host_notification_options': '',
                'passive_checks_enabled': True,
                'host_dependency_enabled': True,
                'labels': '',
                'icon_set': '',
                'definition_order': 100,
                'parallelize_check': True,
                'snapshot_criteria': 'w,c,u',
                'notifications_enabled': True,
                'aggregation': '',
                'business_rule_smart_notifications': False,
                'host_name': 'srv001',
                'reactionner_tag': 'None',
                'service_description': 'http toto.com',
                'trigger_name': '',
                'imported_from': 'alignakbackend',
                'service_dependencies': '',
                'time_to_orphanage': 300,
                'trigger_broker_raise_enabled': False,
                'custom_views': '',
                'check_command': 'check_http!',
                'duplicate_foreach': '',
                'notification_options': 'w,u,c,r,f,s',
                'notes_url': '',
                'poller_tag': 'None',
                'merge_host_contacts': False,
                'high_flap_threshold': -1,
                'check_interval': 5,
                'business_impact': 2,
                'max_check_attempts': 1,
                'notes': '',
                'freshness_threshold': 0,
                'check_freshness': False
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
