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

    def __init__(self, mod_conf):
        """
        Module initialization

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
        logger.info(
            "Number of processes used by backend client: %s", self.client_processes
        )

        self.url = getattr(mod_conf, 'api_url', 'http://localhost:5000')
        self.backend = Backend(self.url, self.client_processes)
        self.backend.token = getattr(mod_conf, 'token', '')
        self.backend_connected = False
        if self.backend.token == '':
            self.getToken(getattr(mod_conf, 'username', ''), getattr(mod_conf, 'password', ''),
                          getattr(mod_conf, 'allowgeneratetoken', False))

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

        Note: We are obliged to define this method (even if not called!) because
        it is an abstract function in the base class
        """
        logger.info("In loop")
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
            self.backend_connected = self.backend.login(username, password, generate)
        except BackendException as exp:
            logger.warning("Alignak backend is not available for login. "
                           "No backend connection.")
            logger.exception("Exception: %s", exp)
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

        logger.error("Configured user account is not allowed for this module")
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
                    data_to_update['ls_last_state'] = self.ref_live['host'][h_id]['initial_state']
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
            service_name = ''.join([data['host_name'], data['service_description']])
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
                    logger.error('%s', response['_issues'])
                    ret = False
                else:
                    self.ref_live['host'][self.mapping['host'][name]]['_etag'] = response['_etag']
            except BackendException as exp:
                logger.error('Patch livestate for host %s error', self.mapping['host'][name])
                logger.error('Data: %s', data)
                logger.exception("Exception: %s", exp)
        elif type_data == 'livestate_service':
            headers['If-Match'] = self.ref_live['service'][self.mapping['service'][name]]['_etag']
            try:
                response = self.backend.patch(
                    'service/%s' % self.ref_live['service'][self.mapping['service'][name]]['_id'],
                    data, headers, True)
                if response['_status'] == 'ERR':
                    logger.error('%s', response['_issues'])
                    ret = False
                else:
                    self.ref_live['service'][self.mapping['service'][name]]['_etag'] = response[
                        '_etag']
            except BackendException as exp:
                logger.error('Patch livestate for service %s error', self.mapping['service'][name])
                logger.error('Data: %s', data)
                logger.exception("Exception: %s", exp)
        elif type_data == 'log_host':
            try:
                response = self.backend.post('logcheckresult', data)
            except BackendException as exp:
                logger.error('Post logcheckresult for host %s error', self.mapping['host'][name])
                logger.error('Data: %s', data)
                logger.exception("Exception: %s", exp)
                ret = False
        elif type_data == 'log_service':
            try:
                response = self.backend.post('logcheckresult', data)
            except BackendException as exp:
                logger.error('Post logcheckresult for service %s error',
                             self.mapping['service'][name])
                logger.error('Data: %s', data)
                logger.exception("Exception: %s", exp)
                logger.error('Error detail: %s, %s, %s', exp.code, exp.message, exp.response)
                ret = False
        return ret

    def manage_brok(self, brok):
        """
        We get the data to manage

        :param brok: Brok object
        :type brok: object
        :return: None
        """
        if not self.logged_in:
            logger.debug("Not logged-in, ignoring broks...")
            return

        try:
            logger.debug("Received a brok :%s", brok.type)
            if brok.type == 'new_conf':
                logger.info("Got configuration")
                self.get_refs('livestate_host')
                self.get_refs('livestate_service')
                logger.info("Hosts/services references reloaded")

            if brok.type == 'host_check_result':
                self.update(brok.data, 'host')
            elif brok.type == 'service_check_result':
                self.update(brok.data, 'service')
            elif brok.type in ['acknowledge_raise', 'acknowledge_expire', 'downtime_raise',
                               'downtime_raise']:
                self.update_actions(brok)
        except Exception as exp:
            logger.exception("Manage brok exception: %s", exp)

    def update_actions(self, brok):
        """We manage the acknowledge and downtime broks

        :param brok: the brok
        :type brok:
        :return: None
        """
        if brok.data['host'] not in self.mapping['host']:
            return
        if 'service' in brok.data:
            service_name = ''.join([brok.data['host'], brok.data['service']])
            if service_name not in self.mapping['service']:
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
            'host': self.mapping['host'][brok.data['host']],
            'comment': brok.data['comment'],
            'service': None
        }

        if 'service' in brok.data:
            # it's a service
            self.send_to_backend('livestate_service', service_name, data_to_update)
            where['service'] = self.mapping['service'][service_name]
        else:
            # it's a host
            self.send_to_backend('livestate_host', brok.data['host'], data_to_update)

        params = {
            'where': json.dumps(where)
        }
        actions = self.backend.get_all(endpoint, params)
        if len(actions['_items']) > 0:
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
            if len(users['_items']) > 0:
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
            logger.debug("queue length: %s", self.to_q.qsize())
            start = time.time()
            l = self.to_q.get()
            for b in l:
                b.prepare()
                self.manage_brok(b)

            logger.debug("time to manage %s broks (%d secs)", len(l), time.time() - start)

        logger.info("stopping...")
        logger.info("stopped")
