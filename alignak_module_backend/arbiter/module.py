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
This module is used to get configuration from alignak-backend with arbiter
"""

import os
import signal
import time
import traceback
import logging
from datetime import datetime

from alignak.basemodule import BaseModule
from alignak.external_command import ExternalCommand

from alignak_backend_client.client import Backend, BackendException

logger = logging.getLogger('alignak.module')  # pylint: disable=C0103

# pylint: disable=C0103
properties = {
    'daemons': ['arbiter'],
    'type': 'backend_arbiter',
    'external': False,
    'phases': ['configuration'],
}


def get_instance(mod_conf):
    """
    Return a module instance for the modules manager

    :param mod_conf: the module properties as defined globally in this file
    :return:
    """
    logger.info("Give an instance of %s for alias: %s", mod_conf.python_name, mod_conf.module_alias)

    return AlignakBackendArbiter(mod_conf)


class AlignakBackendArbiter(BaseModule):
    # pylint: disable=too-many-public-methods
    """ This class is used to get configuration from alignak-backend
    """

    def __init__(self, modconf):
        BaseModule.__init__(self, modconf)

        self.my_arbiter = None

        # Alignak backend importation script is running
        self.backend_import = False
        if 'ALIGNAK_BACKEND_IMPORT_RUN' in os.environ and os.environ['ALIGNAK_BACKEND_IMPORT_RUN']:
            logger.info("[Backend Arbiter] Alignak backend importation script is active.")
            self.backend_import = True

        self.url = getattr(modconf, 'api_url', 'http://localhost:5000')
        self.backend = Backend(self.url)
        self.backend.token = getattr(modconf, 'token', '')
        self.backend_connected = False
        if self.backend.token == '':
            self.getToken(getattr(modconf, 'username', ''), getattr(modconf, 'password', ''),
                          getattr(modconf, 'allowgeneratetoken', False))
        self.bypass_verify_mode = int(getattr(modconf, 'bypass_verify_mode', 0)) == 1
        logger.info(
            "[Backend Arbiter] bypass objects loading when Arbiter is in verify mode: %s",
            self.bypass_verify_mode
        )
        self.verify_modification = int(getattr(modconf, 'verify_modification', 5))
        logger.info(
            "[Backend Arbiter] configuration reload check period: %s minutes",
            self.verify_modification
        )
        self.action_check = int(getattr(modconf, 'action_check', 15))
        logger.info(
            "[Backend Arbiter] actions check period: %s seconds", self.action_check
        )
        self.next_check = 0
        self.next_action_check = 0
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
                       'hostdependencies': [],
                       'hostescalations': [],
                       'servicedependencies': [],
                       'serviceescalations': [],
                       'triggers': []}

    # Common functions
    def do_loop_turn(self):
        """This function is called/used when you need a module with
        a loop function (and use the parameter 'external': True)
        """
        logger.info("[Backend Arbiter] In loop")
        time.sleep(1)

    def hook_read_configuration(self, arbiter):
        """
        Hook in arbiter used on configuration parsing start. This is useful to get our arbiter
        object and its parameters.

        :param arbiter: alignak.daemons.arbiterdaemon.Arbiter
        :type arbiter: object
        :return: None
        """
        self.my_arbiter = arbiter

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
        if self.backend_import:
            # Do no try to login when importing a configuration into the backend
            logger.info("[Backend Arbiter] Alignak backend importation script is active. "
                        "No backend connection.")
            return

        generate = 'enabled'
        if not generatetoken:
            generate = 'disabled'

        try:
            self.backend.login(username, password, generate)
            self.backend_connected = True
        except BackendException as e:
            logger.warning("[Backend Arbiter] Alignak backend is not available for login. "
                           "No backend connection.")
            logger.warning("[Backend Arbiter] Exception: %s", str(e))
            self.backend_connected = False

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
        fields = [
            '_links', '_updated', '_created', '_etag', '_id', 'name', 'ui', '_realm',
            '_sub_realm', '_users_read', '_users_update', '_users_delete', '_parent',
            '_tree_parents', '_all_children', '_level', 'customs', 'host', 'service',
            'back_role_super_admin', 'token', '_templates', '_template_fields', 'note',
            '_is_template', '_templates_with_services', '_templates_from_host_template',
            'merge_host_users', 'hosts_critical_threshold', 'hosts_warning_threshold',
            'services_critical_threshold', 'services_warning_threshold',
            'global_critical_threshold', 'global_warning_threshold', '_children',
            'hostgroups', 'hosts', 'dependent_hostgroups', 'dependent_hosts',
            'servicegroups', 'services', 'dependent_servicegroups', 'dependent_services',
            'usergroups', 'users',
            'location',
            'duplicate_foreach', 'tags',
            'ls_acknowledged', 'ls_current_attempt', 'ls_downtimed', 'ls_execution_time',
            'ls_grafana', 'ls_grafana_panelid', 'ls_impact', 'ls_last_check', 'ls_last_state',
            'ls_last_state_changed', 'ls_last_state_type', 'ls_latency', 'ls_long_output',
            'ls_max_attempts', 'ls_next_check', 'ls_output', 'ls_perf_data',
            'ls_state', 'ls_state_id', 'ls_state_type'
        ]
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
                resource[prop] = u','.join(str(e) for e in resource[prop])
            # Is it really useful ... considered as not useful!
            # elif isinstance(resource[prop], dict):
            # logger.warning("=====> %s", prop)
            # logger.warning(resource[prop])

    def get_realms(self):
        """
        Get realms from alignak_backend

        :return: None
        """
        self.configraw['realms'] = {}
        all_realms = self.backend.get_all('realm')
        logger.info("[Backend Arbiter] Got %d realms",
                    len(all_realms['_items']))
        for realm in all_realms['_items']:
            logger.info("[Backend Arbiter] - %s", realm['name'])
            self.configraw['realms'][realm['_id']] = realm['name']
            realm['imported_from'] = u'alignakbackend'
            realm['realm_name'] = realm['name']
            realm['realm_members'] = []
            self.clean_unusable_keys(realm)
            del realm['notes']
            del realm['alias']
            # self.convert_lists(realm)

            logger.debug("[Backend Arbiter] - realm: %s", realm)
            self.config['realms'].append(realm)

    def get_commands(self):
        """
        Get commands from alignak_backend

        :return: None
        """
        self.configraw['commands'] = {}
        all_commands = self.backend.get_all('command')
        logger.info("[Backend Arbiter] Got %d commands",
                    len(all_commands['_items']))
        for command in all_commands['_items']:
            logger.info("[Backend Arbiter] - %s", command['name'])
            self.configraw['commands'][command['_id']] = command['name']
            command['imported_from'] = u'alignakbackend'
            command['command_name'] = command['name']
            self.clean_unusable_keys(command)
            del command['alias']
            del command['notes']
            self.convert_lists(command)

            logger.debug("[Backend Arbiter] - command: %s", command)
            self.config['commands'].append(command)

    def get_timeperiods(self):
        """
        Get timeperiods from alignak_backend

        :return: None
        """
        self.configraw['timeperiods'] = {}
        all_timeperiods = self.backend.get_all('timeperiod')
        logger.info("[Backend Arbiter] Got %d timeperiods",
                    len(all_timeperiods['_items']))
        for timeperiod in all_timeperiods['_items']:
            logger.info("[Backend Arbiter] - %s", timeperiod['name'])
            self.configraw['timeperiods'][timeperiod['_id']] = timeperiod['name']
            timeperiod['imported_from'] = u'alignakbackend'
            timeperiod['timeperiod_name'] = timeperiod['name']
            for daterange in timeperiod['dateranges']:
                timeperiod.update(daterange)
            del timeperiod['dateranges']
            self.clean_unusable_keys(timeperiod)
            del timeperiod['notes']
            self.convert_lists(timeperiod)

            logger.debug("[Backend Arbiter] - timeperiod: %s", timeperiod)
            self.config['timeperiods'].append(timeperiod)

    def get_contactgroups(self):
        """
        Get contactgroups from alignak_backend

        :return: None
        """
        self.configraw['contactgroups'] = {}
        all_contactgroups = self.backend.get_all('usergroup')
        logger.info("[Backend Arbiter] Got %d contactgroups",
                    len(all_contactgroups['_items']))
        for contactgroup in all_contactgroups['_items']:
            logger.info("[Backend Arbiter] - %s", contactgroup['name'])
            self.configraw['contactgroups'][contactgroup['_id']] = contactgroup['name']

        for contactgroup in all_contactgroups['_items']:
            contactgroup[u'imported_from'] = u'alignakbackend'
            contactgroup[u'contactgroup_name'] = contactgroup['name']
            contactgroup[u'contactgroup_members'] = contactgroup['usergroups']
            contactgroup[u'members'] = contactgroup['users']
            # members
            self.multiple_relation(contactgroup, 'members', 'contacts')
            # contactgroup_members
            self.multiple_relation(contactgroup, 'contactgroup_members', 'contactgroups')
            self.clean_unusable_keys(contactgroup)
            del contactgroup['notes']
            self.convert_lists(contactgroup)

            logger.debug("[Backend Arbiter] - contacts group: %s", contactgroup)
            self.config['contactgroups'].append(contactgroup)

    def get_contacts(self):
        """
        Get contacts from alignak_backend

        :return: None
        """
        self.configraw['contacts'] = {}
        all_contacts = self.backend.get_all('user')
        logger.info("[Backend Arbiter] Got %d contacts",
                    len(all_contacts['_items']))
        for contact in all_contacts['_items']:
            logger.info("[Backend Arbiter] - %s", contact['name'])
            self.configraw['contacts'][contact['_id']] = contact['name']
            contact['imported_from'] = u'alignakbackend'
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
            del contact['notes']
            del contact['ui_preferences']
            self.convert_lists(contact)

            logger.debug("[Backend Arbiter] - contact: %s", contact)
            self.config['contacts'].append(contact)

    def get_hostgroups(self):
        """
        Get hostgroups from alignak_backend

        :return: None
        """
        self.configraw['hostgroups'] = {}
        all_hostgroups = self.backend.get_all('hostgroup')
        logger.info("[Backend Arbiter] Got %d hostgroups",
                    len(all_hostgroups['_items']))
        for hostgroup in all_hostgroups['_items']:
            logger.info("[Backend Arbiter] - %s", hostgroup['name'])
            self.configraw['hostgroups'][hostgroup['_id']] = hostgroup['name']

        for hostgroup in all_hostgroups['_items']:
            self.configraw['hostgroups'][hostgroup['_id']] = hostgroup['name']
            hostgroup[u'imported_from'] = u'alignakbackend'
            hostgroup[u'hostgroup_name'] = hostgroup['name']
            hostgroup[u'hostgroup_members'] = hostgroup['hostgroups']
            hostgroup[u'members'] = hostgroup['hosts']
            # members
            self.multiple_relation(hostgroup, 'members', 'hosts')
            # hostgroup_members
            self.multiple_relation(hostgroup, 'hostgroup_members', 'hostgroups')
            self.clean_unusable_keys(hostgroup)
            self.convert_lists(hostgroup)

            logger.debug("[Backend Arbiter] - hosts group: %s", hostgroup)
            self.config['hostgroups'].append(hostgroup)

    def get_hosts(self):
        """
        Get hosts from alignak_backend

        :return: None
        """
        self.configraw['hosts'] = {}
        all_hosts = self.backend.get_all('host', {"where": '{"_is_template": false}'})
        logger.info("[Backend Arbiter] Got %d hosts",
                    len(all_hosts['_items']))
        for host in all_hosts['_items']:
            logger.info("[Backend Arbiter] - %s", host['name'])
            self.configraw['hosts'][host['_id']] = host['name']
            host[u'host_name'] = host['name']
            host[u'imported_from'] = u'alignakbackend'
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
            host[u'contacts'] = []
            if 'users' in host:
                host[u'contacts'] = host['users']
            host[u'contact_groups'] = []
            if 'usergroups' in host:
                host[u'contact_groups'] = host['usergroups']
            # check_period
            self.single_relation(host, 'check_period', 'timeperiods')
            # realm
            self.single_relation(host, '_realm', 'realms')
            host['realm'] = host['_realm']
            # notification_period
            self.single_relation(host, 'notification_period', 'timeperiods')
            # maintenance_period
            self.single_relation(host, 'maintenance_period', 'timeperiods')
            # snapshot_period
            self.single_relation(host, 'snapshot_period', 'timeperiods')
            # event_handler
            self.single_relation(host, 'event_handler', 'commands')
            # parents
            # ## self.multiple_relation(host, 'parents', 'host_name')
            host[u'parents'] = ''
            # hostgroups
            self.multiple_relation(host, 'hostgroup_name', 'hostgroups')
            # contacts
            self.multiple_relation(host, 'contacts', 'contacts')
            # contact_groups
            self.multiple_relation(host, 'contact_groups', 'contactgroups')
            # escalations
            # ## self.multiple_relation(host, 'escalations', 'escalation_name')
            del host['escalations']
            if 'alias' in host and host['alias'] == '':
                del host['alias']
            if 'realm' in host:
                if host['realm'] is None:
                    del host['realm']
            for key, value in host['customs'].iteritems():
                host[key] = value
            # Fix #9: inconsistent state when no retention module exists
            if 'ls_last_state' in host:
                if host['ls_state'] == 'UNREACHABLE':
                    host['initial_state'] = 'u'
                if host['ls_state'] == 'DOWN':
                    host['initial_state'] = 'd'
                if host['ls_state'] == 'UP':
                    host['initial_state'] = 'o'

                logger.debug(
                    "[Backend Arbiter] - host current live state is %s, "
                    "set initial_state as '%s'", host['ls_state'], host['initial_state']
                )
            self.clean_unusable_keys(host)
            self.convert_lists(host)

            logger.debug("[Backend Arbiter] - host: %s", host)
            self.config['hosts'].append(host)

    def get_servicegroups(self):
        """
        Get servicegroups from alignak_backend

        :return: None
        """
        self.configraw['servicegroups'] = {}
        all_servicegroups = self.backend.get_all('servicegroup')
        logger.info("[Backend Arbiter] Got %d servicegroups",
                    len(all_servicegroups['_items']))
        for servicegroup in all_servicegroups['_items']:
            logger.info("[Backend Arbiter] - %s", servicegroup['name'])
            self.configraw['servicegroups'][servicegroup['_id']] = servicegroup['name']

        for servicegroup in all_servicegroups['_items']:
            self.configraw['servicegroups'][servicegroup['_id']] = servicegroup['name']
            servicegroup['imported_from'] = u'alignakbackend'
            servicegroup['servicegroup_name'] = servicegroup['name']
            servicegroup[u'servicegroup_members'] = servicegroup['servicegroups']
            # members
            members = []
            for service in servicegroup['services']:
                if service not in self.configraw['services']:
                    continue
                for svc in self.config['services']:
                    if self.configraw['services'][service] == svc['service_description']:
                        members.append("%s,%s" % (svc['host_name'], svc['service_description']))
            servicegroup['members'] = ','.join(members)
            # servicegroup_members
            self.multiple_relation(servicegroup, 'servicegroup_members', 'servicegroups')
            self.clean_unusable_keys(servicegroup)
            self.convert_lists(servicegroup)

            logger.debug("[Backend Arbiter] - services group: %s", servicegroup)
            self.config['servicegroups'].append(servicegroup)

    def get_services(self):
        """
        Get services from alignak_backend

        :return: None
        """
        self.configraw['services'] = {}
        params = {'embedded': '{"escalations":1,"service_dependencies":1}',
                  "where": '{"_is_template": false}'}
        all_services = self.backend.get_all('service', params)
        logger.info("[Backend Arbiter] Got %d services",
                    len(all_services['_items']))
        for service in all_services['_items']:
            logger.info("[Backend Arbiter] - %s", service['name'])
            self.configraw['services'][service['_id']] = service['name']
            service['imported_from'] = u'alignakbackend'
            service['service_description'] = service['name']
            service['host_name'] = service['host']
            service['merge_host_contacts'] = service['merge_host_users']
            service['hostgroup_name'] = service['hostgroups']
            service[u'contacts'] = []
            if 'users' in service:
                service[u'contacts'] = service['users']
            service[u'contact_groups'] = []
            if 'usergroups' in service:
                service[u'contact_groups'] = service['usergroups']
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
            # event_handler
            self.single_relation(service, 'event_handler', 'commands')
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
            # Fix #9: inconsistent state when no retention module exists
            if 'ls_last_state' in service:
                if service['ls_state'] == 'UNKNOWN':
                    service['initial_state'] = 'u'
                if service['ls_state'] == 'CRITICAL':
                    service['initial_state'] = 'c'
                if service['ls_state'] == 'WARNING':
                    service['initial_state'] = 'w'
                if service['ls_state'] == 'UP':
                    service['initial_state'] = 'o'

                logger.debug(
                    "[Backend Arbiter] - service current live state is %s, "
                    "set initial_state as '%s'", service['ls_state'], service['initial_state']
                )

            self.clean_unusable_keys(service)
            self.convert_lists(service)

            logger.debug("[Backend Arbiter] - service: %s", service)
            self.config['services'].append(service)

    def get_hostdependencies(self):
        """
        Get hostdependencies from alignak_backend

        :return: None
        """
        self.configraw['hostdependencies'] = {}
        all_hostdependencies = self.backend.get_all('hostdependency')
        logger.info("[Backend Arbiter] Got %d hostdependencies",
                    len(all_hostdependencies['_items']))
        for hostdependency in all_hostdependencies['_items']:
            logger.info("[Backend Arbiter] - %s", hostdependency['name'])
            self.configraw['hostdependencies'][hostdependency['_id']] = hostdependency['name']
            hostdependency['imported_from'] = u'alignakbackend'
            # Do not exist in Alignak
            # hostdependency['hostdependency_name'] = hostdependency['name']

            hostdependency['dependent_hostgroup_name'] = hostdependency['dependent_hostgroups']
            hostdependency['dependent_host_name'] = hostdependency['dependent_hosts']
            hostdependency['hostgroup_name'] = hostdependency['hostgroups']
            hostdependency['host_name'] = hostdependency['hosts']

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

            logger.debug("[Backend Arbiter] - hosts dependency: %s", hostdependency)
            self.config['hostdependencies'].append(hostdependency)

    def get_hostescalations(self):
        """
        Get hostescalations from alignak_backend

        :return: None
        """
        self.configraw['hostescalations'] = {}
        all_hostescalations = self.backend.get_all('hostescalation')
        logger.info("[Backend Arbiter] Got %d hostescalations",
                    len(all_hostescalations['_items']))
        for hostescalation in all_hostescalations['_items']:
            logger.info("[Backend Arbiter] - %s", hostescalation['name'])
            self.configraw['hostescalations'][hostescalation['_id']] = hostescalation['name']
            hostescalation['hostescalation_name'] = hostescalation['name']
            hostescalation['imported_from'] = u'alignakbackend'
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

            logger.debug("[Backend Arbiter] - host escalation: %s", hostescalation)
            self.config['hostescalations'].append(hostescalation)

    def get_servicedependencies(self):
        """
        Get servicedependencies from alignak_backend

        :return: None
        """
        self.configraw['servicedependencies'] = {}
        all_servicedependencies = self.backend.get_all('servicedependency')
        logger.info("[Backend Arbiter] Got %d servicedependencies",
                    len(all_servicedependencies['_items']))
        for servicedependency in all_servicedependencies['_items']:
            logger.info("[Backend Arbiter] - %s", servicedependency['name'])
            self.configraw['servicedependencies'][servicedependency['_id']] = \
                servicedependency['name']
            servicedependency['imported_from'] = u'alignakbackend'
            # Do not exist in Alignak
            # servicedependency['servicedependency_name'] = servicedependency['name']

            servicedependency['dependent_hostgroup_name'] = \
                servicedependency['dependent_hostgroups']
            servicedependency['dependent_host_name'] = \
                servicedependency['dependent_hosts']
            servicedependency['dependent_service_description'] = \
                servicedependency['dependent_services']
            servicedependency['hostgroup_name'] = servicedependency['hostgroups']
            servicedependency['host_name'] = servicedependency['hosts']
            servicedependency['service_description'] = servicedependency['services']

            # dependent_host_name
            self.multiple_relation(servicedependency, 'dependent_host_name', 'hosts')
            # dependent_hostgroup_name
            self.multiple_relation(servicedependency, 'dependent_hostgroup_name', 'hostgroups')
            # service_description
            self.multiple_relation(servicedependency, 'service_description', 'services')
            # dependent_service_description
            self.multiple_relation(servicedependency, 'dependent_service_description', 'services')
            # host_name
            self.multiple_relation(servicedependency, 'host_name', 'hosts')
            # hostgroup_name
            self.multiple_relation(servicedependency, 'hostgroup_name', 'hostgroups')
            self.clean_unusable_keys(servicedependency)
            self.convert_lists(servicedependency)

            if not servicedependency['hostgroup_name']:
                del servicedependency['hostgroup_name']
            if not servicedependency['dependent_hostgroup_name']:
                del servicedependency['dependent_hostgroup_name']

            logger.debug("[Backend Arbiter] - services dependency: %s", servicedependency)
            self.config['servicedependencies'].append(servicedependency)

    def get_serviceescalations(self):
        """
        Get serviceescalations from alignak_backend

        :return: None
        """
        self.configraw['serviceescalations'] = {}
        all_serviceescalations = self.backend.get_all('serviceescalation')
        logger.info("[Backend Arbiter] Got %d serviceescalations",
                    len(all_serviceescalations['_items']))
        for serviceescalation in all_serviceescalations['_items']:
            logger.info("[Backend Arbiter] - %s", serviceescalation['name'])
            self.configraw['serviceescalations'][serviceescalation['_id']] = \
                serviceescalation['name']
            serviceescalation['serviceescalation_name'] = serviceescalation['name']
            serviceescalation['imported_from'] = u'alignakbackend'
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

            logger.debug("[Backend Arbiter] - service escalation: %s", serviceescalation)
            self.config['serviceescalations'].append(serviceescalation)

    def get_objects(self):
        """
        Get objects from alignak-backend

        :return: configuration objects
        :rtype: dict
        """
        if not self.backend_connected:
            logger.error("[Backend Arbiter] Alignak backend connection is not available. "
                         "Skipping objects load and provide an empty list to the Arbiter.")
            return self.config

        if self.my_arbiter and self.my_arbiter.verify_only:
            logger.info("[Backend Arbiter] my Arbiter is in verify only mode")
            if self.bypass_verify_mode:
                logger.info("[Backend Arbiter] configured to bypass the objects loading. "
                            "Skipping objects load and provide an empty list to the Arbiter.")
                return self.config

        if self.backend_import:
            logger.info("[Backend Arbiter] Alignak backend importation script is active. "
                        "Provide an empty objects list to the Arbiter.")
            return self.config

        start_time = time.time()
        try:
            self.get_realms()
            self.get_commands()
            self.get_timeperiods()
            self.get_contacts()
            self.get_contactgroups()
            self.get_hosts()
            self.get_hostgroups()
            self.get_services()
            self.get_servicegroups()
            self.get_hostdependencies()
            self.get_hostescalations()
            self.get_servicedependencies()
            self.get_serviceescalations()
        except BackendException as e:
            logger.warning("[Backend Arbiter] Alignak backend is not available for reading. "
                           "Backend communication error.")
            logger.warning("[Backend Arbiter] Exception: %s", str(e))
            self.backend_connected = False

        self.time_loaded_conf = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

        now = time.time()
        logger.info(
            "[Backend Arbiter] backend configuration loaded in %s seconds",
            (now - start_time)
        )

        # Schedule next configuration reload check in 10 minutes (need time to finish load config)
        self.next_check = int(now) + (60 * self.verify_modification)
        self.next_action_check = int(now) + self.action_check

        logger.info(
            "[Backend Arbiter] next configuration reload check in %s seconds ---",
            (self.next_check - int(now))
        )
        logger.info(
            "[Backend Arbiter] next actions check in %s seconds ---",
            (self.next_action_check - int(now))
        )
        return self.config

    def hook_tick(self, arbiter):
        """
        Hook in arbiter used to check if configuration has changed in the backend since
        last configuration loaded

        :param arbiter: alignak.daemons.arbiterdaemon.Arbiter
        :type arbiter: object
        :return: None
        """
        try:
            now = int(time.time())
            if now > self.next_check:
                logger.info(
                    "[Backend Arbiter] Check if system configuration changed in the backend..."
                )
                resources = [
                    'realm', 'command', 'timeperiod',
                    'usergroup', 'user',
                    'hostgroup', 'host', 'hostdependency', 'hostescalation',
                    'servicegroup', 'service', 'servicedependency', 'serviceescalation'
                ]
                reload_conf = False
                for resource in resources:
                    ret = self.backend.get(resource, {'where': '{"_updated":{"$gte": "' +
                                                               self.time_loaded_conf + '"}}'})
                    logger.info(
                        " - backend updated resource: %s, count: %d",
                        resource, ret['_meta']['total']
                    )
                    if ret['_meta']['total'] > 0:
                        reload_conf = True
                if reload_conf:
                    logger.warning(
                        "[Backend Arbiter] Hey, we must reload configuration from the backend!"
                    )
                    with open(arbiter.pidfile, 'r') as f:
                        arbiterpid = f.readline()
                    os.kill(int(arbiterpid), signal.SIGHUP)
                self.next_check = now + (60 * self.verify_modification)
                logger.debug(
                    "[Backend Arbiter] next configuration reload check in %s seconds ---",
                    (self.next_check - now)
                )

            if now > self.next_action_check:
                logger.debug("Check if acknowledgements are required...")
                self.get_acknowledge(arbiter)
                logger.debug("Check if downtime scheduling are required...")
                self.get_downtime(arbiter)
                logger.debug("Check if re-checks are required...")
                self.get_forcecheck(arbiter)

                self.next_action_check = now + self.action_check
                logger.debug(
                    "[Backend Arbiter] next actions check in %s seconds ---",
                    (self.next_action_check - int(now))
                )
        except Exception as exp:
            logger.warning("[Backend Arbiter] hook_tick exception: %s", str(exp))
            logger.warning("[Backend Arbiter] traceback: %s", traceback.format_exc())

    @staticmethod
    def convert_date_timestamp(mydate):
        """
        Convert date/time of backend into timestamp

        :param mydate: the date
        :type mydate: str
        :return: the timestamp
        :rtype: int
        """
        return int(time.mktime(datetime.strptime(mydate, "%a, %d %b %Y %H:%M:%S %Z").
                               timetuple()))

    def get_acknowledge(self, arbiter):
        """
        Get acknowledge from backend

        :return: None
        """
        all_ack = self.backend.get_all('actionacknowledge',
                                       {'where': '{"processed": false}',
                                        'embedded': '{"host": 1, "service": 1, "user": 1}'})
        for ack in all_ack['_items']:
            sticky = 1
            if ack['sticky']:
                sticky = 2
            if ack['action'] == 'add':
                if ack['service']:
                    command = '[{}] ACKNOWLEDGE_SVC_PROBLEM;{};{};{};{};{};{};{}\n'.\
                        format(self.convert_date_timestamp(ack['_created']), ack['host']['name'],
                               ack['service']['name'], sticky, int(ack['notify']),
                               int(ack['persistent']), ack['user']['name'], ack['comment'])
                else:
                    # logger.warning(time.time())
                    # logger.warning(self.convert_date_timestamp(ack['_created']))
                    command = '[{}] ACKNOWLEDGE_HOST_PROBLEM;{};{};{};{};{};{}\n'. \
                        format(self.convert_date_timestamp(ack['_created']), ack['host']['name'],
                               sticky, int(ack['notify']), int(ack['persistent']),
                               ack['user']['name'], ack['comment'])
            elif ack['action'] == 'delete':
                if ack['service']:
                    command = '[{}] REMOVE_SVC_ACKNOWLEDGEMENT;{};{}\n'.\
                        format(self.convert_date_timestamp(ack['_created']), ack['host']['name'],
                               ack['service']['name'])
                else:
                    command = '[{}] REMOVE_HOST_ACKNOWLEDGEMENT;{}\n'. \
                        format(self.convert_date_timestamp(ack['_created']), ack['host']['name'])

            headers = {'Content-Type': 'application/json', 'If-Match': ack['_etag']}
            data = {'processed': True}
            self.backend.patch('actionacknowledge/' + ack['_id'], data, headers)

            logger.info("[Backend Arbiter] build external command: %s", str(command))
            ext = ExternalCommand(command)
            arbiter.external_commands.append(ext)

    def get_downtime(self, arbiter):
        """
        Get downtime from backend

        :return: None
        """
        all_downt = self.backend.get_all('actiondowntime',
                                         {'where': '{"processed": false}',
                                          'embedded': '{"host": 1, "service": 1, '
                                                      '"user": 1}'})
        # pylint: disable=too-many-format-args
        for downt in all_downt['_items']:
            if downt['action'] == 'add':
                if downt['service']:
                    command = '[{}] SCHEDULE_SVC_DOWNTIME;{};{};{};{};{};{};{};{};{}\n'.\
                        format(self.convert_date_timestamp(downt['_created']),
                               downt['host']['name'], downt['service']['name'],
                               downt['start_time'], downt['end_time'], int(downt['fixed']),
                               0, downt['duration'], downt['user']['name'],
                               downt['comment'])
                elif downt['host'] and 'name' in downt['host']:
                    command = '[{}] SCHEDULE_HOST_DOWNTIME;{};{};{};{};{};{};{};{}\n'.\
                        format(self.convert_date_timestamp(downt['_created']),
                               downt['host']['name'], downt['start_time'], downt['end_time'],
                               int(downt['fixed']), 0, downt['duration'],
                               downt['user']['name'], downt['comment'])
            elif downt['action'] == 'delete':
                if downt['service']:
                    command = '[{}] DEL_ALL_SVC_DOWNTIMES;{};{}\n'.\
                        format(self.convert_date_timestamp(downt['_created']),
                               downt['host']['name'], downt['service']['name'])
                else:
                    command = '[{}] DEL_ALL_HOST_DOWNTIMES;{}\n'. \
                        format(self.convert_date_timestamp(downt['_created']),
                               downt['host']['name'])

            headers = {'Content-Type': 'application/json', 'If-Match': downt['_etag']}
            data = {'processed': True}
            self.backend.patch('actiondowntime/' + downt['_id'], data, headers)

            logger.info("[Backend Arbiter] build external command: %s", str(command))
            ext = ExternalCommand(command)
            arbiter.external_commands.append(ext)

    def get_forcecheck(self, arbiter):
        """
        Get forcecheck from backend

        :return: None
        """
        all_fcheck = self.backend.get_all('actionforcecheck',
                                          {'where': '{"processed": false}',
                                           'embedded': '{"host": 1, "service": 1}'})
        for fcheck in all_fcheck['_items']:
            timestamp = self.convert_date_timestamp(fcheck['_created'])
            if fcheck['service']:
                command = '[{}] SCHEDULE_FORCED_SVC_CHECK;{};{};{}\n'.\
                    format(timestamp, fcheck['host']['name'], fcheck['service']['name'], timestamp)
            else:
                command = '[{}] SCHEDULE_FORCED_HOST_CHECK;{};{}\n'.\
                    format(timestamp, fcheck['host']['name'], timestamp)

            headers = {'Content-Type': 'application/json', 'If-Match': fcheck['_etag']}
            data = {'processed': True}
            self.backend.patch('actionforcecheck/' + fcheck['_id'], data, headers)

            logger.info("[Backend Arbiter] build external command: %s", str(command))
            ext = ExternalCommand(command)
            arbiter.external_commands.append(ext)

        logger.info("stopping...")
        logger.info("stopped")
