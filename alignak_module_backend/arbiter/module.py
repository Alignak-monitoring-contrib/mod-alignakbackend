# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018: Alignak contrib team, see AUTHORS.txt file for contributors
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
import json
import logging
from datetime import datetime

from alignak.stats import Stats
from alignak.basemodule import BaseModule
from alignak.external_command import ExternalCommand

from alignak_backend_client.client import Backend, BackendException

# Set the backend client library log to ERROR level
logging.getLogger("alignak_backend_client.client").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name
for handler in logger.parent.handlers:
    if isinstance(handler, logging.StreamHandler):
        logger.parent.removeHandler(handler)

# pylint: disable=invalid-name
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

    def __init__(self, mod_conf):
        """Module initialization

        mod_conf is a dictionary that contains:
        - all the variables declared in the module configuration file
        - a 'properties' value that is the module properties as defined globally in this file

        :param mod_conf: module configuration file as a dictionary
        """
        BaseModule.__init__(self, mod_conf)

        # pylint: disable=global-statement
        global logger
        logger = logging.getLogger('alignak.module.%s' % self.alias)
        logger.setLevel(getattr(mod_conf, 'log_level', logging.INFO))

        logger.debug("inner properties: %s", self.__dict__)
        logger.debug("received configuration: %s", mod_conf.__dict__)

        self.my_arbiter = None

        # Alignak backend importation script is running
        self.backend_import = False
        if 'ALIGNAK_BACKEND_IMPORT_RUN' in os.environ and os.environ['ALIGNAK_BACKEND_IMPORT_RUN']:
            logger.info("Alignak backend importation script is active.")
            self.backend_import = True

        self.client_processes = int(getattr(mod_conf, 'client_processes', 1))
        logger.info("Number of processes used by backend client: %s", self.client_processes)

        logger.info("StatsD configuration: %s:%s, prefix: %s, enabled: %s",
                    getattr(mod_conf, 'statsd_host', 'localhost'),
                    int(getattr(mod_conf, 'statsd_port', '8125')),
                    getattr(mod_conf, 'statsd_prefix', 'alignak'),
                    (getattr(mod_conf, 'statsd_enabled', '0') != '0'))
        self.statsmgr = Stats()
        self.statsmgr.register(self.alias, 'module',
                               statsd_host=getattr(mod_conf, 'statsd_host', 'localhost'),
                               statsd_port=int(getattr(mod_conf, 'statsd_port', '8125')),
                               statsd_prefix=getattr(mod_conf, 'statsd_prefix', 'alignak'),
                               statsd_enabled=(getattr(mod_conf, 'statsd_enabled', '0') != '0'))

        self.url = getattr(mod_conf, 'api_url', 'http://localhost:5000')
        logger.info("Alignak backend endpoint: %s", self.url)
        self.backend = Backend(self.url, self.client_processes)
        self.backend.token = getattr(mod_conf, 'token', '')
        self.backend_connected = False
        self.backend_errors_count = 0
        self.backend_username = getattr(mod_conf, 'username', '')
        self.backend_password = getattr(mod_conf, 'password', '')
        self.backend_generate = getattr(mod_conf, 'allowgeneratetoken', False)

        self.backend_count = int(getattr(mod_conf, 'backend_count', '50'))
        logger.info("backend pagination count: %d items", self.backend_count)

        if not self.backend.token:
            logger.warning("no user token configured. "
                           "It is recommended to set a user token rather than a user login "
                           "in the configuration. Trying to get a token from the provided "
                           "user login information...")
            self.getToken()
        else:
            self.backend_connected = True

        self.bypass_verify_mode = int(getattr(mod_conf, 'bypass_verify_mode', 0)) == 1
        logger.info("bypass objects loading when Arbiter is in verify mode: %s",
                    self.bypass_verify_mode)

        self.verify_modification = int(getattr(mod_conf, 'verify_modification', 5))
        logger.info("configuration reload check period: %s minutes", self.verify_modification)

        self.action_check = int(getattr(mod_conf, 'action_check', 15))
        logger.info("actions check period: %s seconds", self.action_check)
        self.daemons_state = int(getattr(mod_conf, 'daemons_state', 60))
        logger.info("daemons state update period: %s seconds", self.daemons_state)
        self.retention_actived = int(getattr(mod_conf, 'retention_actived', 1))
        self.next_check = 0
        self.next_action_check = 0
        self.next_daemons_state = 0

        # Configuration load/reload
        self.backend_date_format = "%a, %d %b %Y %H:%M:%S GMT"
        self.time_loaded_conf = datetime.utcnow().strftime(self.backend_date_format)
        self.configuration_reload_required = False
        self.configuration_reload_changelog = []

        self.configraw = {}
        self.highlevelrealm = {
            'level': 30000,
            'name': ''
        }
        self.daemonlist = {'arbiter': {}, 'scheduler': {}, 'poller': {}, 'reactionner': {},
                           'receiver': {}, 'broker': {}}
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
        self.backend_nb_hosts = 0
        self.backend_nb_services = 0
        self.default_tp_always = None
        self.default_tp_never = None
        self.default_host_check_command = None
        self.default_service_check_command = None
        self.default_user = None

        self.alignak_configuration = {}

    # Common functions
    def do_loop_turn(self):
        """This function is called/used when you need a module with
        a loop function (and use the parameter 'external': True)
        """
        logger.info("In loop")
        time.sleep(1)

    def hook_read_configuration(self, arbiter):
        """Hook in arbiter used on configuration parsing start. This is useful to get our arbiter
        object and its parameters.

        :param arbiter: alignak.daemons.arbiterdaemon.Arbiter
        :type arbiter: object
        :return: None
        """
        self.my_arbiter = arbiter

    def getToken(self):
        """Authenticate and get the token

        :return: None
        """
        if self.backend_import:
            # Do no try to login when importing a configuration into the backend
            logger.info("Alignak backend importation script is active. "
                        "No backend connection.")
            return

        generate = 'enabled'
        if not self.backend_generate:
            generate = 'disabled'

        try:
            start = time.time()
            self.backend_connected = self.backend.login(self.backend_username,
                                                        self.backend_password,
                                                        generate)
            self.statsmgr.counter('backend-login', 1)
            self.statsmgr.timer('backend-login-time', time.time() - start)
            if not self.backend_connected:
                logger.warning("Backend login failed")
            self.token = self.backend.token
            self.backend_errors_count = 0
        except BackendException as exp:  # pragma: no cover - should not happen
            self.backend_connected = False
            self.backend_errors_count += 1
            logger.warning("Alignak backend is not available for login. "
                           "No backend connection, attempt: %d", self.backend_errors_count)
            logger.debug("Exception: %s", exp)

    def raise_backend_alert(self, errors_count=10):
        """Raise a backend alert

        :return: True if the backend is not connected and the error count
        is greater than a defined threshold
        """
        logger.debug("Check backend connection, connected: %s, errors count: %d",
                     self.backend_connected, self.backend_errors_count)
        if not self.backend_connected and self.backend_errors_count >= errors_count:
            return True

        return False

    def single_relation(self, resource, mapping, ctype):
        """Convert single embedded data to name of relation_data
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
        """Convert multiple embedded data to name of relation_data
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
        """Delete keys of dictionary not used

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
            # 'ls_acknowledged', 'ls_acknowledgement_type', 'ls_current_attempt', 'ls_attempt',
            # 'ls_downtimed', 'ls_execution_time',
            # 'ls_grafana', 'ls_grafana_panelid', 'ls_impact', 'ls_last_check', 'ls_last_state',
            # 'ls_last_state_changed', 'ls_last_hard_state_changed', 'ls_last_state_type',
            # 'ls_latency', 'ls_long_output',
            # 'ls_max_attempts', 'ls_next_check', 'ls_output', 'ls_perf_data',
            # 'ls_state', 'ls_state_id', 'ls_state_type',
            # 'ls_last_time_up', 'ls_last_time_down',
            # 'ls_last_time_ok', 'ls_last_time_warning', 'ls_last_time_critical',
            # 'ls_last_time_unknown', 'ls_last_time_unreachable',
            # 'ls_passive_check', 'ls_last_notification',
            '_overall_state_id',
            'trigger', 'schema_version'
        ]
        # Add live state fields
        for field in resource:
            if field.startswith('ls_'):
                fields.append(field)
        for field in fields:
            if field in resource:
                del resource[field]

    @classmethod
    def convert_lists(cls, resource):
        """Convert lists into string with values separated with comma

        :param resource: ressource
        :type resource: dict
        :return: None
        """
        for prop in resource:
            if isinstance(resource[prop], list):
                resource[prop] = ','.join(str(e) for e in resource[prop])
            # Is it really useful ... considered as not useful!
            # elif isinstance(resource[prop], dict):
            # logger.warning("=====> %s", prop)
            # logger.warning(resource[prop])

    def get_realms(self):
        """Get realms from alignak_backend

        :return: None
        """
        self.configraw['realms'] = {}
        self.configraw['realms_name'] = {}
        params = {"max_results": self.backend_count,
                  "embedded": json.dumps({'_children': 1})}
        all_realms = self.backend.get_all('realm', params)
        logger.info("Got %d realms",
                    len(all_realms['_items']))
        for realm in all_realms['_items']:
            logger.debug("- %s", realm['name'])
            self.configraw['realms'][realm['_id']] = realm['name']
            # we store the relation name => id because will use it for add / update alignak daemon
            # state in the backend
            self.configraw['realms_name'][realm['name']] = realm['_id']
            if realm['_level'] < self.highlevelrealm['level']:
                self.highlevelrealm['name'] = realm['name']
            realm['imported_from'] = 'alignak-backend'
            if 'definition_order' in realm and realm['definition_order'] == 100:
                realm['definition_order'] = 50
            realm['realm_name'] = realm['name']
            realm['realm_members'] = []
            for child in realm['_children']:
                realm['realm_members'].append(child['name'])
            self.clean_unusable_keys(realm)
            del realm['notes']
            del realm['alias']
            self.convert_lists(realm)

            logger.debug("- realm: %s", realm)
            self.config['realms'].append(realm)

        self.statsmgr.counter('objects.realm', len(self.config['realms']))

    def get_commands(self):
        """Get commands from alignak_backend

        :return: None
        """
        self.configraw['commands'] = {}
        params = {"max_results": self.backend_count}
        all_commands = self.backend.get_all('command', params)
        logger.info("Got %d commands",
                    len(all_commands['_items']))
        for command in all_commands['_items']:
            logger.debug("- %s", command['name'])
            self.configraw['commands'][command['_id']] = command['name']
            command['imported_from'] = 'alignak-backend'
            if 'definition_order' in command and command['definition_order'] == 100:
                command['definition_order'] = 50
            command['command_name'] = command['name']
            # poller_tag empty
            if 'poller_tag' in command and command['poller_tag'] == '':
                del command['poller_tag']
            self.clean_unusable_keys(command)
            del command['alias']
            del command['notes']
            self.convert_lists(command)

            # Set default host/service check commands
            if command['command_name'] == "_internal_host_up":
                self.default_host_check_command = command
            if command['command_name'] == "_echo":
                self.default_service_check_command = command

            logger.debug("- command: %s", command)
            self.config['commands'].append(command)

        self.statsmgr.counter('objects.command', len(self.config['commands']))

    def get_timeperiods(self):
        """Get timeperiods from alignak_backend

        :return: None
        """
        self.configraw['timeperiods'] = {}
        params = {"max_results": self.backend_count}
        all_timeperiods = self.backend.get_all('timeperiod', params)
        logger.info("Got %d timeperiods",
                    len(all_timeperiods['_items']))
        for timeperiod in all_timeperiods['_items']:
            logger.debug("- %s", timeperiod['name'])
            self.configraw['timeperiods'][timeperiod['_id']] = timeperiod['name']
            timeperiod['imported_from'] = 'alignak-backend'
            if 'definition_order' in timeperiod and timeperiod['definition_order'] == 100:
                timeperiod['definition_order'] = 50
            timeperiod['timeperiod_name'] = timeperiod['name']
            for daterange in timeperiod['dateranges']:
                timeperiod.update(daterange)
            del timeperiod['dateranges']
            self.clean_unusable_keys(timeperiod)
            del timeperiod['notes']
            self.convert_lists(timeperiod)

            # Set default timeperiod
            if timeperiod['timeperiod_name'] == "24x7":
                self.default_tp_always = timeperiod
            if timeperiod['timeperiod_name'] == "Never":
                self.default_tp_never = timeperiod

            logger.debug("- timeperiod: %s", timeperiod)
            self.config['timeperiods'].append(timeperiod)

        self.statsmgr.counter('objects.timeperiod', len(self.config['timeperiods']))

    def get_contactgroups(self):
        """Get contactgroups from alignak_backend

        :return: None
        """
        self.configraw['contactgroups'] = {}
        params = {"max_results": self.backend_count}
        all_contactgroups = self.backend.get_all('usergroup', params)
        logger.info("Got %d contactgroups",
                    len(all_contactgroups['_items']))
        for contactgroup in all_contactgroups['_items']:
            logger.debug("- %s", contactgroup['name'])
            self.configraw['contactgroups'][contactgroup['_id']] = contactgroup['name']

        for contactgroup in all_contactgroups['_items']:
            contactgroup['imported_from'] = 'alignak-backend'
            if 'definition_order' in contactgroup and contactgroup['definition_order'] == 100:
                contactgroup['definition_order'] = 50
            contactgroup['contactgroup_name'] = contactgroup['name']
            contactgroup['contactgroup_members'] = contactgroup['usergroups']
            contactgroup['members'] = contactgroup['users']
            # members
            self.multiple_relation(contactgroup, 'members', 'contacts')
            # contactgroup_members
            self.multiple_relation(contactgroup, 'contactgroup_members', 'contactgroups')
            self.clean_unusable_keys(contactgroup)
            del contactgroup['notes']
            self.convert_lists(contactgroup)

            logger.debug("- contacts group: %s", contactgroup)
            self.config['contactgroups'].append(contactgroup)

        self.statsmgr.counter('objects.contactgroup', len(self.config['contactgroups']))

    def get_contacts(self):
        """Get contacts from alignak_backend

        :return: None
        """
        self.configraw['contacts'] = {}
        params = {"max_results": self.backend_count,
                  "where": '{"_is_template": false}'}
        all_contacts = self.backend.get_all('user', params)
        logger.info("Got %d contacts",
                    len(all_contacts['_items']))
        for contact in all_contacts['_items']:
            logger.debug("- %s", contact['name'])
            self.configraw['contacts'][contact['_id']] = contact['name']
            contact['imported_from'] = 'alignak-backend'
            if 'definition_order' in contact and contact['definition_order'] == 100:
                contact['definition_order'] = 50
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

            # todo: perhaps those properties should have a default value in the backend?
            if 'host_notification_commands' not in contact:
                contact['host_notification_commands'] = ''
            if 'service_notification_commands' not in contact:
                contact['service_notification_commands'] = ''

            # todo: how should it be possible to not have those properties in the backend?
            # they are defined as required!
            if 'host_notification_period' not in contact:
                contact['host_notification_period'] = \
                    self.config['timeperiods'][0]['timeperiod_name']
                contact['host_notifications_enabled'] = False
            if 'service_notification_period' not in contact:
                contact['service_notification_period'] = \
                    self.config['timeperiods'][0]['timeperiod_name']
                contact['service_notifications_enabled'] = False

            for key, value in contact['customs'].items():
                if key[0] not in ['_']:
                    key = '_' + key
                contact[key.upper()] = value
            self.clean_unusable_keys(contact)
            del contact['notes']
            del contact['ui_preferences']
            del contact['can_update_livestate']
            del contact['skill_level']
            self.convert_lists(contact)

            # Set default user
            if contact['contact_name'] == "admin":
                self.default_user = contact

            logger.debug("- contact: %s", contact)
            self.config['contacts'].append(contact)

        self.statsmgr.counter('objects.contact', len(self.config['contacts']))

    def get_hostgroups(self):
        """Get hostgroups from alignak_backend

        :return: None
        """
        self.configraw['hostgroups'] = {}
        params = {"max_results": self.backend_count}
        all_hostgroups = self.backend.get_all('hostgroup', params)
        logger.info("Got %d hostgroups",
                    len(all_hostgroups['_items']))
        for hostgroup in all_hostgroups['_items']:
            logger.debug("- %s", hostgroup['name'])
            self.configraw['hostgroups'][hostgroup['_id']] = hostgroup['name']

        for hostgroup in all_hostgroups['_items']:
            self.configraw['hostgroups'][hostgroup['_id']] = hostgroup['name']
            hostgroup['imported_from'] = 'alignak-backend'
            if 'definition_order' in hostgroup and hostgroup['definition_order'] == 100:
                hostgroup['definition_order'] = 50
            hostgroup['hostgroup_name'] = hostgroup['name']
            hostgroup['hostgroup_members'] = hostgroup['hostgroups']
            hostgroup['members'] = hostgroup['hosts']
            # members
            self.multiple_relation(hostgroup, 'members', 'hosts')
            # hostgroup_members
            self.multiple_relation(hostgroup, 'hostgroup_members', 'hostgroups')
            self.clean_unusable_keys(hostgroup)
            self.convert_lists(hostgroup)

            logger.debug("- hosts group: %s", hostgroup)
            self.config['hostgroups'].append(hostgroup)

        self.statsmgr.counter('objects.hostgroup', len(self.config['hostgroups']))

    def get_hosts(self):
        """Get hosts from alignak_backend

        :return: None
        """
        self.configraw['hosts'] = {}
        params = {"max_results": self.backend_count,
                  "where": '{"_is_template": false}'}
        all_hosts = self.backend.get_all('host', params)
        logger.info("Got %d hosts", len(all_hosts['_items']))

        for host in all_hosts['_items']:
            logger.debug("- %s", host['name'])
            self.configraw['hosts'][host['_id']] = host['name']
            host['host_name'] = host['name']
            host['imported_from'] = 'alignak-backend'

            # If default backend definition order is set, set as default alignak one
            if 'definition_order' in host and host['definition_order'] == 100:
                host['definition_order'] = 50

            # Check command
            if 'check_command' in host:
                if host['check_command'] in self.configraw['commands']:
                    host['check_command'] = self.configraw['commands'][host['check_command']]
                else:
                    host['check_command'] = self.default_host_check_command['command_name']
            else:
                host['check_command'] = self.default_host_check_command['name']

            # event handler
            if 'event_handler' in host:
                if host['event_handler'] in self.configraw['commands']:
                    host['event_handler'] = self.configraw['commands'][host['event_handler']]
                else:
                    del host['event_handler']

            # snapshot command
            if 'snapshot_command' in host:
                if host['snapshot_command'] in self.configraw['commands']:
                    host['snapshot_command'] = self.configraw['commands'][host['snapshot_command']]
                else:
                    del host['snapshot_command']

            for command_arg in ['check_command', 'event_handler']:
                arg = command_arg + "_args"
                if arg in host:
                    if command_arg not in host:
                        host[command_arg] = ''
                    elif host[arg] != '':
                        host[command_arg] += '!'
                        host[command_arg] += host[arg]
                    del host[arg]
                    logger.debug("Host %s, %s: '%s'",
                                 host['name'], command_arg, host[command_arg])

            # poller and reactionner tags are empty - Alignak defaults to the string 'None'
            if not host['poller_tag']:
                host['poller_tag'] = 'None'
            if not host['reactionner_tag']:
                host['reactionner_tag'] = 'None'

            # Contacts
            host['contacts'] = host['users']
            host['contact_groups'] = host['usergroups']

            # notification period - set default as 24x7
            if 'notification_period' not in host or not host['notification_period']:
                host['notification_period'] = self.default_tp_always['timeperiod_name']
            # maintenance period - set default as Never
            if 'maintenance_period' not in host or not host['maintenance_period']:
                host['maintenance_period'] = self.default_tp_never['timeperiod_name']
            # snapshot period - set default as Never
            if 'snapshot_period' not in host or not host['snapshot_period']:
                host['snapshot_period'] = self.default_tp_never['timeperiod_name']

            # realm
            self.single_relation(host, '_realm', 'realms')
            host['realm'] = host['_realm']
            # check period
            self.single_relation(host, 'check_period', 'timeperiods')
            # notification_period
            self.single_relation(host, 'notification_period', 'timeperiods')
            # maintenance_period
            self.single_relation(host, 'maintenance_period', 'timeperiods')
            # snapshot_period
            self.single_relation(host, 'snapshot_period', 'timeperiods')
            # event_handler
            self.single_relation(host, 'event_handler', 'commands')

            # parents
            # todo: why is it always an empty list ???
            # ## self.multiple_relation(host, 'parents', 'host_name')
            host['parents'] = ''

            # hostgroups
            self.multiple_relation(host, 'hostgroup_name', 'hostgroups')
            # contacts
            self.multiple_relation(host, 'contacts', 'contacts')
            # contact_groups
            self.multiple_relation(host, 'contact_groups', 'contactgroups')
            # escalations
            # ## self.multiple_relation(host, 'escalations', 'escalation_name')
            if 'escalations' in host:
                del host['escalations']

            if 'alias' in host and host['alias'] == '':
                del host['alias']
            if 'realm' in host:
                if host['realm'] is None:
                    del host['realm']
            for key, value in host['customs'].items():
                if key[0] not in ['_']:
                    key = '_' + key
                host[key.upper()] = value

            # Fix #9: inconsistent state when no retention module exists
            if not self.retention_actived and 'ls_last_state' in host:
                if host['ls_state'] == 'UNREACHABLE':
                    host['initial_state'] = 'u'
                if host['ls_state'] == 'DOWN':
                    host['initial_state'] = 'd'
                if host['ls_state'] == 'UP':
                    host['initial_state'] = 'o'

                logger.debug(
                    "- host current live state is %s, "
                    "set initial_state as '%s'", host['ls_state'], host['initial_state']
                )
            self.clean_unusable_keys(host)
            self.convert_lists(host)

            logger.debug("- host: %s", host)
            self.config['hosts'].append(host)
        self.backend_nb_hosts = len(self.config['hosts'])

        self.statsmgr.counter('objects.host', len(self.config['hosts']))

    def get_servicegroups(self):
        """Get servicegroups from alignak_backend

        :return: None
        """
        self.configraw['servicegroups'] = {}
        params = {"max_results": self.backend_count}
        all_servicegroups = self.backend.get_all('servicegroup', params)
        logger.info("Got %d servicegroups",
                    len(all_servicegroups['_items']))
        for servicegroup in all_servicegroups['_items']:
            logger.debug("- %s", servicegroup['name'])
            self.configraw['servicegroups'][servicegroup['_id']] = servicegroup['name']

        for servicegroup in all_servicegroups['_items']:
            self.configraw['servicegroups'][servicegroup['_id']] = servicegroup['name']
            servicegroup['imported_from'] = 'alignak-backend'
            if 'definition_order' in servicegroup and servicegroup['definition_order'] == 100:
                servicegroup['definition_order'] = 50
            servicegroup['servicegroup_name'] = servicegroup['name']
            servicegroup['servicegroup_members'] = servicegroup['servicegroups']
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

            logger.debug("- services group: %s", servicegroup)
            self.config['servicegroups'].append(servicegroup)

        self.statsmgr.counter('objects.servicegroup', len(self.config['servicegroups']))

    def get_services(self):
        """Get services from alignak_backend

        :return: None
        """
        self.configraw['services'] = {}
        params = {"max_results": self.backend_count,
                  "where": '{"_is_template": false}'}
        all_services = self.backend.get_all('service', params)
        logger.info("Got %d services", len(all_services['_items']))

        for service in all_services['_items']:
            # Get host name from the previously loaded hosts list
            try:
                service['host_name'] = self.configraw['hosts'][service['host']]
            except KeyError:
                logger.warning("Got a service for an unknown host")
                continue
            logger.debug("- %s/%s", service['host_name'], service['name'])
            self.configraw['services'][service['_id']] = service['name']
            service['imported_from'] = 'alignak-backend'

            # If default backend definition order is set, set as default alignak one
            if 'definition_order' in service and service['definition_order'] == 100:
                service['definition_order'] = 50
            service['service_description'] = service['name']
            service['merge_host_contacts'] = service['merge_host_users']
            service['hostgroup_name'] = service['hostgroups']

            # Check command
            if 'check_command' in service:
                if service['check_command'] in self.configraw['commands']:
                    service['check_command'] = self.configraw['commands'][service['check_command']]
                else:
                    service['check_command'] = self.default_service_check_command['command_name']

            # event handler
            if 'event_handler' in service:
                if service['event_handler'] in self.configraw['commands']:
                    service['event_handler'] = self.configraw['commands'][service['event_handler']]
                else:
                    del service['event_handler']

            # snapshot command
            if 'snapshot_command' in service:
                if service['snapshot_command'] in self.configraw['commands']:
                    service['snapshot_command'] = \
                        self.configraw['commands'][service['snapshot_command']]
                else:
                    del service['snapshot_command']

            for command_arg in ['check_command', 'event_handler']:
                arg = command_arg + "_args"
                if arg in service:
                    if command_arg not in service:
                        service[command_arg] = ''
                    elif service[arg] != '':
                        service[command_arg] += '!'
                        service[command_arg] += service[arg]
                    del service[arg]
                logger.debug("Service %s, %s: '%s'",
                             service['name'], command_arg, service[command_arg])

            # poller and reactionner tags are empty - Alignak defaults to the string 'None'
            if not service['poller_tag']:
                service['poller_tag'] = 'None'
            if not service['reactionner_tag']:
                service['reactionner_tag'] = 'None'

            # Contacts
            service['contacts'] = service['users']
            service['contact_groups'] = service['usergroups']

            # notification period - set default as 24x7
            if 'notification_period' not in service or not service['notification_period']:
                service['notification_period'] = self.default_tp_always['timeperiod_name']
            # maintenance period - set default as Never
            if 'maintenance_period' not in service or not service['maintenance_period']:
                service['maintenance_period'] = self.default_tp_never['timeperiod_name']
            # snapshot period - set default as Never
            if 'snapshot_period' not in service or not service['snapshot_period']:
                service['snapshot_period'] = self.default_tp_never['timeperiod_name']

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
            # hostgroups
            self.multiple_relation(service, 'hostgroup_name', 'hostgroups')
            # servicegroups
            self.multiple_relation(service, 'servicegroups', 'servicegroups')
            # contacts
            self.multiple_relation(service, 'contacts', 'contacts')
            # contact_groups
            self.multiple_relation(service, 'contact_groups', 'contactgroups')
            # escalations
            # ## self.multiple_relation(service, 'escalations', 'escalation_name')
            if 'escalations' in service:
                del service['escalations']
            # service_dependencies
            # ## self.multiple_relation(service, 'service_dependencies', 'service_name')
            service['service_dependencies'] = ''

            if 'alias' in service and service['alias'] == '':
                del service['alias']
            for key, value in service['customs'].items():
                if key[0] not in ['_']:
                    key = '_' + key
                service[key.upper()] = value

            # Fix #9: inconsistent state when no retention module exists
            if not self.retention_actived and 'ls_last_state' in service:
                if service['ls_state'] == 'UNKNOWN':
                    service['initial_state'] = 'u'
                if service['ls_state'] == 'CRITICAL':
                    service['initial_state'] = 'c'
                if service['ls_state'] == 'WARNING':
                    service['initial_state'] = 'w'
                if service['ls_state'] == 'UP':
                    service['initial_state'] = 'o'

                logger.debug(
                    "- service current live state is %s, "
                    "set initial_state as '%s'", service['ls_state'], service['initial_state']
                )

            self.clean_unusable_keys(service)
            self.convert_lists(service)

            logger.debug("- service: %s", service)
            self.config['services'].append(service)
        self.backend_nb_services = len(self.config['services'])

        self.statsmgr.counter('objects.service', len(self.config['services']))

    def get_hostdependencies(self):
        """Get hostdependencies from alignak_backend

        :return: None
        """
        self.configraw['hostdependencies'] = {}
        params = {"max_results": self.backend_count}
        all_hostdependencies = self.backend.get_all('hostdependency', params)
        logger.info("Got %d hostdependencies",
                    len(all_hostdependencies['_items']))
        for hostdependency in all_hostdependencies['_items']:
            logger.debug("- %s", hostdependency['name'])
            self.configraw['hostdependencies'][hostdependency['_id']] = hostdependency['name']
            hostdependency['imported_from'] = 'alignak-backend'
            if 'definition_order' in hostdependency and hostdependency['definition_order'] == 100:
                hostdependency['definition_order'] = 50
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

            logger.debug("- hosts dependency: %s", hostdependency)
            self.config['hostdependencies'].append(hostdependency)

        self.statsmgr.counter('objects.hostdependency', len(self.config['hostdependencies']))

    def get_hostescalations(self):
        """Get hostescalations from alignak_backend

        :return: None
        """
        self.configraw['hostescalations'] = {}
        params = {"max_results": self.backend_count}
        all_hostescalations = self.backend.get_all('hostescalation', params)
        logger.info("Got %d hostescalations",
                    len(all_hostescalations['_items']))
        for hostescalation in all_hostescalations['_items']:
            logger.debug("- %s", hostescalation['name'])
            self.configraw['hostescalations'][hostescalation['_id']] = hostescalation['name']
            # hostescalation['hostescalation_name'] = hostescalation['name']
            hostescalation['imported_from'] = 'alignak-backend'
            if 'definition_order' in hostescalation and hostescalation['definition_order'] == 100:
                hostescalation['definition_order'] = 50
            hostescalation['contacts'] = []
            if 'users' in hostescalation:
                hostescalation['contacts'] = hostescalation['users']
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

            del hostescalation['notes']
            del hostescalation['alias']

            logger.debug("- host escalation: %s", hostescalation)
            self.config['hostescalations'].append(hostescalation)

        self.statsmgr.counter('objects.hostescalation', len(self.config['hostescalations']))

    def get_servicedependencies(self):
        """Get servicedependencies from alignak_backend

        :return: None
        """
        self.configraw['servicedependencies'] = {}
        params = {"max_results": self.backend_count}
        all_servicedependencies = self.backend.get_all('servicedependency', params)
        logger.info("Got %d servicedependencies",
                    len(all_servicedependencies['_items']))
        for servicedependency in all_servicedependencies['_items']:
            logger.debug("- %s", servicedependency['name'])
            self.configraw['servicedependencies'][servicedependency['_id']] = \
                servicedependency['name']
            servicedependency['imported_from'] = 'alignak-backend'
            if 'definition_order' in servicedependency and \
                    servicedependency['definition_order'] == 100:
                servicedependency['definition_order'] = 50
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

            logger.debug("- services dependency: %s", servicedependency)
            self.config['servicedependencies'].append(servicedependency)

        self.statsmgr.counter('objects.servicedependency', len(self.config['servicedependencies']))

    def get_serviceescalations(self):
        """Get serviceescalations from alignak_backend

        :return: None
        """
        self.configraw['serviceescalations'] = {}
        params = {"max_results": self.backend_count}
        all_serviceescalations = self.backend.get_all('serviceescalation', params)
        logger.info("Got %d serviceescalations",
                    len(all_serviceescalations['_items']))
        for serviceescalation in all_serviceescalations['_items']:
            logger.debug("- %s", serviceescalation['name'])
            self.configraw['serviceescalations'][serviceescalation['_id']] = \
                serviceescalation['name']
            # serviceescalation['serviceescalation_name'] = serviceescalation['name']
            serviceescalation['imported_from'] = 'alignak-backend'
            if 'definition_order' in serviceescalation and \
                    serviceescalation['definition_order'] == 100:
                serviceescalation['definition_order'] = 50
            serviceescalation['contacts'] = []
            if 'users' in serviceescalation:
                serviceescalation['contacts'] = serviceescalation['users']
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

            del serviceescalation['notes']
            del serviceescalation['alias']
            logger.debug("- service escalation: %s", serviceescalation)
            self.config['serviceescalations'].append(serviceescalation)

        self.statsmgr.counter('objects.serviceescalation', len(self.config['serviceescalations']))

    def get_alignak_configuration(self):
        """Get Alignak configuration from alignak-backend

        This function is an Arbiter hook called by the arbiter during its configuration loading.

        :return: alignak configuration parameters
        :rtype: dict
        """
        self.alignak_configuration = {}

        if not self.backend_connected:
            self.getToken()
            if self.raise_backend_alert(errors_count=1):
                logger.error("Alignak backend connection is not available. "
                             "Skipping Alignak configuration load and provide "
                             "an empty configuration to the Arbiter.")
                return self.alignak_configuration

        if self.my_arbiter and self.my_arbiter.verify_only:
            logger.info("My Arbiter is in verify only mode")
            if self.bypass_verify_mode:
                logger.info("Configured to bypass the objects loading. "
                            "Skipping Alignak configuration load and provide "
                            "the last read configuration to the Arbiter.")
                return self.alignak_configuration

        if self.backend_import:
            logger.info("Alignak backend importation script is active. "
                        "Provide the last read Alignak configuration to the Arbiter.")
            return self.alignak_configuration

        start_time = time.time()
        try:
            logger.info("Loading Alignak configuration...")
            self.alignak_configuration = {}
            params = {'sort': '_id'}
            if self.my_arbiter and self.my_arbiter.arbiter_name:
                params.update({'where': '{"name": "%s"}' % self.my_arbiter.arbiter_name})
            all_alignak = self.backend.get_all('alignak', params)
            logger.info("Got %d Alignak configurations", len(all_alignak['_items']))
            for alignak_cfg in all_alignak['_items']:
                logger.info("- %s", alignak_cfg['name'])

                self.alignak_configuration.update(alignak_cfg)

                logger.debug("- configuration: %s", alignak_cfg)
        except BackendException as exp:
            logger.warning("Alignak backend is not available for reading configuration. "
                           "Backend communication error.")
            logger.debug("Exception: %s", exp)
            self.backend_connected = False
            return self.alignak_configuration

        self.time_loaded_conf = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

        now = time.time()
        logger.info("Alignak configuration loaded in %s seconds", now - start_time)

        self.statsmgr.counter('objects.alignak', len(self.alignak_configuration))
        self.statsmgr.timer('objects-alignak-time', now - start_time)

        return self.alignak_configuration

    def get_objects(self):
        """Get objects from alignak-backend

        This function is an Arbiter hook called by the arbiter during its configuration loading.

        :return: configuration objects
        :rtype: dict
        """

        if not self.backend_connected:
            self.getToken()
            if self.raise_backend_alert(errors_count=1):
                logger.error("Alignak backend connection is not available. "
                             "Skipping objects load and provide an empty list to the Arbiter.")
                return self.config

        if self.my_arbiter and self.my_arbiter.verify_only:
            logger.info("my Arbiter is in verify only mode")
            if self.bypass_verify_mode:
                logger.info("Configured to bypass the objects loading. "
                            "Skipping objects load and provide an empty list to the Arbiter.")
                return self.config

        if self.backend_import:
            logger.info("Alignak backend importation script is active. "
                        "Provide an empty objects list to the Arbiter.")
            return self.config

        start_time = time.time()
        try:
            logger.info("Loading Alignak monitored system configuration...")
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
        except BackendException as exp:  # pragma: no cover - should not happen
            logger.warning("Alignak backend is not available for reading. "
                           "Backend communication error.")
            logger.exception("Exception: %s", exp)
            self.backend_connected = False

        self.time_loaded_conf = datetime.utcnow().strftime(self.backend_date_format)

        now = time.time()
        logger.info("Alignak monitored system configuration loaded in %s seconds", now - start_time)

        self.statsmgr.timer('objects-time', now - start_time)

        # Schedule next configuration reload check
        self.next_check = int(now) + (60 * self.verify_modification)
        self.next_action_check = int(now) + self.action_check
        self.next_daemons_state = int(now) + self.daemons_state

        if self.verify_modification:
            logger.info("next configuration reload check in %s seconds ---",
                        (self.next_check - int(now)))
        else:
            logger.info("no configuration reload check")
        if self.action_check:
            logger.info("next actions check in %s seconds ---",
                        (self.next_action_check - int(now)))
        else:
            logger.info("no actions check")
        if self.daemons_state:
            logger.info("next update daemons state in %s seconds ---",
                        (self.next_daemons_state - int(now)))
        else:
            logger.info("no daemons state update")
        return self.config

    def hook_tick(self, arbiter):
        # pylint: disable=too-many-nested-blocks
        """Hook in arbiter used to check if configuration has changed in the backend since
        last configuration loaded

        :param arbiter: alignak.daemons.arbiterdaemon.Arbiter
        :type arbiter: object
        :return: None
        """
        if not self.backend_connected:
            self.getToken()
            if self.raise_backend_alert(errors_count=10):
                logger.warning("Alignak backend connection is not available. "
                               "Periodical actions are disabled: configuration change checking, "
                               "ack/downtime/forced check, and daemons state updates.")
                return

        try:
            now = int(time.time())
            if self.verify_modification and now > self.next_check:
                logger.info("Check if system configuration changed in the backend...")
                logger.debug("Now is: %s", datetime.utcnow().strftime(self.backend_date_format))
                logger.debug("Last configuration loading time is: %s", self.time_loaded_conf)
                # todo: we should find a way to declare in the backend schema
                # that a resource endpoint is concerned with this feature. Something like:
                #   'arbiter_reload_check': True,
                #   'schema': {...}
                logger.debug("Check if system configuration changed in the backend...")
                resources = [
                    'realm', 'command', 'timeperiod',
                    'usergroup', 'user',
                    'hostgroup', 'host', 'hostdependency', 'hostescalation',
                    'servicegroup', 'service', 'servicedependency', 'serviceescalation'
                ]
                self.configuration_reload_required = False
                for resource in resources:
                    ret = self.backend.get(resource, {'where': '{"_updated":{"$gte": "%s"}}'
                                                               % self.time_loaded_conf})
                    if ret['_meta']['total'] > 0:
                        logger.info(" - backend updated resource: %s, count: %d",
                                    resource, ret['_meta']['total'])

                        self.statsmgr.counter('updated.%s' % resource, ret['_meta']['total'])

                        self.configuration_reload_required = True
                        for updated in ret['_items']:
                            logger.debug("  -> updated: %s", updated)
                            exists = [log for log in self.configuration_reload_changelog
                                      if log['resource'] == resource and
                                      log['item']['_id'] == updated['_id'] and
                                      log['item']['_updated'] == updated['_updated']]
                            if not exists:
                                self.configuration_reload_changelog.append({"resource": resource,
                                                                            "item": updated})

                # Test number of host and services in backend. The goal is to detect the resources
                # deleted
                # todo: this should also be checked for other resources!
                ret = self.backend.get('host', {"where": '{"_is_template": false}'})
                if ret['_meta']['total'] < self.backend_nb_hosts:
                    self.configuration_reload_required = True
                    self.configuration_reload_changelog.append({"resource": 'host',
                                                                "item": 'deleted'})
                ret = self.backend.get('service', {"where": '{"_is_template": false}'})
                if ret['_meta']['total'] < self.backend_nb_services:
                    self.configuration_reload_required = True
                    self.configuration_reload_changelog.append({"resource": 'service',
                                                                "item": 'deleted'})

                if self.configuration_reload_required:
                    self.statsmgr.counter('reload_required', 1)

                    logger.warning("Hey, we must reload configuration from the backend!")
                    try:
                        with open(arbiter.pidfile, 'r') as f:
                            arbiter_pid = f.readline()
                        os.kill(int(arbiter_pid), signal.SIGHUP)
                        message = "The configuration reload notification was " \
                                  "raised to the arbiter (pid=%s)." % arbiter_pid
                        self.configuration_reload_changelog.append({"resource": "backend-log",
                                                                    "item": {
                                                                        "_updated": now,
                                                                        "level": "INFO",
                                                                        "message": message
                                                                    }})
                        logger.info(message)
                    except Exception as exp:
                        message = "Problem with the arbiter pid file (%s). " \
                                  "Configuration reload notification was not raised." \
                                  % arbiter.pidfile
                        self.configuration_reload_changelog.append({"resource": "backend-log",
                                                                    "item": {
                                                                        "_updated": now,
                                                                        "level": "ERROR",
                                                                        "message": message
                                                                    }})
                        logger.error(message)
                else:
                    logger.debug("No changes found")
                self.next_check = now + (60 * self.verify_modification)
                logger.debug(
                    "next configuration reload check in %s seconds ---",
                    (self.next_check - now)
                )

            if self.action_check and now > self.next_action_check:
                logger.debug("Check if acknowledgements are required...")
                self.get_acknowledge(arbiter)
                logger.debug("Check if downtime scheduling are required...")
                self.get_downtime(arbiter)
                logger.debug("Check if re-checks are required...")
                self.get_forcecheck(arbiter)

                self.next_action_check = now + self.action_check
                logger.debug("next actions check in %s seconds ---",
                             (self.next_action_check - int(now)))

            if self.daemons_state and now > self.next_daemons_state:
                logger.debug("Update daemons state in the backend...")
                self.update_daemons_state(arbiter)

                self.next_daemons_state = now + self.daemons_state
                logger.debug(
                    "next update daemons state in %s seconds ---",
                    (self.next_daemons_state - int(now))
                )
        except Exception as exp:
            logger.warning("hook_tick exception: %s", str(exp))
            logger.debug("Exception: %s", exp)

    @staticmethod
    def convert_date_timestamp(mydate):
        """Convert date/time of backend into timestamp

        :param mydate: the date
        :type mydate: str
        :return: the timestamp
        :rtype: int
        """
        return int(time.mktime(datetime.strptime(mydate, "%a, %d %b %Y %H:%M:%S %Z").
                               timetuple()))

    def get_acknowledge(self, arbiter):
        """Get acknowledge from backend

        :return: None
        """
        if not self.backend_connected:
            return

        try:
            all_ack = self.backend.get_all('actionacknowledge',
                                           {'where': '{"processed": false}',
                                            'embedded': '{"host": 1, "service": 1, "user": 1}'})
        except BackendException as exp:  # pragma: no cover - should not happen
            logger.debug("Exception: %s", exp)
            return

        self.statsmgr.counter('action.acknowledge', len(all_ack['_items']))

        for ack in all_ack['_items']:
            sticky = 1
            if ack['sticky']:
                sticky = 2
            if ack['action'] == 'add':
                # ack['comment'] = ack['comment'].encode('utf8', 'replace')
                if ack['service']:
                    command = '[{}] ACKNOWLEDGE_SVC_PROBLEM;{};{};{};{};{};{};{}\n'.\
                        format(self.convert_date_timestamp(ack['_created']), ack['host']['name'],
                               ack['service']['name'], sticky, int(ack['notify']),
                               1, ack['user']['name'], ack['comment'])
                else:
                    command = '[{}] ACKNOWLEDGE_HOST_PROBLEM;{};{};{};{};{};{}\n'. \
                        format(self.convert_date_timestamp(ack['_created']), ack['host']['name'],
                               sticky, int(ack['notify']), 1, ack['user']['name'], ack['comment'])
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

            logger.info("build external command: %s", str(command))
            ext = ExternalCommand(command)
            arbiter.external_commands.append(ext)

    def get_downtime(self, arbiter):
        """Get downtime from backend

        :return: None
        """
        if not self.backend_connected:
            return

        all_downt = self.backend.get_all('actiondowntime',
                                         {'where': '{"processed": false}',
                                          'embedded': '{"host": 1, "service": 1, '
                                                      '"user": 1}'})

        self.statsmgr.counter('action.downtime', len(all_downt['_items']))

        # pylint: disable=too-many-format-args
        for downt in all_downt['_items']:
            if downt['action'] == 'add':
                # downt['comment'] = downt['comment'].encode('utf8', 'replace')
                if downt['service']:
                    command = '[{}] SCHEDULE_SVC_DOWNTIME;{};{};{};{};{};{};{};{};{}\n'.\
                        format(self.convert_date_timestamp(downt['_created']),
                               downt['host']['name'], downt['service']['name'],
                               downt['start_time'], downt['end_time'], int(downt['fixed']),
                               0, downt['duration'], downt['user']['name'], downt['comment'])
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

            logger.info("build external command: %s", str(command))
            ext = ExternalCommand(command)
            arbiter.external_commands.append(ext)

    def get_forcecheck(self, arbiter):
        """Get forcecheck from backend

        :return: None
        """
        if not self.backend_connected:
            return

        all_fcheck = self.backend.get_all('actionforcecheck',
                                          {'where': '{"processed": false}',
                                           'embedded': '{"host": 1, "service": 1}'})

        self.statsmgr.counter('action.force_check', len(all_fcheck['_items']))

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

            logger.info("build external command: %s", str(command))
            ext = ExternalCommand(command)
            arbiter.external_commands.append(ext)

    def update_daemons_state(self, arbiter):
        """Update the daemons status in the backend

        :param arbiter:
        :return:
        """
        if not self.backend_connected:
            return

        if not self.daemonlist['arbiter']:
            all_daemons = self.backend.get_all('alignakdaemon')
            for item in all_daemons['_items']:
                self.daemonlist[item['type']][item['name']] = item

        for s_type in ['arbiter', 'scheduler', 'poller', 'reactionner', 'receiver', 'broker']:
            for daemon in getattr(arbiter.conf, s_type + 's'):
                data = {'type': s_type}
                data['name'] = getattr(daemon, s_type + '_name')
                for field in ['address', 'port', 'alive', 'reachable', 'passive', 'spare']:
                    data[field] = getattr(daemon, field)
                data['last_check'] = int(getattr(daemon, 'last_check'))
                if s_type == 'arbiter' and data['last_check'] == 0 and data['reachable']:
                    data['last_check'] = int(time.time())
                if getattr(daemon, 'realm_name') == '':
                    # it's arbiter case not have realm refined
                    data['_realm'] = self.configraw['realms_name'][self.highlevelrealm['name']]
                    if len(self.configraw['realms']) == 1:
                        data['_sub_realm'] = False
                    else:
                        data['_sub_realm'] = True
                else:
                    data['_realm'] = self.configraw['realms_name'][getattr(daemon, 'realm_name')]
                    if hasattr(daemon, 'manage_sub_realms'):
                        data['_sub_realm'] = getattr(daemon, 'manage_sub_realms')

                if data['name'] in self.daemonlist[s_type]:
                    headers = {
                        'Content-Type': 'application/json',
                        'If-Match': self.daemonlist[s_type][data['name']]['_etag']
                    }
                    response = self.backend.patch(
                        'alignakdaemon/%s' % self.daemonlist[s_type][data['name']]['_id'],
                        data, headers, True)
                else:
                    response = self.backend.post('alignakdaemon', data)
                self.daemonlist[s_type][data['name']] = response
