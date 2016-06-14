#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Copyright (C) 2015-2015: Alignak team, see AUTHORS.txt file for contributors
#
# This file is part of Alignak.
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
This module is used to get configuration from alignak-backend with arbiter
"""

import time
from datetime import datetime
import os
import signal
from alignak_backend_client.client import Backend
# pylint: disable=F0401
from alignak.basemodule import BaseModule
# pylint: disable=F0401
from alignak.log import logger
from alignak.external_command import ExternalCommand


# pylint: disable=C0103
properties = {
    'daemons': ['arbiter'],
    'type': 'alignakbackendarbit',
    'external': False,
    'phases': ['configuration'],
    }


def get_instance(mod_conf):
    """Return a module instance for the plugin manager

    :param mod_conf: Configuration object
    :type mod_conf: object
    :return: AlignakBackendArbit instance
    :rtype: object
    """
    logger.info("[Backend Arbiter] Get a Alignak config module for plugin %s",
                mod_conf.get_name())
    instance = AlignakBackendArbit(mod_conf)
    return instance


class AlignakBackendArbit(BaseModule):
    """ This class is used to get configuration from alignak-backend
    """

    def __init__(self, modconf):
        BaseModule.__init__(self, modconf)
        self.url = getattr(modconf, 'api_url', 'http://localhost:5000')
        self.backend = Backend(self.url)
        self.backend.token = getattr(modconf, 'token', '')
        if self.backend.token == '':
            self.getToken(getattr(modconf, 'username', ''), getattr(modconf, 'password', ''),
                          getattr(modconf, 'allowgeneratetoken', False))
        self.verify_modification = int(getattr(modconf, 'verify_modification', 5))
        self.next_check = 0
        self.time_loaded_conf = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        self.configraw = {}
        self.config = {'commands': [],
                       'timeperiods': [],
                       'hosts': [],
                       'hostgroups': [],
                       'services': [],
                       'contacts': [],
                       'contactgroups': [],
                       'servicegroups': [],
                       'realms': [],
                       'escalations': [],
                       'hostdependencies': [],
                       'hostescalations': [],
                       'hostextinfo': [],
                       'servicedependencies': [],
                       'serviceescalations': [],
                       'serviceextinfo': [],
                       'triggers': []}

    # Common functions
    def do_loop_turn(self):
        """This function is called/used when you need a module with
        a loop function (and use the parameter 'external': True)
        """
        logger.info("[Backend Arbiter] In loop")
        time.sleep(1)

    def getToken(self, username, password, generatetoken):
        """
        Authenticate and get the token

        :param username: login name
        :type username: str
        :param password: password
        :type password: str
        :param generatetoken: if True allow generate token, otherwise not generate
        :type generatetoken: bool
        :return: None
        """
        generate = 'enabled'
        if not generatetoken:
            generate = 'disabled'
        self.backend.login(username, password, generate)

    def single_relation(self, resource, mapping, ctype):
        """
        Convert single embedded data to name of relation_data
        Example:
        {'contacts': {'_id': a3659204fe,'name':'admin'}}
        converted to:
        {'contacts': 'admin'}

        :param resource: dictionary got from alignak-backend
        :type resource: dict
        :param mapping: key value of resource
        :type mapping: str
        :param ctype: type of configraw (hosts, services, commands...)
        :type ctype: str
        """
        if mapping in resource:
            if resource[mapping] is not None:
                if resource[mapping] in self.configraw[ctype]:
                    resource[mapping] = self.configraw[ctype][resource[mapping]]

    def multiple_relation(self, resource, mapping, ctype):
        """
        Convert multiple embedded data to name of relation_data
        Example:
        {'contacts': [{'_id': a3659204fe,'contact_name':'admin'},
                      {'_id': a3659204ff,'contact_name':'admin2'}]}
        converted to:
        {'contacts': 'admin,admin2'}

        :param resource: dictionary got from alignak-backend
        :type resource: dict
        :param mapping: key value of resource
        :type mapping: str
        :param ctype: type of configraw (hosts, services, commands...)
        :type ctype: str
        """
        if mapping in resource:
            members = []
            for member in resource[mapping]:
                if member in self.configraw[ctype]:
                    members.append(self.configraw[ctype][member])
            resource[mapping] = ','.join(members)

    @classmethod
    def clean_unusable_keys(cls, resource):
        """
        Delete keys of dictionary not used

        :param resource: dictionary got from alignak-backend
        :type resource: dict
        :return:
        """
        fields = ['_links', '_updated', '_created', '_etag', '_id', 'name', 'ui', '_realm',
                  '_sub_realm', '_users_read', '_users_update', '_users_delete', '_parent',
                  '_tree_parents', '_tree_children', '_level', 'customs', 'host', 'service',
                  'back_role_super_admin', 'token', '_templates', '_template_fields', 'note',
                  '_is_template', '_templates_with_services', '_templates_from_host_template',
                  'merge_host_users']
        for field in fields:
            if field in resource:
                del resource[field]

    @classmethod
    def convert_lists(cls, resource):
        """
        Convert lists into string with values separated with comma

        :param resource: ressource
        :type resource: dict
        :return: None
        """
        for prop in resource:
            if isinstance(resource[prop], list):
                resource[prop] = ','.join(str(e) for e in resource[prop])
            elif isinstance(resource[prop], dict):
                logger.warning("=====> %s", prop)
                logger.warning(resource[prop])

    def get_realms(self):
        """
        Get realms from alignak_backend

        :return: None
        """
        self.configraw['realms'] = {}
        all_realms = self.backend.get_all('realm')
        logger.warning("[Alignak Backend Arbit] Got %d realms", len(all_realms['_items']))
        for realm in all_realms['_items']:
            self.configraw['realms'][realm['_id']] = realm['name']
            realm['imported_from'] = 'alignakbackend'
            realm['realm_name'] = realm['name']
            self.clean_unusable_keys(realm)
            # self.convert_lists(realm)
            self.config['realms'].append(realm)

    def get_commands(self):
        """
        Get commands from alignak_backend

        :return: None
        """
        self.configraw['commands'] = {}
        all_commands = self.backend.get_all('command')
        logger.warning("[Alignak Backend Arbit] Got %d commands", len(all_commands['_items']))
        for command in all_commands['_items']:
            self.configraw['commands'][command['_id']] = command['name']
            command['imported_from'] = 'alignakbackend'
            command['command_name'] = command['name']
            self.clean_unusable_keys(command)
            self.convert_lists(command)
            self.config['commands'].append(command)

    def get_timeperiods(self):
        """
        Get timeperiods from alignak_backend

        :return: None
        """
        self.configraw['timeperiods'] = {}
        all_timeperiods = self.backend.get_all('timeperiod')
        logger.warning("[Alignak Backend Arbit] Got %d timeperiods",
                       len(all_timeperiods['_items']))
        for timeperiod in all_timeperiods['_items']:
            self.configraw['timeperiods'][timeperiod['_id']] = timeperiod['name']
            timeperiod['imported_from'] = 'alignakbackend'
            timeperiod['timeperiod_name'] = timeperiod['name']
            for daterange in timeperiod['dateranges']:
                timeperiod.update(daterange)
            del timeperiod['dateranges']
            self.clean_unusable_keys(timeperiod)
            self.convert_lists(timeperiod)
            self.config['timeperiods'].append(timeperiod)

    def get_contactgroups(self):
        """
        Get contactgroups from alignak_backend

        :return: None
        """
        self.configraw['contactgroups'] = {}
        all_contactgroups = self.backend.get_all('usergroup')
        logger.warning("[Alignak Backend Arbit] Got %d contactgroups",
                       len(all_contactgroups['_items']))
        for contactgroup in all_contactgroups['_items']:
            self.configraw['contactgroups'][contactgroup['_id']] = contactgroup['name']
            contactgroup['imported_from'] = 'alignakbackend'
            contactgroup['contactgroup_name'] = contactgroup['name']
            self.clean_unusable_keys(contactgroup)
            self.convert_lists(contactgroup)
            self.config['contactgroups'].append(contactgroup)

    def get_contact(self):
        """
        Get contacts from alignak_backend

        :return: None
        """
        self.configraw['contacts'] = {}
        all_contacts = self.backend.get_all('user')
        for contact in all_contacts['_items']:
            self.configraw['contacts'][contact['_id']] = contact['name']
            contact['imported_from'] = 'alignakbackend'
            contact['contact_name'] = contact['name']

            # host_notification_period
            self.single_relation(contact, 'host_notification_period', 'timeperiods')
            # service_notification_period
            self.single_relation(contact, 'service_notification_period', 'timeperiods')
            # host_notification_commands
            self.multiple_relation(contact, 'host_notification_commands', 'commands')
            # service_notification_commands
            self.multiple_relation(contact, 'service_notification_commands', 'commands')
            # contactgroups
            self.multiple_relation(contact, 'contactgroups', 'contactgroups')

            if 'host_notification_commands' not in contact:
                contact['host_notification_commands'] = ''
            if 'service_notification_commands' not in contact:
                contact['service_notification_commands'] = ''
            if 'host_notification_period' not in contact:
                contact['host_notification_period'] = \
                    self.config['timeperiods'][0]['timeperiod_name']
                contact['host_notifications_enabled'] = False
            if 'service_notification_period' not in contact:
                contact['service_notification_period'] = \
                    self.config['timeperiods'][0]['timeperiod_name']
                contact['service_notifications_enabled'] = False
            for key, value in contact['customs'].iteritems():
                contact[key] = value
            self.clean_unusable_keys(contact)
            self.convert_lists(contact)
            self.config['contacts'].append(contact)

    def get_hostgroups(self):
        """
        Get hostgroups from alignak_backend

        :return: None
        """
        self.configraw['hostgroups'] = {}
        all_hostgroups = self.backend.get_all('hostgroup')
        logger.warning("[Alignak Backend Arbit] Got %d hostgroups", len(all_hostgroups['_items']))
        for hostgroup in all_hostgroups['_items']:
            self.configraw['hostgroups'][hostgroup['_id']] = hostgroup['name']
            hostgroup['imported_from'] = 'alignakbackend'
            hostgroup['hostgroup_name'] = hostgroup['name']
            # realm
            self.single_relation(hostgroup, 'realm', 'realms')
            # members
            # ## self.multiple_relation(hostgroup, 'members', 'host_name')
            hostgroup['members'] = ''
            # hostgroup_members
            # ## self.multiple_relation(hostgroup, 'hostgroup_members', 'hostgroup_name')
            hostgroup['hostgroup_members'] = ''
            # realm
            if hostgroup['realm'] is None:
                del hostgroup['realm']

            self.clean_unusable_keys(hostgroup)
            self.convert_lists(hostgroup)
            self.config['hostgroups'].append(hostgroup)

    def get_hosts(self):
        """
        Get hosts from alignak_backend

        :return: None
        """
        self.configraw['hosts'] = {}
        all_hosts = self.backend.get_all('host', {"where": '{"_is_template": false}'})
        logger.warning("[Alignak Backend Arbit] Got %d hosts", len(all_hosts['_items']))
        for host in all_hosts['_items']:
            self.configraw['hosts'][host['_id']] = host['name']
            host['host_name'] = host['name']
            host['imported_from'] = 'alignakbackend'
            # check_command
            if 'check_command' in host:
                if host['check_command'] is None:
                    host['check_command'] = ''
                elif host['check_command'] in self.configraw['commands']:
                    host['check_command'] = self.configraw['commands'][host['check_command']]
                else:
                    host['check_command'] = ''
            if 'check_command_args' in host:
                if 'check_command' not in host:
                    host['check_command'] = ''
                elif host['check_command_args'] != '':
                    host['check_command'] += '!'
                    host['check_command'] += host['check_command_args']
                del host['check_command_args']
            # check_period
            self.single_relation(host, 'check_period', 'timeperiods')
            # realm
            self.single_relation(host, 'realm', 'realms')
            # notification_period
            self.single_relation(host, 'notification_period', 'timeperiods')
            # maintenance_period
            self.single_relation(host, 'maintenance_period', 'timeperiods')
            # snapshot_period
            self.single_relation(host, 'snapshot_period', 'timeperiods')
            # parents
            # ## self.multiple_relation(host, 'parents', 'host_name')
            host['parents'] = ''
            # hostgroups
            self.multiple_relation(host, 'hostgroups', 'hostgroups')
            # contacts
            self.multiple_relation(host, 'contacts', 'contacts')
            # contact_groups
            self.multiple_relation(host, 'contact_groups', 'contactgroups')
            # escalations
            # ## self.multiple_relation(host, 'escalations', 'escalation_name')
            if 'escalation' in host and host['escalation'] == '':
                del host['escalation']
            if 'alias' in host and host['alias'] == '':
                del host['alias']
            if 'realm' in host:
                if host['realm'] is None:
                    del host['realm']
            for key, value in host['customs'].iteritems():
                host[key] = value
            self.clean_unusable_keys(host)
            self.convert_lists(host)
            self.config['hosts'].append(host)

    def get_servicegroups(self):
        """
        Get servicegroups from alignak_backend

        :return: None
        """
        self.configraw['servicegroups'] = {}
        all_servicegroups = self.backend.get_all('servicegroup')
        logger.warning("[Alignak Backend Arbit] Got %d servicegroups",
                       len(all_servicegroups['_items']))
        for servicegroup in all_servicegroups['_items']:
            self.configraw['servicegroups'][servicegroup['_id']] = servicegroup['name']
            servicegroup['imported_from'] = 'alignakbackend'
            servicegroup['servicegroup_name'] = servicegroup['name']
            # members
            # ## self.multiple_relation(servicegroup, 'members', 'service_description')
            servicegroup['members'] = ''
            # servicegroup_members
            # ## self.multiple_relation(servicegroup, 'servicegroup_members', 'servicegroup_name')
            servicegroup['servicegroup_members'] = ''

            self.clean_unusable_keys(servicegroup)
            self.convert_lists(servicegroup)
            self.config['servicegroups'].append(servicegroup)

    def get_services(self):
        """
        Get services from alignak_backend

        :return: None
        """
        params = {'embedded': '{"escalations":1,"service_dependencies":1}',
                  "where": '{"_is_template": false}'}
        all_services = self.backend.get_all('service', params)
        logger.warning("[Alignak Backend Arbit] Got %d services", len(all_services['_items']))
        for service in all_services['_items']:
            service['imported_from'] = 'alignakbackend'
            service['service_description'] = service['name']
            service['host_name'] = service['host']
            service['merge_host_contacts'] = service['merge_host_users']
            # check_command
            if 'check_command' in service:
                if service['check_command'] is None:
                    del service['check_command']
                elif service['check_command'] in self.configraw['commands']:
                    service['check_command'] = self.configraw['commands'][service['check_command']]
                else:
                    del service['check_command']
            if 'check_command_args' in service:
                if 'check_command' not in service:
                    service['check_command'] = ''
                else:
                    service['check_command'] += '!'
                service['check_command'] += service['check_command_args']
                del service['check_command_args']
            # host_name
            self.single_relation(service, 'host_name', 'hosts')
            # check_period
            self.single_relation(service, 'check_period', 'timeperiods')
            # notification_period
            self.single_relation(service, 'notification_period', 'timeperiods')
            # maintenance_period
            self.single_relation(service, 'maintenance_period', 'timeperiods')
            # snapshot_period
            self.single_relation(service, 'snapshot_period', 'timeperiods')
            # servicegroups
            self.multiple_relation(service, 'servicegroups', 'servicegroups')
            # contacts
            self.multiple_relation(service, 'contacts', 'contacts')
            # contact_groups
            self.multiple_relation(service, 'contact_groups', 'contactgroups')
            # escalations
            # ## self.multiple_relation(service, 'escalations', 'escalation_name')
            if 'escalation' in service and service['escalation'] == '':
                del service['escalation']
            # service_dependencies
            # ## self.multiple_relation(service, 'service_dependencies', 'service_name')
            service['service_dependencies'] = ''
            if 'alias' in service and service['alias'] == '':
                del service['alias']
            for key, value in service['customs'].iteritems():
                service[key] = value
            self.clean_unusable_keys(service)
            self.convert_lists(service)
            self.config['services'].append(service)

    def get_escalations(self):
        """
        Get escalations from alignak_backend

        :return: None
        """
        self.configraw['escalations'] = {}
        all_escalations = self.backend.get_all('escalation')
        logger.warning("[Alignak Backend Arbit] Got %d escalations",
                       len(all_escalations['_items']))
        for escalation in all_escalations['_items']:
            self.configraw['escalations'][escalation['_id']] = escalation['name']
            escalation['escalation_name'] = escalation['name']
            escalation['imported_from'] = 'alignakbackend'
            # contacts
            self.multiple_relation(escalation, 'contacts', 'contacts')
            # contact_groups
            self.multiple_relation(escalation, 'contact_groups', 'contactgroups')
            self.clean_unusable_keys(escalation)
            self.convert_lists(escalation)
            self.config['escalations'].append(escalation)

    def get_hostdependencies(self):
        """
        Get hostdependencies from alignak_backend

        :return: None
        """
        self.configraw['hostdependencies'] = {}
        all_hostdependencies = self.backend.get_all('hostdependency')
        logger.warning("[Alignak Backend Arbit] Got %d hostdependencies",
                       len(all_hostdependencies['_items']))
        for hostdependency in all_hostdependencies['_items']:
            self.configraw['hostdependencies'][hostdependency['_id']] = hostdependency['name']
            hostdependency['imported_from'] = 'alignakbackend'
            hostdependency['hostdependency_name'] = hostdependency['name']
            hostdependency['host_name'] = hostdependency['host']

            # dependent_host_name
            self.multiple_relation(hostdependency, 'dependent_host_name', 'hosts')
            # dependent_hostgroup_name
            self.multiple_relation(hostdependency, 'dependent_hostgroup_name', 'hostgroups')
            # host_name
            self.multiple_relation(hostdependency, 'host_name', 'hosts')
            # hostgroup_name
            self.multiple_relation(hostdependency, 'hostgroup_name', 'hostgroups')
            self.clean_unusable_keys(hostdependency)
            self.convert_lists(hostdependency)
            if hostdependency['host_name'] != '' and hostdependency['dependent_host_name'] != '':
                self.config['hostdependencies'].append(hostdependency)

    def get_hostescalations(self):
        """
        Get hostescalations from alignak_backend

        :return: None
        """
        self.configraw['hostescalations'] = {}
        all_hostescalations = self.backend.get_all('hostescalation')
        logger.warning("[Alignak Backend Arbit] Got %d hostescalations",
                       len(all_hostescalations['_items']))
        for hostescalation in all_hostescalations['_items']:
            self.configraw['hostescalations'][hostescalation['_id']] = hostescalation['name']
            hostescalation['hostescalation_name'] = hostescalation['name']
            hostescalation['imported_from'] = 'alignakbackend'
            # host_name
            self.single_relation(hostescalation, 'host_name', 'hosts')
            # hostgroup_name
            self.multiple_relation(hostescalation, 'hostgroup_name', 'hostgroups')
            # contacts
            self.multiple_relation(hostescalation, 'contacts', 'contacts')
            # contact_groups
            self.multiple_relation(hostescalation, 'contact_groups', 'contactgroups')
            self.clean_unusable_keys(hostescalation)
            self.convert_lists(hostescalation)
            self.config['hostescalations'].append(hostescalation)

    def get_hostextinfos(self):
        """
        Get hostextinfos from alignak_backend

        :return: None
        """
        all_hostextinfos = self.backend.get_all('hostextinfo')
        logger.warning("[Alignak Backend Arbit] Got %d hostextinfos",
                       len(all_hostextinfos['_items']))
        for hostextinfo in all_hostextinfos['_items']:
            hostextinfo['hostextinfo_name'] = hostextinfo['name']
            hostextinfo['imported_from'] = 'alignakbackend'
            # host_name
            self.single_relation(hostextinfo, 'host_name', 'hosts')
            self.clean_unusable_keys(hostextinfo)
            self.convert_lists(hostextinfo)
            self.config['hostextinfos'].append(hostextinfo)

    def get_servicedependencies(self):
        """
        Get servicedependencies from alignak_backend

        :return: None
        """
        self.configraw['servicedependencies'] = {}
        all_servicedependencies = self.backend.get_all('servicedependency')
        logger.warning("[Alignak Backend Arbit] Got %d servicedependencies",
                       len(all_servicedependencies['_items']))
        for servicedependency in all_servicedependencies['_items']:
            self.configraw['servicedependencies'][servicedependency['_id']] = \
                servicedependency['name']
            servicedependency['imported_from'] = 'alignakbackend'
            servicedependency['servicedependency_name'] = servicedependency['name']
            # dependent_host_name
            self.multiple_relation(servicedependency, 'dependent_host_name', 'hosts')
            # dependent_hostgroup_name
            self.multiple_relation(servicedependency, 'dependent_hostgroup_name', 'hostgroups')
            # dependent_service_description
            self.multiple_relation(servicedependency, 'dependent_service_description', 'services')
            # host_name
            self.multiple_relation(servicedependency, 'host_name', 'hosts')
            # hostgroup_name
            self.multiple_relation(servicedependency, 'hostgroup_name', 'hostgroups')
            self.clean_unusable_keys(servicedependency)
            self.convert_lists(servicedependency)
            self.config['servicedependencies'].append(servicedependency)

    def get_serviceescalations(self):
        """
        Get serviceescalations from alignak_backend

        :return: None
        """
        self.configraw['serviceescalations'] = {}
        all_serviceescalations = self.backend.get_all('serviceescalation')
        logger.warning("[Alignak Backend Arbit] Got %d serviceescalations",
                       len(all_serviceescalations['_items']))
        for serviceescalation in all_serviceescalations['_items']:
            self.configraw['serviceescalations'][serviceescalation['_id']] = \
                serviceescalation['name']
            serviceescalation['serviceescalation_name'] = serviceescalation['name']
            serviceescalation['imported_from'] = 'alignakbackend'
            # host_name
            self.single_relation(serviceescalation, 'host_name', 'hosts')
            # hostgroup_name
            self.multiple_relation(serviceescalation, 'hostgroup_name', 'hostgroups')
            # service_description
            self.single_relation(serviceescalation, 'service_description', 'services')
            # contacts
            self.multiple_relation(serviceescalation, 'contacts', 'contacts')
            # contact_groups
            self.multiple_relation(serviceescalation, 'contact_groups', 'contactgroups')
            self.clean_unusable_keys(serviceescalation)
            self.convert_lists(serviceescalation)
            self.config['serviceescalations'].append(serviceescalation)

    def get_serviceextinfos(self):
        """
        Get serviceextinfos from alignak_backend

        :return: None
        """
        all_serviceextinfos = self.backend.get_all('serviceextinfo')
        logger.warning("[Alignak Backend Arbit] Got %d serviceextinfos",
                       len(all_serviceextinfos['_items']))
        for serviceextinfo in all_serviceextinfos['_items']:
            serviceextinfo['serviceextinfo_name'] = serviceextinfo['name']
            serviceextinfo['imported_from'] = 'alignakbackend'
            # host_name
            self.single_relation(serviceextinfo, 'host_name', 'hosts')
            # service_description
            self.single_relation(serviceextinfo, 'service_description', 'hosts')
            self.clean_unusable_keys(serviceextinfo)
            self.convert_lists(serviceextinfo)
            self.config['serviceextinfos'].append(serviceextinfo)

    def get_triggers(self):
        """
        Get triggers from alignak_backend

        :return: None
        """
        all_triggers = self.backend.get_all('trigger')
        logger.warning("[Alignak Backend Arbit] Got %d triggers", len(all_triggers['_items']))
        for trigger in all_triggers['_items']:
            trigger['trigger_name'] = trigger['name']
            trigger['imported_from'] = 'alignakbackend'
            self.clean_unusable_keys(trigger)
            self.convert_lists(trigger)
            self.config['triggers'].append(trigger)

    def get_objects(self):
        """
        Get objects from alignak-backend

        :return: configuration objects
        :rtype: dict
        """
        start_time = time.time()
        self.get_realms()
        self.get_commands()
        self.get_timeperiods()
        self.get_contactgroups()
        self.get_contact()
        self.get_hostgroups()
        self.get_hosts()
        self.get_servicegroups()
        self.get_services()
        self.get_escalations()
        self.get_hostdependencies()
        self.get_hostescalations()
        self.get_hostextinfos()
        self.get_servicedependencies()
        self.get_serviceescalations()
        self.get_serviceextinfos()
        self.get_triggers()

        self.time_loaded_conf = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

        logger.info("[backend arbiter] loaded in --- %s seconds ---", (time.time() - start_time))
        # Planify next execution in 10 minutes (need time to finish load config)
        self.next_check = int(time.time()) + (180 * self.verify_modification)
        return self.config

    def hook_tick(self, arbiter):
        """
        Hook in arbiter used to check if configuration has changed in the backend since
        last configuration loaded

        :param arbiter: alignak.daemons.arbiterdaemon.Arbiter
        :type arbiter: object
        :return: None
        """
        if int(time.time()) > self.next_check:
            logger.debug('Check if config in backend has changed')
            resources = ['realm', 'command', 'timeperiod', 'contactgroup', 'contact', 'hostgroup',
                         'host', 'servicegroup', 'service', 'escalation', 'hostdependency',
                         'hostescalation', 'hostextinfo', 'servicedependency', 'serviceescalation',
                         'serviceextinfo', 'trigger']
            reload_conf = False
            for resource in resources:
                ret = self.backend.get(resource, {'where': '{"_updated":{"$gte": "' +
                                                           self.time_loaded_conf + '"}}'})
                if ret['_meta']['total'] > -1:
                    reload_conf = True
            if reload_conf:
                logger.warning('Hey, we must reload conf from backend !!!!')
                with open(arbiter.pidfile, 'r') as f:
                    arbiterpid = f.readline()
                os.kill(int(arbiterpid), signal.SIGHUP)
            self.next_check = int(time.time()) + (60 * self.verify_modification)

    def get_acknowledge(self):
        """
        Get acknowledge from backend

        :return: None
        """
        all_ack = self.backend.get_all('actionacknowledge',
                                       {'where': '{"processed": "False"}',
                                        'embedded': '{"host": 1, "service": 1, "user": 1}'})
        for ack in all_ack['_items']:
            if ack['action'] == 'add':
                if ack['service']:
                    command = '[{}] ACKNOWLEDGE_SVC_PROBLEM;{};{};{};{};{};{};{}\n'.\
                        format(ack['_created'], ack['host']['name'], ack['service']['name'],
                               ack['sticky'], ack['notify'], ack['persistent'], ack['user']['_id'],
                               ack['comment'])
                else:
                    command = '[{}] ACKNOWLEDGE_HOST_PROBLEM;{};{};{};{};{};{}\n'. \
                        format(ack['_created'], ack['host']['name'], ack['sticky'], ack['notify'],
                               ack['persistent'], ack['user']['_id'], ack['comment'])
            elif ack['action'] == 'delete':
                if ack['service']:
                    command = '[{}] REMOVE_SVC_ACKNOWLEDGEMENT;{};{}\n'.\
                        format(ack['_created'], ack['host']['name'], ack['service']['name'])
                else:
                    command = '[{}] REMOVE_HOST_ACKNOWLEDGEMENT;{}\n'. \
                        format(ack['_created'], ack['host']['name'])

        logger.debug("[backend arbiter] command: %s", str(command))
        ext = ExternalCommand(command)
        self.from_q.put(ext)

    def get_downtime(self):
        """
        Get downtime from backend

        :return: None
        """
        all_downt = self.backend.get_all('actiondowntime',
                                         {'where': '{"processed": "False"}',
                                          'embedded': '{"host": 1, "service": 1, "trigger": 1, '
                                                      '"user": 1}'})
        for downt in all_downt['_items']:
            if downt['action'] == 'add':
                if downt['service']:
                    command = '[{}] SCHEDULE_SVC_DOWNTIME;{};{};{};{};{};{};{};{}\n'.\
                        format(downt['_created'], downt['host']['name'], downt['service']['name'],
                               downt['start_time'], downt['end_time'], downt['fixed'],
                               downt['trigger']['_id'], downt['duration'], downt['user']['_id'],
                               downt['comment'])
                else:
                    command = '[{}] SCHEDULE_HOST_DOWNTIME;{};{};{};{};{};{};{}\n'.\
                        format(downt['_created'], downt['host']['name'], downt['start_time'],
                               downt['end_time'], downt['fixed'], downt['trigger']['_id'],
                               downt['duration'], downt['user']['_id'], downt['comment'])
            elif downt['action'] == 'delete':
                if downt['service']:
                    command = '[{}] DEL_ALL_SVC_DOWNTIMES;{};{}\n'.\
                        format(downt['_created'], downt['host']['name'], downt['service']['name'])
                else:
                    command = '[{}] DEL_ALL_HOST_DOWNTIMES;{}\n'. \
                        format(downt['_created'], downt['host']['name'])

        logger.debug("[backend arbiter] command: %s", str(command))
        ext = ExternalCommand(command)
        self.from_q.put(ext)
