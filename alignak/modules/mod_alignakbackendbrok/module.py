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
This module is used to send logs and livestate to alignak-backend with broker
"""

import time
import ujson

# pylint: disable=F0401
from alignak.basemodule import BaseModule
# pylint: disable=F0401
from alignak.log import logger
from alignak.modules.mod_alignakbackendsched.alignakbackend import Backend


# pylint: disable=C0103
properties = {
    'daemons': ['broker'],
    'type': 'alignakbackendbrok',
    'external': True,
    }


def get_instance(mod_conf):
    """Return a module instance for the plugin manager

    :param mod_conf: Configuration object
    :type mod_conf: object
    :return: AlignakBackendArbit instance
    :rtype: object
    """
    logger.info("[Alignak Backend Brok] Get a Alignak log & livestate module for plugin %s"
                % mod_conf.get_name())
    instance = AlignakBackendBrok(mod_conf)
    return instance


class AlignakBackendBrok(BaseModule):
    """ This class is used to send logs and livestate to alignak-backend
    """

    def __init__(self, mod_conf):
        BaseModule.__init__(self, mod_conf)
        self.url = getattr(mod_conf, 'api_url', 'http://localhost:5000')
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

    def endpoint(self, resource):
        """
        Produce endpoint with base url + the resource

        :param resource: resource value
        :type resource: str
        :return: the complete endpoint
        :rtype: str
        """
        return '%s/%s' % (self.url, resource)

    def get_refs(self, type_data):
        """
        Get the _id in the backend for hosts and services

        :param type_data: livestate type to get: livehost or liveservice
        :type type_data: str
        :return: None
        """
        backend = Backend()
        if type_data == 'livehost':
            content = backend.method_get(self.endpoint('host?projection={"host_name":1}'
                                                       '&where={"register":true}'))
            hosts = {}
            for item in content:
                hosts[item['_id']] = item['host_name']
                self.mapping['host'][item['host_name']] = item['_id']
            # get all livehost
            contentlh = backend.method_get(self.endpoint('livehost?embedded={"host_name":1}'
                                                         '&projection={"host_name":1}'))
            for item in contentlh:
                self.ref_live['host'][item['host_name']['_id']] = {
                    '_id': item['_id'],
                    '_etag': item['_etag']
                }
                del hosts[item['host_name']['_id']]
            # create livehost for hosts not added
            for key_id in hosts:
                data = {'host_name': key_id}
                headers = {'Content-Type': 'application/json'}
                contentadd = backend.method_post(self.endpoint('livehost'), ujson.dumps(data),
                                                 headers=headers)
                self.ref_live['host'][key_id] = {
                    '_id': contentadd['_id'],
                    '_etag': contentadd['_etag']
                }
        elif type_data == 'liveservice':
            content = backend.method_get(self.endpoint('service?projection={'
                                                       '"service_description":1,"host_name":1}'
                                                       '&embedded={"host_name":1}'
                                                       '&where={"register":true}'))
            services = {}
            for item in content:
                services[item['_id']] = item['service_description']
                self.mapping['service'][''.join([item['host_name']['host_name'],
                                                 item['service_description']])] = item['_id']
            # get all liveservice
            contentls = backend.method_get(self.endpoint('liveservice?'
                                                         'embedded={"service_description":1}'
                                                         '&projection={"service_description":1}'))
            for item in contentls:
                self.ref_live['service'][item['service_description']['_id']] = {
                    '_id': item['_id'],
                    '_etag': item['_etag']
                }
                del services[item['service_description']['_id']]
            # create liveservice for services not added
            for key_id in services:
                data = {'service_description': key_id}
                headers = {'Content-Type': 'application/json'}
                contentadd = backend.method_post(self.endpoint('liveservice'), ujson.dumps(data),
                                                 headers=headers)
                self.ref_live['service'][key_id] = {
                    '_id': contentadd['_id'],
                    '_etag': contentadd['_etag']
                }

    def update(self, data, obj_type):
        """
        Update livehost and liveservice

        :param data: dictionary of data from scheduler
        :type data: dict
        :param obj_type: type of data (host | service)
        :type obj_type: str
        :return: Counters of updated or add data to alignak backend
        :rtype: dict
        """
        start_time = time.time()
        counters = {
            'livehost': 0,
            'liveservice': 0,
            'loghost': 0,
            'logservice': 0
        }

        if obj_type == 'host':
            if data['host_name'] in self.mapping['host']:
                data_to_update = {
                    'state': data['state'],
                    'state_type': data['state_type'],
                    'last_check': data['last_chk'],
                    'output': data['output'],
                    'long_output': data['long_output'],
                    'perf_data': data['perf_data'],
                    'acknowledged': data['problem_has_been_acknowledged'],
                }
                # Update live state
                ret = self.send_to_backend('livehost', data['host_name'], data_to_update)
                if ret:
                    counters['livehost'] += 1
                # Add log
                ret = self.send_to_backend('loghost', data['host_name'], data_to_update)
                if ret:
                    counters['loghost'] += 1
        elif obj_type == 'service':
            service_name = ''.join([data['host_name'], data['service_description']])
            if service_name in self.mapping['service']:
                data_to_update = {
                    'state': data['state'],
                    'state_type': data['state_type'],
                    'last_check': data['last_chk'],
                    'output': data['output'],
                    'long_output': data['long_output'],
                    'perf_data': data['perf_data'],
                    'acknowledged': data['problem_has_been_acknowledged'],
                }
                # Update live state
                ret = self.send_to_backend('liveservice', service_name, data_to_update)
                if ret:
                    counters['liveservice'] += 1
                # Add log
                self.send_to_backend('logservice', service_name, data_to_update)
                if ret:
                    counters['logservice'] += 1
        if (counters['livehost'] + counters['liveservice']) > 0:
            logger.debug("--- %s seconds ---" % (time.time() - start_time))
        return counters

    def send_to_backend(self, type_data, name, data):
        """
        Send data to alignak backend livehost or liveservice

        :param type_data: one of ['livehost', 'liveservice', 'loghost', 'logservice']
        :type type_data: str
        :param name: name of host or service
        :type name: str
        :param data: dictionary with data to add / update
        :type data: dict
        :return: True if send is ok, False otherwise
        :rtype: bool
        """
        backend = Backend()
        headers = {
            'Content-Type': 'application/json',
        }
        ret = True
        if type_data == 'livehost':
            headers['If-Match'] = self.ref_live['host'][self.mapping['host'][name]]['_etag']
            response = backend.method_patch(
                self.endpoint('livehost/%s'
                              % self.ref_live['host'][self.mapping['host'][name]]['_id']),
                ujson.dumps(data),
                headers=headers
            )
            if response['_status'] == 'ERR':
                logger.error(response['_issues'])
                ret = False
            else:
                self.ref_live['host'][self.mapping['host'][name]]['_etag'] = response['_etag']
        elif type_data == 'liveservice':
            headers['If-Match'] = self.ref_live['service'][self.mapping['service'][name]]['_etag']
            response = backend.method_patch(
                self.endpoint('liveservice/%s'
                              % self.ref_live['service'][self.mapping['service'][name]]['_id']),
                ujson.dumps(data),
                headers=headers
            )
            if response['_status'] == 'ERR':
                logger.error(response['_issues'])
                ret = False
            else:
                self.ref_live['service'][self.mapping['service'][name]]['_etag'] = response['_etag']
        elif type_data == 'loghost':
            data['host_name'] = self.mapping['host'][name]
            response = backend.method_post(
                self.endpoint('loghost'), ujson.dumps(data), headers=headers
            )
            if response['_status'] == 'ERR':
                logger.error(response['_issues'])
                ret = False
        elif type_data == 'logservice':
            data['service_description'] = self.mapping['service'][name]
            response = backend.method_post(
                self.endpoint('logservice'), ujson.dumps(data), headers=headers
            )
            if response['_status'] == 'ERR':
                logger.error(response['_issues'])
                ret = False
        return ret

    def manage_brok(self, queue):
        """
        We get the data to manage

        :param queue: Brok object
        :type queue: object
        :return: None
        """

        if not self.ref_live['host']:
            self.get_refs('livehost')
        if not self.ref_live['service']:
            self.get_refs('liveservice')

        if queue.type == 'host_check_result':
            self.update(queue.data, 'host')
        elif queue.type == 'service_check_result':
            self.update(queue.data, 'service')

    def main(self):
        """
        Main function where send queue to manage_brok function

        :return: None
        """
        self.set_proctitle(self.name)
        self.set_exit_handler()
        while not self.interrupted:
            logger.debug("[Alignak Backend Brok] queue length: %s", self.to_q.qsize())
            start = time.time()
            l = self.to_q.get()
            for b in l:
                b.prepare()
                self.manage_brok(b)

            logger.debug("[Alignak Backend Brok] time to manage %s broks (%d secs)", len(l),
                         time.time() - start)
