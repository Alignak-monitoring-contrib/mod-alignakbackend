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
This module is used to send logs and livestate to alignak-backend with broker
"""

import time
import json
import Queue
import logging

from alignak.basemodule import BaseModule
from alignak_backend_client.client import Backend, BackendException

logger = logging.getLogger('alignak.module')  # pylint: disable=invalid-name

# pylint: disable=C0103
properties = {
    'daemons': ['broker'],
    'type': 'backend_broker',
    'external': True,
}


def get_instance(mod_conf):
    """
    Return a module instance for the modules manager

    :param mod_conf: the module properties as defined globally in this file
    :return:
    """
    logger.info("Give an instance of %s for alias: %s", mod_conf.python_name, mod_conf.module_alias)

    return AlignakBackendBroker(mod_conf)


class AlignakBackendBroker(BaseModule):
    """ This class is used to send logs and livestate to alignak-backend
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

        logger.debug("inner properties: %s", self.__dict__)
        logger.debug("received configuration: %s", mod_conf.__dict__)

        self.client_processes = int(getattr(mod_conf, 'client_processes', 1))
        logger.info("Number of processes used by backend client: %s", self.client_processes)

        self.default_realm = None

        self.url = getattr(mod_conf, 'api_url', 'http://localhost:5000')
        self.backend = Backend(self.url, self.client_processes)
        self.backend.token = getattr(mod_conf, 'token', '')
        self.backend_connected = False
        self.backend_errors_count = 0
        self.backend_username = getattr(mod_conf, 'username', '')
        self.backend_password = getattr(mod_conf, 'password', '')
        self.backend_generate = getattr(mod_conf, 'allowgeneratetoken', False)

        if not self.backend.token:
            logger.warning("no user token configured. "
                           "It is recommended to set a user token rather than a user login "
                           "in the configuration. Trying to get a token from the provided "
                           "user login information...")
            self.getToken()
        else:
            self.backend_connected = True

        self.logged_in = self.backendConnection()

        self.ref_live = {
            'host': {},
            'service': {},
            'user': {}
        }
        self.mapping = {
            'host': {},
            'service': {},
            'user': {}
        }

        # Objects reference
        self.load_protect_delay = int(getattr(mod_conf, 'load_protect_delay', '300'))
        self.loaded_hosts = 0
        self.loaded_services = 0
        self.loaded_users = 0

    # Common functions
    def do_loop_turn(self):
        """This function is called/used when you need a module with
        a loop function (and use the parameter 'external': True)

        Note: We are obliged to define this method (even if not called!) because
        it is an abstract function in the base class
        """
        logger.info("In loop")
        time.sleep(1)

    def getToken(self):
        """Authenticate and get the token

        :return: None
        """
        generate = 'enabled'
        if not self.backend_generate:
            generate = 'disabled'

        try:
            self.backend_connected = self.backend.login(self.backend_username,
                                                        self.backend_password,
                                                        generate)
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

    def backendConnection(self, default_realm='All'):
        """Backend connection to check live state update is allowed

        :return: True/False
        """
        if not self.backend_connected:
            self.getToken()
            if self.raise_backend_alert(errors_count=1):
                logger.error("Alignak backend connection is not available. "
                             "Checking if livestate update is allowed is not possible.")
                return False

        if not self.backend_connected:
            return False

        if not self.default_realm:
            try:
                params = {'where': '{"name":"%s"}' % default_realm}
                realms = self.backend.get('realm', params=params)
                for realm in realms['_items']:
                    self.default_realm = realm['_id']
            except BackendException:
                self.backend_connected = False
                self.backend_errors_count += 1
                logger.warning("Alignak backend connection fails. Check and fix your configuration")
                return False

        params = {'where': '{"token":"%s"}' % self.backend.token}
        users = self.backend.get('user', params)
        for item in users['_items']:
            return item['can_update_livestate']

        logger.error("Configured user account is not allowed for this module")
        return False

    def get_refs(self, type_data):
        """
        Get the _id in the backend for hosts, services and users

        :param type_data: livestate type to get: livestate_host, livestate_service, livestate_user
        :type type_data: str
        :return: None
        """
        now = int(time.time())
        if type_data == 'livestate_host' \
                and self.loaded_hosts < now - self.load_protect_delay:
            params = {
                'projection': '{"name":1,"ls_state":1,"ls_state_type":1,"_realm":1}',
                'where': '{"_is_template":false}'
            }
            content = self.backend.get_all('host', params)
            for item in content['_items']:
                self.mapping['host'][item['name']] = item['_id']

                self.ref_live['host'][item['_id']] = {
                    '_id': item['_id'],
                    '_etag': item['_etag'],
                    '_realm': item['_realm'],
                    'initial_state': item['ls_state'],
                    'initial_state_type': item['ls_state_type']
                }
            self.loaded_hosts = now
        elif type_data == 'livestate_service' \
                and self.loaded_services < now - self.load_protect_delay:
            params = {
                'projection': '{"name":1}',
                'where': '{"_is_template":false}'
            }
            contenth = self.backend.get_all('host', params)
            hosts = {}
            for item in contenth['_items']:
                hosts[item['_id']] = item['name']

            params = {
                'projection': '{"host":1,"name":1,"ls_state":1,"ls_state_type":1,"_realm":1}',
                'where': '{"_is_template":false}'
            }
            content = self.backend.get_all('service', params)
            for item in content['_items']:
                self.mapping['service']['__'.join([hosts[item['host']],
                                                   item['name']])] = item['_id']

                self.ref_live['service'][item['_id']] = {
                    '_id': item['_id'],
                    '_etag': item['_etag'],
                    '_realm': item['_realm'],
                    'initial_state': item['ls_state'],
                    'initial_state_type': item['ls_state_type']
                }
            self.loaded_services = now
        elif type_data == 'livestate_user' \
                and self.loaded_users < now - self.load_protect_delay:
            params = {
                'projection': '{"name":1,"_realm":1}',
                'where': '{"_is_template":false}'
            }
            content = self.backend.get_all('user', params)
            for item in content['_items']:
                self.mapping['user'][item['name']] = item['_id']

                self.ref_live['user'][item['_id']] = {
                    '_id': item['_id'],
                    '_etag': item['_etag'],
                    '_realm': item['_realm']
                }
            self.loaded_users = now

    def update_next_check(self, data, obj_type):
        """Update livestate host and service next check timestamp

        {'instance_id': u'475dc864674943b4aa4cbc966f7cc737', u'service_description': u'nsca_disk',
        u'next_chk': 0, u'in_checking': True, u'host_name': u'ek3022fdj-00011'}

        :param data: dictionary of data from scheduler
        :type data: dict
        :param obj_type: type of data (host | service)
        :type obj_type: str
        :return: Counters of updated or add data to alignak backend
        :rtype: dict
        """
        start_time = time.time()
        counters = {
            'livestate_host': 0,
            'livestate_service': 0,
            'log_host': 0,
            'log_service': 0
        }
        logger.debug("Update next check: %s, %s", obj_type, data)

        if obj_type == 'host':
            if data['host_name'] in self.mapping['host']:
                # Received data for an host:
                data_to_update = {
                    'ls_next_check': data['next_chk']
                }

                # Update live state
                ret = self.send_to_backend('livestate_host', data['host_name'], data_to_update)
                if ret:
                    counters['livestate_host'] += 1
                logger.debug("Updated host live state data: %s", data_to_update)
        elif obj_type == 'service':
            service_name = '__'.join([data['host_name'], data['service_description']])
            if service_name in self.mapping['service']:
                # Received data for a service:
                data_to_update = {
                    'ls_next_check': data['next_chk']
                }

                # Update live state
                ret = self.send_to_backend('livestate_service', service_name, data_to_update)
                if ret:
                    counters['livestate_service'] += 1
                logger.debug("Updated service live state data: %s", data_to_update)
        if (counters['livestate_host'] + counters['livestate_service']) > 0:
            logger.debug("--- %s seconds ---", (time.time() - start_time))
        return counters

    def update_livestate(self, data, obj_type):
        """
        Update livestate_host and livestate_service

        :param data: dictionary of data from scheduler
        :type data: dict
        :param obj_type: type of data (host | service)
        :type obj_type: str
        :return: Counters of updated or add data to alignak backend
        :rtype: dict
        """
        start_time = time.time()
        counters = {
            'livestate_host': 0,
            'livestate_service': 0,
            'log_host': 0,
            'log_service': 0
        }
        logger.debug("Update livestate: %s - %s", obj_type, data)

        if obj_type == 'host':
            if data['host_name'] in self.mapping['host']:
                # Received data for an host:
                data_to_update = {
                    'ls_state': data['state'],
                    'ls_state_id': data['state_id'],
                    'ls_state_type': data['state_type'],
                    'ls_last_check': data['last_chk'],
                    'ls_last_state': data['last_state'],
                    'ls_last_state_type': data['last_state_type'],
                    'ls_last_state_changed': data['last_state_change'],
                    'ls_output': data['output'],
                    'ls_long_output': data['long_output'],
                    'ls_perf_data': data['perf_data'],
                    'ls_acknowledged': data['problem_has_been_acknowledged'],
                    'ls_acknowledgement_type': data['acknowledgement_type'],
                    'ls_downtimed': data['in_scheduled_downtime'],
                    'ls_execution_time': data['execution_time'],
                    'ls_latency': data['latency'],

                    # 'ls_passive_check': data['passive_check'],
                    'ls_attempt': data['attempt'],
                    'ls_last_hard_state_changed': data['last_hard_state_change'],
                    # Last time in the corresponding state
                    'ls_last_time_up': data['last_time_up'],
                    'ls_last_time_down': data['last_time_down'],
                    'ls_last_time_unknown': 0,
                    'ls_last_time_unreachable': data['last_time_unreachable']
                }

                h_id = self.mapping['host'][data['host_name']]
                if 'initial_state' in self.ref_live['host'][h_id]:
                    data_to_update['ls_last_state'] = \
                        self.ref_live['host'][h_id]['initial_state']
                    data_to_update['ls_last_state_type'] = \
                        self.ref_live['host'][h_id]['initial_state_type']
                    del self.ref_live['host'][h_id]['initial_state']
                    del self.ref_live['host'][h_id]['initial_state_type']

                data_to_update['_realm'] = self.ref_live['host'][h_id]['_realm']

                # Update live state
                ret = self.send_to_backend('livestate_host', data['host_name'], data_to_update)
                if ret:
                    counters['livestate_host'] += 1
                logger.debug("Updated host live state data: %s", data_to_update)

                # Add an host log
                data_to_update['ls_state_changed'] = (
                    data_to_update['ls_state'] != data_to_update['ls_last_state']
                )
                data_to_update['host'] = self.mapping['host'][data['host_name']]
                data_to_update['service'] = None

                # Rename ls_ keys and delete non used keys...
                for field in ['ls_attempt', 'ls_last_state_changed', 'ls_last_hard_state_changed',
                              'ls_last_time_up', 'ls_last_time_down', 'ls_last_time_unknown',
                              'ls_last_time_unreachable']:
                    del data_to_update[field]
                for key in data_to_update:
                    if key.startswith('ls_'):
                        data_to_update[key[3:]] = data_to_update[key]
                        del data_to_update[key]

                ret = self.send_to_backend('log_host', data['host_name'], data_to_update)
                if ret:
                    counters['log_host'] += 1
        elif obj_type == 'service':
            service_name = '__'.join([data['host_name'], data['service_description']])
            if service_name in self.mapping['service']:
                # Received data for a service:
                data_to_update = {
                    'ls_state': data['state'],
                    'ls_state_id': data['state_id'],
                    'ls_state_type': data['state_type'],
                    'ls_last_check': data['last_chk'],
                    'ls_last_state': data['last_state'],
                    'ls_last_state_type': data['last_state_type'],
                    'ls_last_state_changed': data['last_state_change'],
                    'ls_output': data['output'],
                    'ls_long_output': data['long_output'],
                    'ls_perf_data': data['perf_data'],
                    'ls_acknowledged': data['problem_has_been_acknowledged'],
                    'ls_acknowledgement_type': data['acknowledgement_type'],
                    'ls_downtimed': data['in_scheduled_downtime'],
                    'ls_execution_time': data['execution_time'],
                    'ls_latency': data['latency'],

                    # 'ls_passive_check': data['passive_check'],
                    'ls_attempt': data['attempt'],
                    'ls_last_hard_state_changed': data['last_hard_state_change'],
                    # Last time in the corresponding state
                    'ls_last_time_ok': data['last_time_ok'],
                    'ls_last_time_warning': data['last_time_warning'],
                    'ls_last_time_critical': data['last_time_critical'],
                    'ls_last_time_unknown': data['last_time_unknown'],
                    'ls_last_time_unreachable': data['last_time_unreachable']
                }
                s_id = self.mapping['service'][service_name]
                if 'initial_state' in self.ref_live['service'][s_id]:
                    data_to_update['ls_last_state'] = \
                        self.ref_live['service'][s_id]['initial_state']
                    data_to_update['ls_last_state_type'] = \
                        self.ref_live['service'][s_id]['initial_state_type']
                    del self.ref_live['service'][s_id]['initial_state']
                    del self.ref_live['service'][s_id]['initial_state_type']

                data_to_update['_realm'] = self.ref_live['service'][s_id]['_realm']

                # Update live state
                ret = self.send_to_backend('livestate_service', service_name, data_to_update)
                if ret:
                    counters['livestate_service'] += 1
                logger.debug("Updated service live state data: %s", data_to_update)

                # Add a service log
                data_to_update['ls_state_changed'] = (
                    data_to_update['ls_state'] != data_to_update['ls_last_state']
                )
                data_to_update['host'] = self.mapping['host'][data['host_name']]
                data_to_update['service'] = self.mapping['service'][service_name]

                # Rename ls_ keys and delete non used keys...
                for field in ['ls_attempt', 'ls_last_state_changed', 'ls_last_hard_state_changed',
                              'ls_last_time_ok', 'ls_last_time_warning', 'ls_last_time_critical',
                              'ls_last_time_unknown', 'ls_last_time_unreachable']:
                    del data_to_update[field]
                for key in data_to_update:
                    if key.startswith('ls_'):
                        data_to_update[key[3:]] = data_to_update[key]
                        del data_to_update[key]

                self.send_to_backend('log_service', service_name, data_to_update)
                if ret:
                    counters['log_service'] += 1

        if (counters['livestate_host'] + counters['livestate_service']) > 0:
            logger.debug("--- %s seconds ---", (time.time() - start_time))
        return counters

    def send_to_backend(self, type_data, name, data):
        """
        Send data to alignak backend

        :param type_data: one of ['livestate_host', 'livestate_service', 'log_host', 'log_service']
        :type type_data: str
        :param name: name of host or service
        :type name: str
        :param data: dictionary with data to add / update
        :type data: dict
        :return: True if send is ok, False otherwise
        :rtype: bool
        """
        if not self.backend_connected:
            logger.error("Alignak backend connection is not available. "
                         "Skipping objects update.")
            return
        logger.debug("Send to backend: %s, %s", type_data, data)

        headers = {
            'Content-Type': 'application/json',
        }
        ret = True
        if type_data == 'livestate_host':
            headers['If-Match'] = self.ref_live['host'][self.mapping['host'][name]]['_etag']
            try:
                response = self.backend.patch(
                    'host/%s' % self.ref_live['host'][self.mapping['host'][name]]['_id'],
                    data, headers, True)
                if response['_status'] == 'ERR':  # pragma: no cover - should not happen
                    logger.error('%s', response['_issues'])
                    ret = False
                else:
                    self.ref_live['host'][self.mapping['host'][name]]['_etag'] = response['_etag']
            except BackendException as exp:  # pragma: no cover - should not happen
                logger.error('Patch livestate for host %s error', self.mapping['host'][name])
                logger.error('Data: %s', data)
                logger.exception("Exception: %s", exp)
                self.backend_connected = False
        elif type_data == 'livestate_service':
            headers['If-Match'] = self.ref_live['service'][self.mapping['service'][name]]['_etag']
            try:
                response = self.backend.patch(
                    'service/%s' % self.ref_live['service'][self.mapping['service'][name]]['_id'],
                    data, headers, True)
                if response['_status'] == 'ERR':  # pragma: no cover - should not happen
                    logger.error('%s', response['_issues'])
                    ret = False
                else:
                    self.ref_live['service'][self.mapping['service'][name]]['_etag'] = response[
                        '_etag']
            except BackendException as exp:  # pragma: no cover - should not happen
                logger.error('Patch livestate for service %s error', self.mapping['service'][name])
                logger.error('Data: %s', data)
                logger.exception("Exception: %s", exp)
                self.backend_connected = False
        elif type_data == 'log_host':
            try:
                response = self.backend.post('logcheckresult', data)
            except BackendException as exp:  # pragma: no cover - should not happen
                logger.error('Post logcheckresult for host %s error', self.mapping['host'][name])
                logger.error('Data: %s', data)
                logger.exception("Exception: %s", exp)
                self.backend_connected = False
                ret = False
        elif type_data == 'log_service':
            try:
                response = self.backend.post('logcheckresult', data)
            except BackendException as exp:  # pragma: no cover - should not happen
                logger.error('Post logcheckresult for service %s error',
                             self.mapping['service'][name])
                logger.error('Data: %s', data)
                logger.exception("Exception: %s", exp)
                logger.error('Error detail: %s, %s, %s', exp.code, exp.message, exp.response)
                self.backend_connected = False
                ret = False
        return ret

    def update_status(self, brok):
        # pylint: disable=too-many-locals
        """We manage the status change for a backend host/service/contact

        :param brok: the brok
        :type brok:
        :return: None
        """
        if 'contact_name' in brok.data:
            contact_name = brok.data['contact_name']
            if brok.data['contact_name'] not in self.mapping['user']:
                logger.warning("Got a brok for an unknown user: '%s'", contact_name)
                return
            endpoint = 'user'
            name = contact_name
            item_id = self.mapping['user'][name]
        else:
            host_name = brok.data['host_name']
            if brok.data['host_name'] not in self.mapping['host']:
                logger.warning("Got a brok for an unknown host: '%s'", host_name)
                return
            endpoint = 'host'
            name = host_name
            item_id = self.mapping['host'][name]
            if 'service_description' in brok.data:
                service_name = '__'.join([host_name, brok.data['service_description']])
                endpoint = 'service'
                name = service_name
                item_id = self.mapping['service'][name]
                if service_name not in self.mapping['service']:
                    logger.warning("Got a brok for an unknown service: '%s'", service_name)
                    return

        # Sort brok properties
        sorted_brok_properties = sorted(brok.data)
        logger.debug("Update status %s: %s", endpoint, sorted(brok.data))

        # Search the concerned element
        item = self.backend.get(endpoint + '/' + item_id)
        logger.debug("Found %s: %s", endpoint, sorted(item))

        differences = {}
        for key in sorted_brok_properties:
            value = brok.data[key]
            # Filter livestate keys...
            if "ls_%s" % key in item:
                logger.debug("Filtered live state: %s", key)
                continue

            # Filter noisy keys...
            if key in ["display_name", "tags"]:
                logger.debug("Filtered noisy key: %s", key)
                continue

            # Filter linked objects...
            if key in ['parents', 'parent_dependencies',
                       'check_command', 'event_handler', 'snapshot_command', 'check_period',
                       'maintenance_period', 'snapshot_period', 'notification_period',
                       'host_notification_period', 'service_notification_period',
                       'host_notification_commands', 'service_notification_commands',
                       'contacts', 'contact_groups', 'hostgroups',
                       'checkmodulations']:
                logger.debug("Filtered linked object: %s", key)
                continue

            if key not in item:
                logger.debug("Not existing: %s", key)
                continue

            if item[key] != value:
                if isinstance(value, bool):
                    logger.debug("Different (%s): '%s' != '%s'!", key, item[key], value)
                    differences.update({key: value})
                elif not item[key] and not value:
                    logger.info("Different but empty fields (%s): '%s' != "
                                "'%s' (brok), types: %s / %s",
                                key, item[key], value, type(item[key]), type(value))
                else:
                    logger.debug("Different (%s): '%s' != '%s'!", key, item[key], value)
                    differences.update({key: value})
            else:
                logger.debug("Identical (%s): '%s'.", key, value)

        update = False
        if differences:
            logger.info("%s / %s, some modifications exist: %s.",
                        endpoint, item['name'], differences)

            headers = {
                'Content-Type': 'application/json',
                'If-Match': item['_etag']
            }
            try:
                response = self.backend.patch('%s/%s' % (endpoint, item['_id']),
                                              differences, headers, True)
                if response['_status'] == 'ERR':  # pragma: no cover - should not happen
                    logger.warning("Update %s: %s failed, errors: %s.",
                                   endpoint, name, response['_issues'])
                else:
                    update = True
                    logger.info("Updated %s: %s.", endpoint, name)
            except BackendException as exp:  # pragma: no cover - should not happen
                logger.error("Update %s '%s' failed", endpoint, name)
                logger.error("Data: %s", differences)
                logger.exception("Exception: %s", exp)
                self.backend_connected = False

        return update

    def update_program_status(self, brok):
        """Manage the whole program status change

        `program_status` brok is raised on program start whereas `update_program_status` brok
        is raised on every scheduler loop.

        `program_status` and `update_program_status` broks may contain:
        {
            # Some general information
            u'alignak_name': u'arbiter-master',
            u'instance_id': u'176064a1b30741d39452415097807ab0',
            u'instance_name': u'scheduler-master',

            # Some running information
            u'program_start': 1493969754,
            u'daemon_mode': 1,
            u'pid': 68989,
            u'last_alive': 1493970641,
            u'last_command_check': 1493970641,
            u'last_log_rotation': 1493970641,
            u'is_running': 1,

            # Some configuration parameters
            u'process_performance_data': True,
            u'passive_service_checks_enabled': True,
            u'event_handlers_enabled': True,
            u'command_file': u'',
            u'global_host_event_handler': None,
            u'interval_length': 60,
            u'modified_host_attributes': 0,
            u'check_external_commands': True,
            u'failure_prediction_enabled': 0,
            u'modified_service_attributes': 0,
            u'passive_host_checks_enabled': True,
            u'obsess_over_hosts': False,
            u'global_service_event_handler': None,
            u'notifications_enabled': True,
            u'check_service_freshness': True,
            u'check_host_freshness': True,
            u'obsess_over_services': False,
            u'flap_detection_enabled': True,
            u'active_service_checks_enabled': True,
            u'active_host_checks_enabled': True
        }

        :param brok: the brok
        :type brok:
        :return: None
        """
        if 'alignak_name' not in brok.data:
            logger.warning("Missing alignak_name in the brok data, "
                           "the program status cannot be updated. "
                           "Your Alignak framework version is too old to support this feature.")
            return
        if not self.default_realm:
            logger.warning("Missing Alignak backend default realm, "
                           "the program status cannot be updated. "
                           "Your Alignak backend is in a very bad state!")
            return

        # Set event handlers as strings - simple protectection
        if 'global_host_event_handler' in brok.data and \
                not isinstance(brok.data['global_host_event_handler'], basestring):
            brok.data['global_host_event_handler'] = str(brok.data['global_host_event_handler'])

        if 'global_service_event_handler' in brok.data and \
                not isinstance(brok.data['global_service_event_handler'], basestring):
            brok.data['global_service_event_handler'] = \
                str(brok.data['global_service_event_handler'])

        name = brok.data.pop('alignak_name')
        brok.data['name'] = name
        brok.data['_realm'] = self.default_realm

        params = {'sort': '_id', 'where': '{"name": "%s"}' % name}
        all_alignak = self.backend.get_all('alignak', params)
        logger.debug("Got %d Alignak configurations for %s", len(all_alignak['_items']), name)

        headers = {'Content-Type': 'application/json'}
        if not all_alignak['_items']:
            try:
                response = self.backend.post('alignak', brok.data)
                if response['_status'] == 'ERR':  # pragma: no cover - should not happen
                    logger.warning("Create alignak: %s failed, errors: %s.",
                                   name, response['_issues'])
                else:
                    logger.info("Created alignak: %s.", name)
            except BackendException as exp:  # pragma: no cover - should not happen
                logger.error("Create alignak '%s' failed", name)
                logger.error("Data: %s", brok.data)
                logger.exception("Exception: %s", exp)
                self.backend_connected = False

        else:
            item = all_alignak['_items'][0]
            for key in item:
                if key not in brok.data:
                    continue
                if item[key] == brok.data[key]:
                    brok.data.pop(key)
                    continue
                logger.debug("- updating: %s = %s", key, brok.data[key])

            if not brok.data:
                logger.debug("Nothing to update")
                return

            headers['If-Match'] = item['_etag']
            try:
                response = self.backend.patch('alignak/%s' % (item['_id']),
                                              brok.data, headers, True)
                if response['_status'] == 'ERR':  # pragma: no cover - should not happen
                    logger.warning("Update alignak: %s failed, errors: %s.",
                                   name, response['_issues'])
                else:
                    logger.debug("Updated alignak: %s. %s", name, response)
            except BackendException as exp:  # pragma: no cover - should not happen
                logger.error("Update alignak '%s' failed", name)
                logger.error("Data: %s", brok.data)
                logger.exception("Exception: %s / %s", exp, exp.response)
                self.backend_connected = False

    def manage_brok(self, brok):
        """
        We get the data to manage

        :param brok: Brok object
        :type brok: object
        :return: False if broks were not managed by the module
        """
        if not self.logged_in:
            self.logged_in = self.backendConnection()

        if not self.logged_in:
            logger.debug("Not logged-in, ignoring broks...")
            return False

        try:
            endpoint = ''
            name = ''
            # Temporary: get concerned item for tracking received broks
            if 'contact_name' in brok.data:
                contact_name = brok.data['contact_name']
                if brok.data['contact_name'] not in self.mapping['user']:
                    logger.debug("Got a brok %s for an unknown user: '%s' (%s)",
                                 brok.type, contact_name, brok.data)
                    return False
                endpoint = 'user'
                name = contact_name
            else:
                if 'host_name' in brok.data:
                    host_name = brok.data['host_name']
                    if brok.data['host_name'] not in self.mapping['host']:
                        logger.debug("Got a brok %s for an unknown host: '%s' (%s)",
                                     brok.type, host_name, brok.data)
                        return False
                    endpoint = 'host'
                    name = host_name
                    if 'service_description' in brok.data:
                        service_name = '__'.join([host_name, brok.data['service_description']])
                        endpoint = 'service'
                        name = service_name
                        if service_name not in self.mapping['service']:
                            logger.debug("Got a brok %s for an unknown service: '%s' (%s)",
                                         brok.type, service_name, brok.data)
                            return False
            if name:
                logger.debug("Received a brok: %s, for %s '%s'", brok.type, endpoint, name)
            else:
                logger.debug("Received a brok: %s", brok.type)
            logger.debug("Brok data: %s", brok.data)

            if brok.type in ['program_status', 'update_program_status']:
                logger.debug("Got %s brok: %s", brok.type, brok.data)
                self.update_program_status(brok)

            if brok.type == 'host_next_schedule':
                logger.debug("Got host next schedule brok: %s", brok.data)
                self.update_next_check(brok.data, 'host')
            if brok.type == 'service_next_schedule':
                logger.debug("Got service next schedule brok: %s", brok.data)
                self.update_next_check(brok.data, 'service')

            if brok.type == 'update_service_status':
                logger.debug("Got service update status brok: %s", brok.data)
                self.update_status(brok)
            if brok.type == 'update_host_status':
                logger.debug("Got host update status brok: %s", brok.data)
                self.update_status(brok)
            if brok.type == 'update_contact_status':
                logger.debug("Got contact update status brok: %s", brok.data)
                self.update_status(brok)

            if brok.type == 'new_conf':
                logger.info("Got a new configuration, reloading objects...")
                loaded = self.loaded_users
                self.get_refs('livestate_user')
                if self.loaded_users > loaded:
                    logger.info("- users references reloaded")
                else:
                    logger.warning("- users references not reloaded. "
                                   "Last reload is too recent; set the 'load_protect_delay' "
                                   "parameter accordingly.")

                loaded = self.loaded_hosts
                self.get_refs('livestate_host')
                if self.loaded_hosts > loaded:
                    logger.info("- hosts references reloaded")
                else:
                    logger.warning("- hosts references not reloaded. "
                                   "Last reload is too recent; set the 'load_protect_delay' "
                                   "parameter accordingly.")

                loaded = self.loaded_services
                self.get_refs('livestate_service')
                if self.loaded_services > loaded:
                    logger.info("- services references reloaded")
                else:
                    logger.warning("- services references not reloaded. "
                                   "Last reload is too recent; set the 'load_protect_delay' "
                                   "parameter accordingly.")

            if brok.type == 'host_check_result':
                self.update_livestate(brok.data, 'host')

            if brok.type == 'service_check_result':
                self.update_livestate(brok.data, 'service')

            if brok.type in ['acknowledge_raise', 'acknowledge_expire',
                             'downtime_raise', 'downtime_expire']:
                self.update_actions(brok)

            return True
        except Exception as exp:  # pragma: no cover - should not happen
            logger.exception("Manage brok exception: %s", exp)

        return False

    def update_actions(self, brok):
        """We manage the acknowledge and downtime broks

        :param brok: the brok
        :type brok:
        :return: None
        """
        host_name = brok.data['host']
        if host_name not in self.mapping['host']:
            logger.warning("Got a brok for an unknown host: '%s'", host_name)
            return
        service_name = ''
        if 'service' in brok.data:
            service_name = '__'.join([host_name, brok.data['service']])
            if service_name not in self.mapping['service']:
                logger.warning("Got a brok for an unknown service: '%s'", service_name)
                return

        data_to_update = {}
        endpoint = 'actionacknowledge'
        if brok.type == 'acknowledge_raise':
            data_to_update['ls_acknowledged'] = True
        elif brok.type == 'acknowledge_expire':
            data_to_update['ls_acknowledged'] = False
        elif brok.type == 'downtime_raise':
            data_to_update['ls_downtimed'] = True
            endpoint = 'actiondowntime'
        elif brok.type == 'downtime_expire':
            data_to_update['ls_downtimed'] = False
            endpoint = 'actiondowntime'

        where = {
            'processed': True,
            'notified': False,
            'host': self.mapping['host'][host_name],
            'comment': brok.data['comment'],
            'service': None
        }

        if 'service' in brok.data:
            # it's a service
            self.send_to_backend('livestate_service', service_name, data_to_update)
            where['service'] = self.mapping['service'][service_name]
        else:
            # it's a host
            self.send_to_backend('livestate_host', host_name, data_to_update)

        params = {
            'where': json.dumps(where)
        }
        actions = self.backend.get_all(endpoint, params)
        if actions['_items']:
            # case 1: the acknowledge / downtime come from backend, we update the 'notified' field
            # to True
            headers = {
                'Content-Type': 'application/json',
                'If-Match': actions['_items'][0]['_etag']
            }
            self.backend.patch(
                endpoint + '/' + actions['_items'][0]['_id'], {"notified": True}, headers, True)
        else:
            # case 2: the acknowledge / downtime do not come from the backend, it's an external
            # command so we create a new entry
            where['notified'] = True
            # try find the user
            users = self.backend.get_all('user',
                                         {'where': '{"name":"' + brok.data['author'] + '"}'})
            if users['_items']:
                where['user'] = users['_items'][0]['_id']
            else:
                return

            if brok.type in ['acknowledge_raise', 'downtime_raise']:
                where['action'] = 'add'
            else:
                where['action'] = 'delete'
            where['_realm'] = self.ref_live['host'][where['host']]['_realm']

            if endpoint == 'actionacknowledge':
                if brok.data['sticky'] == 2:
                    where['sticky'] = False
                else:
                    where['sticky'] = True
                where['notify'] = bool(brok.data['notify'])
            elif endpoint == 'actiondowntime':
                where['start_time'] = int(brok.data['start_time'])
                where['end_time'] = int(brok.data['end_time'])
                where['fixed'] = bool(brok.data['fixed'])
                where['duration'] = int(brok.data['duration'])
            self.backend.post(endpoint, where)

    def main(self):
        """
        Main loop of the process

        This module is an "external" module
        :return:
        """
        # Set the OS process title
        self.set_proctitle(self.alias)
        self.set_exit_handler()

        logger.info("starting...")

        while not self.interrupted:
            try:
                logger.debug("queue length: %s", self.to_q.qsize())
                start = time.time()

                message = self.to_q.get_nowait()
                for brok in message:
                    # Prepare and manage each brok in the queue message
                    brok.prepare()
                    self.manage_brok(brok)

                logger.debug("time to manage %s broks (%d secs)", len(message), time.time() - start)
            except Queue.Empty:
                # logger.debug("No message in the module queue")
                time.sleep(0.1)

        logger.info("stopping...")
        logger.info("stopped")
