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
import logging

from alignak.basemodule import BaseModule
from alignak_backend_client.client import Backend, BackendException

logger = logging.getLogger('alignak.module')  # pylint: disable=C0103

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

    def __init__(self, modconf):
        BaseModule.__init__(self, modconf)
        self.url = getattr(modconf, 'api_url', 'http://localhost:5000')
        self.backend = Backend(self.url)
        self.backend.token = getattr(modconf, 'token', '')
        self.backend_connected = False
        if self.backend.token == '':
            self.getToken(getattr(modconf, 'username', ''), getattr(modconf, 'password', ''),
                          getattr(modconf, 'allowgeneratetoken', False))

        self.logged_in = self.backendConnection()

        self.ref_live = {
            'host': {},
            'service': {}
        }
        self.mapping = {
            'host': {},
            'service': {}
        }
        self.hosts = {}
        self.services = {}
        self.loaded_hosts = False
        self.loaded_services = False

    # Common functions
    def do_loop_turn(self):
        """This function is called/used when you need a module with
        a loop function (and use the parameter 'external': True)
        """
        logger.info("[Backend Broker] In loop")
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

        try:
            self.backend.login(username, password, generate)
            self.backend_connected = True
        except BackendException as e:
            logger.warning("[Backend Arbiter] Alignak backend is not available for login. "
                           "No backend connection.")
            logger.warning("[Backend Arbiter] Exception: %s", str(e))
            self.backend_connected = False

    def backendConnection(self):
        """
        Backend connection to check live state update is allowed

        :return: True/False
        """
        params = {'where': '{"token":"%s"}' % self.backend.token}
        users = self.backend.get('user', params)
        for item in users['_items']:
            return item['can_update_livestate']

        logger.error("[Backend Broker] Configured user account is not allowed for this module")
        return False

    def get_refs(self, type_data):
        """
        Get the _id in the backend for hosts and services

        :param type_data: livestate type to get: livestate_host or livestate_service
        :type type_data: str
        :return: None
        """
        if type_data == 'livestate_host':
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
            self.loaded_hosts = True
        elif type_data == 'livestate_service':
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
                self.mapping['service'][''.join([hosts[item['host']],
                                                 item['name']])] = item['_id']

                self.ref_live['service'][item['_id']] = {
                    '_id': item['_id'],
                    '_etag': item['_etag'],
                    '_realm': item['_realm'],
                    'initial_state': item['ls_state'],
                    'initial_state_type': item['ls_state_type']
                }
            self.loaded_services = True

    def update(self, data, obj_type):
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

        logger.debug("Got data to update: %s - %s", obj_type, data)

        if obj_type == 'host':
            if data['host_name'] in self.mapping['host']:
                # Received data for an host:
                # {
                # u'last_time_unreachable': 0, u'last_problem_id': 0, u'check_type': 1,
                # u'retry_interval': 0,u'last_event_id': 0, u'problem_has_been_acknowledged': False,
                # u'command_name': u'nsca_host_dead', u'last_state': u'UP', u'latency': 0,
                # u'last_state_type': u'HARD', u'last_hard_state_change': 0.0,
                # u'last_time_up': 1473597379, u'percent_state_change': 0.0, u'state': u'UP',
                # u'last_chk': 1473597379,
                # u'last_state_id': 0, u'end_time': 0, u'timeout': 0, u'current_event_id': 0,
                # u'execution_time': 0.0, u'start_time': 0, u'return_code': 0,
                # u'state_type': u'HARD', u'state_id': 0, u'in_checking': False,
                # u'early_timeout': 0,
                # u'in_scheduled_downtime': False, u'attempt': 1, u'state_type_id': 1,
                # u'acknowledgement_type': 1, u'last_state_change': 0.0, u'last_time_down': 0,
                # 'instance_id': u'd2d402f5de244d95b10d1b47d9891710', u'long_output': u'',
                # u'current_problem_id': 0, u'host_name': u'fvc320', u'check_interval': 0,
                # u'output': u'No message', u'has_been_checked': 1, u'perf_data': u''
                # }
                data_to_update = {
                    'ls_state': data['state'],
                    'ls_state_id': data['state_id'],
                    'ls_state_type': data['state_type'],
                    'ls_last_check': data['last_chk'],
                    'ls_last_state': data['last_state'],
                    'ls_last_state_type': data['last_state_type'],
                    'ls_output': data['output'],
                    'ls_long_output': data['long_output'],
                    'ls_perf_data': data['perf_data'],
                    'ls_acknowledged': data['problem_has_been_acknowledged'],
                    'ls_downtimed': data['in_scheduled_downtime'],
                    'ls_latency': data['latency']
                }

                h_id = self.mapping['host'][data['host_name']]
                if 'initial_state' in self.ref_live['host'][h_id]:
                    data_to_update['ls_last_state'] = self.ref_live['host'][h_id]['initial_state']
                    data_to_update['ls_last_state_type'] = \
                        self.ref_live['host'][h_id]['initial_state_type']
                    del self.ref_live['host'][h_id]['initial_state']
                    del self.ref_live['host'][h_id]['initial_state_type']

                data_to_update['_realm'] = self.ref_live['host'][h_id]['_realm']
                logger.debug("[Backend Broker] host live state data: %s", data_to_update)

                # Update live state
                ret = self.send_to_backend('livestate_host', data['host_name'], data_to_update)
                if ret:
                    counters['livestate_host'] += 1

                # Add an host log
                data_to_update['ls_state_changed'] = (
                    data_to_update['ls_state'] != data_to_update['ls_last_state']
                )
                data_to_update['host'] = self.mapping['host'][data['host_name']]
                data_to_update['service'] = None

                # Rename ls_ keys...
                del data_to_update['ls_downtimed']
                for key in data_to_update:
                    if key.startswith('ls_'):
                        data_to_update[key[3:]] = data_to_update[key]
                        del data_to_update[key]

                ret = self.send_to_backend('log_host', data['host_name'], data_to_update)
                if ret:
                    counters['log_host'] += 1
        elif obj_type == 'service':
            service_name = ''.join([data['host_name'], data['service_description']])
            if service_name in self.mapping['service']:
                # Received data for a service:
                # {
                # u'last_problem_id': 0, u'check_type': 0, u'retry_interval': 2,
                # u'last_event_id': 0, u'problem_has_been_acknowledged': False,
                # u'last_time_critical': 1473597376,
                # u'last_time_warning': 0, u'command_name': u'check_nrpe', u'last_state': u'OK',
                # u'latency': 2.4609699249, u'current_event_id': 1, u'last_state_type': u'HARD',
                # u'last_hard_state_change': 0.0, u'percent_state_change': 4.1,
                # u'state': u'CRITICAL',
                # u'last_chk': 1473597375, u'last_state_id': 0, u'host_name': u'denice',
                # u'check_interval': 5, u'last_time_unknown': 0, u'execution_time': 0.1133639812,
                # u'start_time': 0, u'return_code': 2, u'state_type': u'SOFT', u'state_id': 2,
                # u'service_description': u'Disk hda1', u'in_checking': False, u'early_timeout': 0,
                # u'in_scheduled_downtime': False, u'attempt': 1, u'state_type_id': 0,
                # u'acknowledgement_type': 1, u'last_state_change': 1473597376.147903,
                # 'instance_id': u'3ac88dd0c1c04b37a5d181622e93b5bc', u'long_output': u'',
                # u'current_problem_id': 1, u'last_time_ok': 0, u'timeout': 0,
                # u'output': u"NRPE: Command 'check_hda1' not defined", u'has_been_checked': 1,
                # u'perf_data': u'', u'end_time': 0
                # }
                data_to_update = {
                    'ls_state': data['state'],
                    'ls_state_id': data['state_id'],
                    'ls_state_type': data['state_type'],
                    'ls_last_check': data['last_chk'],
                    'ls_last_state': data['last_state'],
                    'ls_last_state_type': data['last_state_type'],
                    'ls_output': data['output'],
                    'ls_long_output': data['long_output'],
                    'ls_perf_data': data['perf_data'],
                    'ls_acknowledged': data['problem_has_been_acknowledged'],
                    'ls_downtimed': data['in_scheduled_downtime'],
                    'ls_execution_time': data['execution_time'],
                    'ls_latency': data['latency']
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
                logger.debug("[Backend Broker] service live state data: %s", data_to_update)

                # Update live state
                ret = self.send_to_backend('livestate_service', service_name, data_to_update)
                if ret:
                    counters['livestate_service'] += 1

                # Add a service log
                data_to_update['ls_state_changed'] = (
                    data_to_update['ls_state'] != data_to_update['ls_last_state']
                )
                data_to_update['host'] = self.mapping['host'][data['host_name']]
                data_to_update['service'] = self.mapping['service'][service_name]

                # Rename ls_ keys...
                del data_to_update['ls_downtimed']
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
            logger.error("[Backend Broker] Alignak backend connection is not available. "
                         "Skipping objects update.")
            return

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
                if response['_status'] == 'ERR':
                    logger.error('[Backend Broker] %s', response['_issues'])
                    ret = False
                else:
                    self.ref_live['host'][self.mapping['host'][name]]['_etag'] = response['_etag']
            except BackendException as e:
                logger.error('[Backend Broker] Patch livestate host %s has error: %s',
                             self.mapping['host'][name],
                             str(e))
                logger.error('[Backend Broker] Data: %s', data)
                logger.error('[Backend Broker] Response: %s', e.response)
        elif type_data == 'livestate_service':
            headers['If-Match'] = self.ref_live['service'][self.mapping['service'][name]]['_etag']
            try:
                response = self.backend.patch(
                    'service/%s' % self.ref_live['service'][self.mapping['service'][name]]['_id'],
                    data, headers, True)
                if response['_status'] == 'ERR':
                    logger.error('[Backend Broker] %s', response['_issues'])
                    ret = False
                else:
                    self.ref_live['service'][self.mapping['service'][name]]['_etag'] = response[
                        '_etag']
            except BackendException as e:
                logger.error('[Backend Broker] Patch livestate service %s has error: %s',
                             self.mapping['service'][name], str(e))
                logger.error('[Backend Broker] Data: %s', data)
                logger.error('[Backend Broker] Response: %s', e.response)
        elif type_data == 'log_host':
            try:
                response = self.backend.post('logcheckresult', data)
            except BackendException as e:
                logger.error('[Backend Broker] Post logcheckresult of host %s has error: %s',
                             self.mapping['host'][name], str(e))
                logger.error('[Backend Broker] Data: %s', data)
                logger.error('[Backend Broker] Response: %s', e.response)
                ret = False
        elif type_data == 'log_service':
            try:
                response = self.backend.post('logcheckresult', data)
            except BackendException as e:
                logger.error('[Backend Broker] Post logcheckresult of service %s has error: %s',
                             self.mapping['service'][name], str(e))
                logger.error('[Backend Broker] Data: %s', data)
                logger.error('[Backend Broker] Response: %s', e.response)
                ret = False
        return ret

    def manage_brok(self, queue):
        """
        We get the data to manage

        :param queue: Brok object
        :type queue: object
        :return: None
        """
        if not self.logged_in:
            logger.debug("[Backend Broker] Not logged-in, ignoring broks...")
            return

        if not self.loaded_hosts:
            self.get_refs('livestate_host')
        if not self.loaded_services:
            self.get_refs('livestate_service')

        if queue.type == 'host_check_result':
            self.update(queue.data, 'host')
        elif queue.type == 'service_check_result':
            self.update(queue.data, 'service')

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
            logger.debug("[Backend Broker] queue length: %s", self.to_q.qsize())
            start = time.time()
            l = self.to_q.get()
            for b in l:
                b.prepare()
                self.manage_brok(b)

            logger.debug("[Backend Broker] time to manage %s broks (%d secs)", len(l),
                         time.time() - start)

        logger.info("stopping...")
        logger.info("stopped")
