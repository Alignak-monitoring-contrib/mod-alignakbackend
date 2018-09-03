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
This module is used to send logs and livestate to alignak-backend with broker
"""

import time
import json
import queue
import logging

from alignak.stats import Stats
from alignak.basemodule import BaseModule
from alignak_backend_client.client import Backend, BackendException

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name
for handler in logger.parent.handlers:
    if isinstance(handler, logging.StreamHandler):
        logger.parent.removeHandler(handler)

# pylint: disable=invalid-name
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
        logger.setLevel(getattr(mod_conf, 'log_level', logging.INFO))

        logger.debug("inner properties: %s", self.__dict__)
        logger.debug("received configuration: %s", mod_conf.__dict__)

        self.client_processes = int(getattr(mod_conf, 'client_processes', 1))
        logger.info("Number of processes used by backend client: %s", self.client_processes)

        self.default_realm = None

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
        self.backend_connected = False
        self.backend_connection_retry_planned = 0
        try:
            self.backend_connection_retry_delay = int(getattr(mod_conf,
                                                              'backend_connection_retry_delay',
                                                              '10'))
        except ValueError:
            self.backend_connection_retry_delay = 10
        logger.info("backend connection retry delay: %.2f seconds",
                    self.backend_connection_retry_delay)

        self.backend_errors_count = 0
        self.backend_username = getattr(mod_conf, 'username', '')
        self.backend_password = getattr(mod_conf, 'password', '')
        self.backend_generate = getattr(mod_conf, 'allowgeneratetoken', False)

        self.backend_count = int(getattr(mod_conf, 'backend_count', '50'))
        logger.info("backend pagination count: %d items", self.backend_count)

        self.backend_token = getattr(mod_conf, 'token', '')
        self.backend = Backend(self.url, self.client_processes)

        self.manage_update_program_status = getattr(mod_conf, 'update_program_status', '0') == '1'
        logger.info("manage update_program_status broks: %s", self.manage_update_program_status)

        # Log in to the backend
        self.logged_in = False
        self.backend_connected = self.backend_connection()

        # Get the default realm
        self.default_realm = self.get_default_realm()

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
        self.last_load = 0

        # Backend to be posted data
        self.logcheckresults = []

    # Common functions
    def do_loop_turn(self):
        """This function is called/used when you need a module with
        a loop function (and use the parameter 'external': True)

        Note: We are obliged to define this method (even if not called!) because
        it is an abstract function in the base class
        """
        logger.info("In loop")
        time.sleep(1)

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

    def backend_connection(self):
        """Backend connection to check live state update is allowed

        :return: True/False
        """
        if self.backend_login():
            self.get_default_realm()

            try:
                start = time.time()
                params = {'where': '{"token":"%s"}' % self.backend.token}
                users = self.backend.get('user', params)
                self.statsmgr.counter('backend-get.user', 1)
                self.statsmgr.timer('backend-get-time.user', time.time() - start)
            except BackendException as exp:
                logger.warning("Error on backend when retrieving user information: %s", exp)
            else:
                try:
                    for item in users['_items']:
                        self.logged_in = item['can_update_livestate']
                    return self.logged_in
                except Exception as exp:
                    logger.error("Can't get the user information in the backend response: %s", exp)

        logger.error("Configured user account is not allowed for this module")
        return False

    def backend_login(self):
        """Log in to the backend

        :return: bool
        """
        generate = 'enabled'
        if not self.backend_generate:
            generate = 'disabled'

        if self.backend_token:
            # We have a token, don't ask for a new one
            self.backend.token = self.backend_token
            connected = True  # Not really yet, but assume yes
        else:
            if not self.backend_username or not self.backend_password:
                logger.error("No user or password supplied, and no default token defined. "
                             "Can't connect to backend")
                connected = False
            else:
                try:
                    start = time.time()
                    connected = self.backend.login(self.backend_username, self.backend_password,
                                                   generate)
                    self.statsmgr.counter('backend-login', 1)
                    self.statsmgr.timer('backend-login-time', time.time() - start)
                except BackendException as exp:
                    logger.error("Error on backend login: %s", exp)
                    connected = False

        return connected

    def get_default_realm(self):
        """
        Retrieves the default top level realm for the connected user
        :return: str or None
        """
        default_realm = None

        if self.backend_connected:
            try:
                start = time.time()
                result = self.backend.get('/realm', {'max_results': 1, 'sort': '_level'})
                self.statsmgr.counter('backend-get.realm', 1)
                self.statsmgr.timer('backend-get-time.realm', time.time() - start)
            except BackendException as exp:
                logger.warning("Error on backend when retrieving default realm: %s", exp)
            else:
                try:
                    default_realm = result['_items'][0]['_id']
                except Exception as exp:
                    logger.error("Can't get the default realm in the backend response: %s", exp)

        return default_realm

    def get_refs(self):
        """
        Get the _id in the backend for hosts, services and users

        :return: None
        """
        start = time.time()
        now = int(time.time())

        logger.info("Got a new configuration, reloading objects...")

        # Get managed inter-process dicts
        host_mapping = self.mapping['host']
        serv_mapping = self.mapping['service']
        user_mapping = self.mapping['user']
        host_ref_live = self.ref_live['host']
        serv_ref_live = self.ref_live['service']
        user_ref_live = self.ref_live['user']

        if now - self.last_load > self.load_protect_delay:
            logger.info("Got a new configuration, reloading objects...")
            # Updating hosts
            hosts = {}
            params = {
                'projection': '{"name":1,"ls_state":1,"ls_state_type":1,"_realm":1}',
                'max_results': self.backend_count,
                'where': '{"_is_template":false}'
            }
            content = self.backend.get_all('host', params)
            self.statsmgr.counter('backend-getall.host', 1)
            for item in content['_items']:
                host_mapping[item['name']] = item['_id']

                host_ref_live[item['_id']] = {
                    '_id': item['_id'],
                    '_etag': item['_etag'],
                    '_realm': item['_realm'],
                    'initial_state': item['ls_state'],
                    'initial_state_type': item['ls_state_type']
                }
                hosts[item['_id']] = item['name']
            logger.info("- hosts references reloaded")

            # Updating services
            params = {
                'projection': '{"host":1,"name":1,"ls_state":1,"ls_state_type":1,"_realm":1}',
                'max_results': self.backend_count,
                'where': '{"_is_template":false}'
            }
            content = self.backend.get_all('service', params)
            self.statsmgr.counter('backend-getall.service', 1)
            for item in content['_items']:
                try:
                    serv_mapping['__'.join([hosts[item['host']], item['name']])] = item['_id']

                    serv_ref_live[item['_id']] = {
                        '_id': item['_id'],
                        '_etag': item['_etag'],
                        '_realm': item['_realm'],
                        'initial_state': item['ls_state'],
                        'initial_state_type': item['ls_state_type']
                    }
                except KeyError:
                    logger.warning("Got a service for an unknown host")
            logger.info("- services references reloaded")

            # Updating users
            params = {
                'projection': '{"name":1,"_realm":1}',
                'max_results': self.backend_count,
                'where': '{"_is_template":false}'
            }
            content = self.backend.get_all('user', params)
            self.statsmgr.counter('backend-getall.user', 1)
            for item in content['_items']:
                user_mapping[item['name']] = item['_id']

                user_ref_live[item['_id']] = {
                    '_id': item['_id'],
                    '_etag': item['_etag'],
                    '_realm': item['_realm']
                }
            logger.info("- users references reloaded")

            self.last_load = now
        else:
            logger.warning("- references not reloaded. Last reload is too recent; "
                           "set the 'load_protect_delay' parameter accordingly.")

        # Propagate changes in the inter-process dicts
        self.mapping['host'] = host_mapping
        self.mapping['service'] = serv_mapping
        self.mapping['user'] = user_mapping
        self.ref_live['host'] = host_ref_live
        self.ref_live['service'] = serv_ref_live
        self.ref_live['user'] = user_ref_live

        end = time.time()
        self.statsmgr.timer('backend-getall.time', end - start)

        return True

    def update_next_check(self, data, obj_type):
        """Update livestate host and service next check timestamp

        {'instance_id': u'475dc864674943b4aa4cbc966f7cc737', u'service_description': u'nsca_disk',
        u'next_chk': 0, u'in_checking': True, u'host_name': u'ek3022fdj-00011'}

        :param data: dictionary of data from scheduler
        :type data: dict
        :param obj_type: type of data (host | service)
        :type obj_type: str
        :return: False if backend update problem
        :rtype: bool
        """
        logger.debug("Update next check: %s, %s", obj_type, data)

        if obj_type == 'host':
            if data['host_name'] in self.mapping['host']:
                # Received data for an host:
                data_to_update = {
                    'ls_next_check': data['next_chk']
                }

                # Update live state
                return self.send_to_backend('livestate_host', data['host_name'], data_to_update)
        elif obj_type == 'service':
            service_name = '__'.join([data['host_name'], data['service_description']])
            if service_name in self.mapping['service']:
                # Received data for a service:
                data_to_update = {
                    'ls_next_check': data['next_chk']
                }

                # Update live state
                return self.send_to_backend('livestate_service', service_name, data_to_update)

        return False

    def check_result(self, data):
        """
        Got a check result for an host/service

        :param data: brok data got from scheduler
        :type data: dict
        :return: False if any error when posting to the backend
        """
        logger.debug("Manage a check result: %s", data)

        # Received data for an host or service
        # Obliged to set an _realm... despite it is unuseful.
        posted_data = {
            '_realm': self.default_realm,
            'state': data['state'],
            'state_type': data['state_type'],
            'state_id': data['state_id'],
            'passive_check': data['passive_check'] if 'passive_check' in data else False,
            'acknowledged': data['problem_has_been_acknowledged'],
            'acknowledgement_type': data['acknowledgement_type'],
            'downtimed': data['in_scheduled_downtime'],
            'last_check': data['last_chk'],
            'last_state': data['last_state'],
            'last_state_id': data['last_state_id'],
            'last_state_type': data['last_state_type'],
            'output': data['output'],
            'long_output': data['long_output'],
            'perf_data': data['perf_data'],
            'latency': data['latency'],
            'execution_time': data['execution_time'],
            'current_attempt': data['attempt'],

            # 'state_changed': data['state_changed'],
            'last_state_changed': data['last_state_change'],
            'last_hard_state_changed': data['last_hard_state_change'],
        }
        if 'service_description' in data:
            posted_data.update({
                'host_name': data['host_name'],
                'service_name': data['service_description'],
                # Last time in the corresponding state
                'last_time_0': data['last_time_ok'],
                'last_time_1': data['last_time_warning'],
                'last_time_2': data['last_time_critical'],
                'last_time_3': data['last_time_unknown'],
                'last_time_4': data['last_time_unreachable']
            })
        else:
            posted_data.update({
                'host_name': data['host_name'],
                # Last time in the corresponding state
                'last_time_0': data['last_time_up'],
                'last_time_1': data['last_time_down'],
                'last_time_2': 0,
                'last_time_3': 0,
                'last_time_4': data['last_time_unreachable']
            })

        # Not managed currently
        # if 'initial_state' in self.ref_live['host'][h_id]:
        #     data_to_update['ls_last_state'] = \
        #         self.ref_live['host'][h_id]['initial_state']
        #     data_to_update['ls_last_state_type'] = \
        #         self.ref_live['host'][h_id]['initial_state_type']
        #     del self.ref_live['host'][h_id]['initial_state']
        #     del self.ref_live['host'][h_id]['initial_state_type']
        self.logcheckresults.append(posted_data)

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
                return None
            endpoint = 'user'
            name = contact_name
            item_id = self.mapping['user'][name]
        else:
            host_name = brok.data['host_name']
            if brok.data['host_name'] not in self.mapping['host']:
                logger.warning("Got a brok for an unknown host: '%s'", host_name)
                return None
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
                    return None

        # Sort brok properties
        sorted_brok_properties = sorted(brok.data)
        logger.debug("Update status %s: %s", endpoint, sorted(brok.data))

        # Search the concerned element
        start = time.time()
        self.statsmgr.counter('backend-get.%s' % endpoint, 1)
        item = self.backend.get(endpoint + '/' + item_id)
        self.statsmgr.timer('backend-get-time.%s' % endpoint, time.time() - start)
        logger.debug("Found %s: %s", endpoint, sorted(item))

        differences = {}
        for key in sorted_brok_properties:
            value = brok.data[key]
            # Filter livestate keys...
            if "ls_%s" % key in item:
                logger.debug("Filtered live state: %s", key)
                continue

            # Filter noisy keys...
            if key in ["display_name", "tags", "notificationways"]:
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
                start = time.time()
                self.statsmgr.counter('backend-patch.%s' % endpoint, 1)
                response = self.backend.patch('%s/%s' % (endpoint, item['_id']),
                                              differences, headers, True)
                self.statsmgr.counter('backend-patch.%s' % endpoint, 1)
                self.statsmgr.timer('backend-patch-time.%s' % endpoint, time.time() - start)
                if response['_status'] == 'ERR':  # pragma: no cover - should not happen
                    logger.warning("Update %s: %s failed, errors: %s.",
                                   endpoint, name, response['_issues'])
                else:
                    update = True
                    logger.info("Updated %s: %s.", endpoint, name)

                if endpoint == 'host':
                    self.ref_live['host'][self.mapping['host'][host_name]]['_etag'] = \
                        response['_etag']
                elif endpoint == 'service':
                    self.ref_live['service'][self.mapping['service'][service_name]]['_etag'] = \
                        response['_etag']
            except BackendException as exp:  # pragma: no cover - should not happen
                logger.error("Update %s '%s' failed", endpoint, name)
                logger.error("Data: %s", differences)
                if exp.code == 404:
                    logger.error('Seems the %s %s deleted in the Backend',
                                 endpoint, name)
                elif exp.code == 412:
                    logger.error('Seems the %s %s was modified in the Backend',
                                 endpoint, name)
                else:
                    logger.exception("Exception: %s", exp)
                    self.backend_connected = False
                    self.backend_connection_retry_planned = \
                        int(time.time()) + self.backend_connection_retry_delay

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
            u'modified_service_attributes': 0,
            u'passive_host_checks_enabled': True,
            u'global_service_event_handler': None,
            u'notifications_enabled': True,
            u'check_service_freshness': True,
            u'check_host_freshness': True,
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
                not isinstance(brok.data['global_host_event_handler'], str):
            brok.data['global_host_event_handler'] = str(brok.data['global_host_event_handler'])

        if 'global_service_event_handler' in brok.data and \
                not isinstance(brok.data['global_service_event_handler'], str):
            brok.data['global_service_event_handler'] = \
                str(brok.data['global_service_event_handler'])

        name = brok.data.pop('alignak_name')
        brok.data['name'] = name
        brok.data['_realm'] = self.default_realm

        params = {'sort': '_id', 'where': '{"name": "%s"}' % name}
        start = time.time()
        all_alignak = self.backend.get_all('alignak', params)
        self.statsmgr.counter('backend-getall.alignak', 1)
        self.statsmgr.timer('backend-getall-time.alignak', time.time() - start)
        logger.debug("Got %d Alignak configurations for %s", len(all_alignak['_items']), name)

        headers = {'Content-Type': 'application/json'}
        if not all_alignak['_items']:
            try:
                start = time.time()
                self.statsmgr.counter('backend-post.alignak', 1)
                response = self.backend.post('alignak', brok.data)
                self.statsmgr.timer('backend-post-time.alignak', time.time() - start)
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
                self.backend_connection_retry_planned = \
                    int(time.time()) + self.backend_connection_retry_delay

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
                start = time.time()
                self.statsmgr.counter('backend-patch.alignak', 1)
                response = self.backend.patch('alignak/%s' % (item['_id']),
                                              brok.data, headers, True)
                self.statsmgr.timer('backend-patch-time.alignak', time.time() - start)
                if response['_status'] == 'ERR':  # pragma: no cover - should not happen
                    logger.warning("Update alignak: %s failed, errors: %s.",
                                   name, response['_issues'])
                else:
                    logger.debug("Updated alignak: %s. %s", name, response)
            except BackendException as exp:  # pragma: no cover - should not happen
                logger.error("Update alignak '%s' failed", name)
                logger.error("Data: %s", brok.data)
                if exp.code == 404:
                    logger.error('Seems the alignak %s deleted in the Backend', name)
                elif exp.code == 412:
                    logger.error('Seems the alignak %s was modified in the Backend', name)
                else:
                    logger.exception("Exception: %s / %s", exp, exp.response)
                    self.backend_connected = False
                    self.backend_connection_retry_planned = \
                        int(time.time()) + self.backend_connection_retry_delay

    def update_actions(self, brok):
        """We manage the acknowledge and downtime broks

        :param brok: the brok
        :type brok:
        :return: None
        """
        host_name = brok.data['host']
        if host_name not in self.mapping['host']:
            logger.error("Updating action for a brok for an unknown host: '%s'", host_name)
            return False
        service_name = ''
        if 'service' in brok.data:
            service_name = '__'.join([host_name, brok.data['service']])
            if service_name not in self.mapping['service']:
                logger.error("Updating action for a brok for an unknown service: '%s'",
                             service_name)
                return False

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
            cr = self.send_to_backend('livestate_service', service_name, data_to_update)
            where['service'] = self.mapping['service'][service_name]
        else:
            # it's a host
            self.send_to_backend('livestate_host', host_name, data_to_update)

        params = {
            'where': json.dumps(where)
        }
        self.statsmgr.counter('backend-getall.%s' % endpoint, 1)
        actions = self.backend.get_all(endpoint, params)
        if actions['_items']:
            # case 1: the acknowledge / downtime come from backend, we update the 'notified' field
            # to True
            headers = {
                'Content-Type': 'application/json',
                'If-Match': actions['_items'][0]['_etag']
            }
            self.statsmgr.counter('backend-patch.%s' % endpoint, 1)
            cr = self.backend.patch(endpoint + '/' + actions['_items'][0]['_id'],
                                    {"notified": True}, headers, True)
            return cr['_status'] == 'OK'

        # case 2: the acknowledge / downtime do not come from the backend, it's an external
        # command so we create a new entry
        where['notified'] = True
        # try find the user
        self.statsmgr.counter('backend-getall.user', 1)
        users = self.backend.get_all('user',
                                     {'where': '{"name":"' + brok.data['author'] + '"}'})
        if users['_items']:
            where['user'] = users['_items'][0]['_id']
        else:
            logger.error("User '%s' is unknown, ack/downtime is set by admin",
                         brok.data['author'])
            users = self.backend.get_all('user', {'where': '{"name":"admin"}'})
            where['user'] = users['_items'][0]['_id']

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
        self.statsmgr.counter('backend-post.%s' % endpoint, 1)
        cr = self.backend.post(endpoint, where)
        return cr['_status'] == 'OK'

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
        if not self.backend_connected and int(time.time() > self.backend_connection_retry_planned):
            self.backend_connected = self.backend_connection()

        if not self.backend_connected:
            logger.error("Alignak backend connection is not available. "
                         "Skipping objects update.")
            return None
        logger.debug("Send to backend: %s, %s", type_data, data)

        headers = {
            'Content-Type': 'application/json',
        }
        ret = True
        if type_data == 'livestate_host':
            headers['If-Match'] = self.ref_live['host'][self.mapping['host'][name]]['_etag']
            try:
                start = time.time()
                # self.statsmgr.counter('backend-patch.host', 1)
                response = self.backend.patch(
                    'host/%s' % self.ref_live['host'][self.mapping['host'][name]]['_id'],
                    data, headers, True)
                self.statsmgr.timer('backend-patch-time.host', time.time() - start)
                if response['_status'] == 'ERR':  # pragma: no cover - should not happen
                    logger.error('%s', response['_issues'])
                    ret = False
                else:
                    self.ref_live['host'][self.mapping['host'][name]]['_etag'] = response['_etag']
            except BackendException as exp:  # pragma: no cover - should not happen
                logger.error('Patch livestate for host %s error', self.mapping['host'][name])
                logger.error('Data: %s', data)
                logger.exception("Exception: %s", exp)
                if exp.code == 404:
                    logger.error('Seems the host %s deleted in the Backend',
                                 self.mapping['host'][name])
                elif exp.code == 412:
                    logger.error('Seems the host %s was modified in the Backend',
                                 self.mapping['host'][name])
                    ret = False
                else:
                    self.backend_connected = False
                    self.backend_connection_retry_planned = \
                        int(time.time()) + self.backend_connection_retry_delay
        elif type_data == 'livestate_service':
            service_id = self.mapping['service'][name]
            headers['If-Match'] = self.ref_live['service'][service_id]['_etag']
            try:
                start = time.time()
                self.statsmgr.counter('backend-patch.service', 1)
                logger.debug("Send to backend: %s, %s (_etag: %s) - %s",
                             type_data, name,
                             self.ref_live['service'][service_id]['_etag'],
                             data)
                response = self.backend.patch('service/%s' %
                                              self.ref_live['service'][service_id]['_id'],
                                              data, headers, True)
                self.statsmgr.timer('backend-patch-time.service', time.time() - start)
                if response['_status'] == 'ERR':  # pragma: no cover - should not happen
                    logger.error('%s', response['_issues'])
                    ret = False
                else:
                    self.ref_live['service'][service_id]['_etag'] = response['_etag']
                    logger.debug("Updated _etag: %s, %s (_etag: %s)",
                                 type_data, name,
                                 self.ref_live['service'][self.mapping['service'][name]]['_etag'])
            except BackendException as exp:  # pragma: no cover - should not happen
                logger.error('Patch livestate for %s/%s %s error',
                             type_data, name, self.mapping['service'][name])
                logger.error('Data: %s', data)
                logger.exception("Exception: %s", exp)
                if exp.code == 404:
                    logger.error('Seems the service %s deleted in the Backend',
                                 self.mapping['service'][name])
                elif exp.code == 412:
                    logger.error('Seems the service %s was modified in the Backend',
                                 self.mapping['service'][name])
                    ret = False
                else:
                    self.backend_connected = False
                    self.backend_connection_retry_planned = \
                        int(time.time()) + self.backend_connection_retry_delay
        elif type_data == 'lcrs':
            response = {'_status': 'OK'}
            try:
                logger.debug("Posting %d LCRs to the backend", len(self.logcheckresults))
                while self.logcheckresults:
                    start = time.time()
                    lcrs = self.logcheckresults[:100]
                    self.statsmgr.counter('backend-post.lcr', len(lcrs))
                    response = self.backend.post(endpoint='logcheckresult', data=lcrs)
                    logger.debug("Posted %d LCRs", len(lcrs))
                    del self.logcheckresults[:100]
                self.logcheckresults = []
            except BackendException as exp:  # pragma: no cover - should not happen
                logger.error('Error when posting LCR to the backend, data: %s',
                             self.logcheckresults)
                logger.error("Exception: %s", exp)
                self.backend_connected = False
                self.backend_connection_retry_planned = \
                    int(time.time()) + self.backend_connection_retry_delay
            else:
                self.statsmgr.timer('backend-post-time.lcr', time.time() - start)

                if response['_status'] == 'ERR':  # pragma: no cover - should not happen
                    logger.error('Error when posting LCR to the backend, data: %s',
                                 self.logcheckresults)
                    logger.error('Issues: %s', response['_issues'])
                    ret = False

        return ret

    def manage_brok(self, brok):
        """
        We get the data to manage

        :param brok: Brok object
        :type brok: object
        :return: False if broks were not managed by the module
        """
        if not self.logged_in:
            if not self.backend_connection():
                logger.debug("Not logged-in, ignoring broks...")
                return False

        brok.prepare()

        logger.debug("manage_brok receives a Brok:")
        logger.debug("\t-Brok: %s - %s", brok.type, brok.data)

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

            start = time.time()
            self.statsmgr.counter('managed-broks-type-count.%s' % brok.type, 1)

            ret = False
            if brok.type in ['new_conf']:
                ret = self.get_refs()

            if self.manage_update_program_status and \
                    brok.type in ['program_status', 'update_program_status']:
                self.update_program_status(brok)
                ret = None

            if brok.type == 'host_next_schedule':
                ret = self.update_next_check(brok.data, 'host')
            if brok.type == 'service_next_schedule':
                ret = self.update_next_check(brok.data, 'service')

            if brok.type in ['update_host_status', 'update_service_status',
                             'update_contact_status']:
                ret = self.update_status(brok)

            if brok.type in ['host_check_result', 'service_check_result']:
                self.check_result(brok.data)
                ret = None

            if brok.type in ['acknowledge_raise', 'acknowledge_expire',
                             'downtime_raise', 'downtime_expire']:
                ret = self.update_actions(brok)

            self.statsmgr.timer('managed-broks-type-time-%s' % brok.type, time.time() - start)

            return ret
        except Exception as exp:  # pragma: no cover - should not happen
            logger.exception("Manage brok exception: %s", exp)

        return False

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
                queue_size = self.to_q.qsize()
                if queue_size:
                    logger.debug("queue length: %s", queue_size)
                    self.statsmgr.gauge('queue-size', queue_size)

                # Reset backend lists
                self.logcheckresults = []

                message = self.to_q.get_nowait()
                start = time.time()
                for brok in message:
                    # Prepare and manage each brok in the queue message
                    brok.prepare()
                    self.manage_brok(brok)
                self.statsmgr.gauge('managed-broks-count', len(message))

                logger.debug("time to manage %s broks (%d secs)", len(message), time.time() - start)
                self.statsmgr.timer('managed-broks-time', time.time() - start)

                if self.logcheckresults:
                    self.send_to_backend('lcrs', None, None)

            except queue.Empty:
                # logger.debug("No message in the module queue")
                time.sleep(0.1)

        logger.info("stopping...")
        logger.info("stopped")
