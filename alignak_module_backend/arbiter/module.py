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
# pylint: disable=F0401
from alignak.basemodule import BaseModule
# pylint: disable=F0401
from alignak.log import logger
from alignak_backend_client.client import Backend


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

        self.config = {'commands': [],
                       'timeperiods': [],
                       'hosts': [],
                       'hostgroups': [],
                       'services': [],
                       'contacts': []}

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

    @classmethod
    def single_relation(cls, resource, mapping):
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
        """
        if mapping in resource:
            if resource[mapping] is not None:
                if 'name' in resource[mapping]:
                    resource[mapping] = resource[mapping]['name']

    @classmethod
    def multiple_relation(cls, resource, mapping, mapping_name):
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
        :param mapping_name: key name of embedded data to use
        :type mapping_name: str
        """
        if mapping in resource:
            members = []
            for member in resource[mapping]:
                if mapping_name in member:
                    members.append(member[mapping_name])
                else:
                    members.append(member['name'])
            resource[mapping] = ','.join(members)

    @classmethod
    def clean_unusable_keys(cls, resource):
        """
        Delete keys of dictionary not used

        :param resource: dictionary got from alignak-backend
        :type resource: dict
        :return:
        """
        fields = ['_links', '_updated', '_created', '_etag', '_id', 'name', 'ui']
        for field in fields:
            if field in resource:
                del resource[field]

    @classmethod
    def convert_lists(cls, resource):
        for prop in resource:
            if isinstance(resource[prop], list):
                resource[prop] = ','.join(str(e) for e in resource[prop])
            elif isinstance(resource[prop], dict):
                logger.warning("=====> %s", prop)
                logger.warning(resource[prop])
    def get_commands(self):
        """
        Get commands from alignak_backend

        :return: None
        """
        all_commands = self.backend.get_all('command')
        logger.warning("[Alignak Backend Arbit] Got %d commands", len(all_commands))
        for command in all_commands:
            command['imported_from'] = 'alignakbackend'
            command['command_name'] = command['name']
            self.clean_unusable_keys(command)
            self.convert_lists(command)
            self.config['commands'].append(command)

    def get_contact(self):
        """
        Get contacts from alignak_backend

        :return: None
        """
        params = {'embedded': '{"contactgroups":1,"host_notification_period":1,'
                              '"service_notification_period":1,"host_notification_commands":1,'
                              '"service_notification_commands":1}'}
        self.backend.get_all('contact', params)
        all_contacts = self.backend.get_all('contact', params)
        for contact in all_contacts:
            contact['imported_from'] = 'alignakbackend'
            contact['contact_name'] = contact['name']

            # host_notification_period
            self.single_relation(contact, 'host_notification_period')
            # service_notification_period
            self.single_relation(contact, 'service_notification_period')
            # host_notification_commands
            self.multiple_relation(contact, 'host_notification_commands', 'contact')
            # service_notification_commands
            self.multiple_relation(contact, 'service_notification_commands', 'contact')
            # contactgroups
            self.multiple_relation(contact, 'contactgroups', 'contact')

            if 'host_notification_commands' not in contact:
                contact['host_notification_commands'] = ''
            if 'service_notification_commands' not in contact:
                contact['service_notification_commands'] = ''
            if 'host_notification_period' not in contact:
                contact['host_notification_period'] = self.config['timeperiods'][0]['timeperiod_name']
                contact['host_notifications_enabled'] = False
            if 'service_notification_period' not in contact:
                contact['service_notification_period'] = self.config['timeperiods'][0]['timeperiod_name']
                contact['service_notifications_enabled'] = False
            self.clean_unusable_keys(contact)
            self.convert_lists(contact)
            self.config['contacts'].append(contact)

    def get_hosts(self):
        """
        Get hosts from alignak_backend

        :return: None
        """
        params = {'embedded': '{"parents":1,"hostgroups":1,"check_command":1,'
                              '"contacts":1,"contact_groups":1,"escalations":1,"check_period":1,'
                              '"notification_period":1}'}
        all_hosts = self.backend.get_all('host', params)
        logger.warning("[Alignak Backend Arbit] Got %d hosts", len(all_hosts))
        for host in all_hosts:
            host['host_name'] = host['name']
            host['imported_from'] = 'alignakbackend'
            # check_command
            if 'check_command' in host:
                if host['check_command'] is None:
                    host['check_command'] = ''
                elif 'name' in host['check_command']:
                    host['check_command'] = host['check_command']['name']
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
            self.single_relation(host, 'check_period')
            # notification_period
            self.single_relation(host, 'notification_period')
            # parents
            self.multiple_relation(host, 'parents', 'host_name')
            # hostgroups
            self.multiple_relation(host, 'hostgroups', 'hostgroup_name')
            # contacts
            self.multiple_relation(host, 'contacts', 'contact_name')
            # contact_groups
            self.multiple_relation(host, 'contact_groups', 'contactgroup_name')
            # escalations
            self.multiple_relation(host, 'escalations', 'escalation_name')
            if 'realm' in host:
                if host['realm'] is None:
                    del host['realm']
            self.clean_unusable_keys(host)
            self.convert_lists(host)
            self.config['hosts'].append(host)

    def get_hostgroups(self):
        """
        Get hostgroups from alignak_backend

        :return: None
        """
        params = {'embedded': '{"hostgroup_members":1,"members":1}'}
        all_hostgroups = self.backend.get_all('hostgroup', params)
        logger.info("[Alignak Backend Arbit] Got %d hostgroups", len(all_hostgroups))
        for hostgroup in all_hostgroups:
            hostgroup['imported_from'] = 'alignakbackend'
            hostgroup['hostgroup_name'] = hostgroup['name']
            # members
            self.multiple_relation(hostgroup, 'members', 'host_name')
            # hostgroup_members
            self.multiple_relation(hostgroup, 'hostgroup_members', 'hostgroup_name')
            # realm
            if hostgroup['realm'] is None:
                del hostgroup['realm']

            self.clean_unusable_keys(hostgroup)
            self.convert_lists(hostgroup)
            self.config['hostgroups'].append(hostgroup)

    def get_services(self):
        """
        Get services from alignak_backend

        :return: None
        """
        params = {'embedded': '{"host_name":1,"servicegroups":1,"check_command":1,'
                              '"check_period":1,"notification_period":1,'
                              '"contacts":1,"contact_groups":1,"escalations":1,'
                              '"maintenance_period":1,"service_dependencies":1}'}
        all_services = self.backend.get_all('service', params)
        logger.warning("[Alignak Backend Arbit] Got %d services", len(all_services))
        for service in all_services:
            service['imported_from'] = 'alignakbackend'
            service['service_name'] = service['name']
            # check_command
            if 'check_command' in service:
                if service['check_command'] is None:
                    del service['check_command']
                elif 'command_name' in service['check_command']:
                    service['check_command'] = service['check_command']['command_name']
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
            self.single_relation(service, 'host_name')
            # check_period
            self.single_relation(service, 'check_period')
            # notification_period
            self.single_relation(service, 'notification_period')
            # maintenance_period
            self.single_relation(service, 'maintenance_period')
            # servicegroups
            self.multiple_relation(service, 'servicegroups', 'servicegroup_name')
            # contacts
            self.multiple_relation(service, 'contacts', 'contact_name')
            # contact_groups
            self.multiple_relation(service, 'contact_groups', 'contactgroup_name')
            # escalations
            self.multiple_relation(service, 'escalations', 'escalation_name')
            # service_dependencies
            self.multiple_relation(service, 'service_dependencies', 'service_name')

            self.clean_unusable_keys(service)
            self.convert_lists(service)
            self.config['services'].append(service)

    def get_timeperiods(self):
        """
        Get timeperiods from alignak_backend

        :return: None
        """
        params = {}
        all_timeperiods = self.backend.get_all('timeperiod', params)
        for timeperiod in all_timeperiods:
            timeperiod['imported_from'] = 'alignakbackend'
            timeperiod['timeperiod_name'] = timeperiod['name']
            for daterange in timeperiod['dateranges']:
                timeperiod.update(daterange)
            del timeperiod['dateranges']
            self.clean_unusable_keys(timeperiod)
            self.convert_lists(timeperiod)
            self.config['timeperiods'].append(timeperiod)

    def get_objects(self):
        """
        Get objects from alignak-backend

        :return: configuration objects
        :rtype: dict
        """

        self.get_commands()
        self.get_timeperiods()
        self.get_contact()
        self.get_hosts()
        self.get_hostgroups()
        self.get_services()

        return self.config
