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
This module is used to manage retention and livestate to alignak-backend with scheduler
"""

# pylint: disable=F0401
from alignak.basemodule import BaseModule
# pylint: disable=F0401
from alignak.log import logger
from alignak.modules.mod_alignakbackendsched.alignakbackend import Backend

import time
import ujson
import copy


# pylint: disable=C0103
properties = {
    'daemons': ['scheduler'],
    'type': 'alignakbackendsched',
    'external': False,
    'phases': ['running'],
}


def get_instance(mod_conf):
    """ Return a module instance for the plugin manager """
    logger.info("[Alignak Backend Sched] Get a Alignak config module for plugin %s"
                % mod_conf.get_name())

    instance = AlignakBackendSched(mod_conf)
    return instance


class DictDiffer(object):
    """
    Calculate the difference between two dictionaries as:
    (1) items added
    (2) items removed
    (3) keys same in both but changed values
    (4) keys same in both and unchanged values
    """
    def __init__(self, current_dict, past_dict):
        self.current_dict, self.past_dict = current_dict, past_dict
        self.set_current, self.set_past = set(current_dict.keys()), set(past_dict.keys())
        self.intersect = self.set_current.intersection(self.set_past)

    def added(self):
        """
        Get items added

        :return: items added
        :rtype: dict
        """
        return self.set_current - self.intersect

    def removed(self):
        """
        Get items removed

        :return: items removed
        :rtype: dict
        """
        return self.set_past - self.intersect

    def changed(self):
        """
        Get items where value is not same

        :return: items changed
        :rtype: dict
        """
        return set(o for o in self.intersect if self.past_dict[o] != self.current_dict[o])

    def unchanged(self):
        """
        Get items are same on the two dict

        :return: items are same
        :rtype: dict
        """
        return set(o for o in self.intersect if self.past_dict[o] == self.current_dict[o])


class AlignakBackendSched(BaseModule):
    """
    This class is used to send live states to alignak-backend
    """

    def __init__(self, modconf):
        BaseModule.__init__(self, modconf)
        self.url = getattr(modconf, 'api_url', 'http://localhost:5000')
        self.ref_live = {
            'host': {},
            'service': {}
        }
        self.mapping = {
            'host': {},
            'service': {}
        }
        self.hosts = {}
        self.host_prop = {
            'state': {
                'alignak_field': 'state',
                'type': 'text'
            },
            'acknowledged': {
                'alignak_field': '',
                'type': 'bool'
            },
            'last_check': {
                'alignak_field': 'last_chk',
                'type': 'int'
            },
            'last_state_change': {
                'alignak_field': 'last_state_change',
                'type': 'int'
            },
            'output': {
                'alignak_field': 'output',
                'type': 'text'
            },
            'plugin_output': {
                'alignak_field': '',
                'type': 'text'
            },
            'long_output': {
                'alignak_field': 'long_output',
                'type': 'text'
            },
            'return_code': {
                'alignak_field': '',
                'type': 'text'
            },
            'service_description': {
                'alignak_field': '',
                'type': 'text'
            },
            'perf_data': {
                'alignak_field': 'perf_data',
                'type': 'text'
            },
        }

        self.services = {}
        self.service_prop = {
            'service_description': {
                'alignak_field': '',
                'type': 'text'
            },
            'description': {
                'alignak_field': '',
                'type': 'text'
            },
            'state': {
                'alignak_field': 'state',
                'type': 'text'
            },
            'acknowledged': {
                'alignak_field': '',
                'type': 'bool'
            },
            'last_check': {
                'alignak_field': 'last_chk',
                'type': 'int'
            },
            'last_state_change': {
                'alignak_field': 'last_state_change',
                'type': 'float'
            },
            'output': {
                'alignak_field': 'output',
                'type': 'text'
            },
            'plugin_output': {
                'alignak_field': '',
                'type': 'text'
            },
            'long_output': {
                'alignak_field': 'long_output',
                'type': 'text'
            },
            'perf_data': {
                'alignak_field': 'perf_data',
                'type': 'text'
            },
        }

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

    def update_first_time(self, object_type):
        """
        Update livehost and liveservice first time find host and service since last
        alignak restart

        :param object_type: scheduler object
        :type object_type: object
        :return: None
        """
        # Hosts
        for host in object_type.hosts:
            if not host.is_tpl():
                if host.imported_from == 'alignakbackend':
                    if host.host_name not in self.hosts:
                        self.hosts[host.host_name] = {}
                        self.convert_host(host)
                        self.send_to_backend('host', host.host_name, self.hosts[host.host_name])
        # Services
        for service in object_type.services:
            if not service.is_tpl():
                if service.imported_from == 'alignakbackend':
                    if service.get_id() not in self.services:
                        self.services[service.get_id()] = {}
                        self.convert_service(service)
                        self.send_to_backend('service', ''.join([service.host_name,
                                                                 service.service_description]),
                                             self.services[service.get_id()])

    def update_if_diff(self, object_type):
        """
        Update livehost and liveservice first only if properties are different from last update

        :param object_type: scheduler object
        :type object_type: object
        :return: None
        """
        start_time = time.time()
        update = 0
        # check if difference between previous value (in self.hosts) and new value
        # (in object_type.hosts)
        for host in object_type.hosts:
            if not host.is_tpl():
                if host.imported_from == 'alignakbackend':
                    old_host = copy.deepcopy(self.hosts[host.host_name])
                    self.convert_host(host)
                    if old_host != self.hosts[host.host_name]:
                        key_changed = DictDiffer(old_host, self.hosts[host.host_name]).changed()
                        to_send = self.prepare_to_send(key_changed, self.hosts[host.host_name])
                        self.send_to_backend('host', host.host_name, to_send)
                        update += 1

        # check if difference between previous value (in self.services) and new value
        # (in object_type.services)
        for service in object_type.services:
            if not service.is_tpl():
                if service.imported_from == 'alignakbackend':
                    # logger.warning("%s" % (getattr(service, 'last_chk')))
                    old_service = copy.deepcopy(self.services[service.get_id()])
                    self.convert_service(service)
                    # logger.warning("[%s] old: %s  | new: %s" % (service.get_id(),
                    # old_service['last_check'], self.services[service.get_id()]['last_check']))
                    if old_service != self.services[service.get_id()]:
                        key_changed = DictDiffer(old_service,
                                                 self.services[service.get_id()]).changed()
                        to_send = self.prepare_to_send(key_changed,
                                                       self.services[service.get_id()])
                        self.send_to_backend('service', ''.join([service.host_name,
                                                                 service.service_description]),
                                             to_send)
                        update += 1
        if update > 0:
            logger.debug("--- %s seconds ---" % (time.time() - start_time))

    def hook_scheduler_tick(self, object_type):
        """
        Hook called in end of each loop of scheduler

        :param object_type: scheduler object
        :type object_type: object
        :return: None
        """
        if not self.ref_live['host']:
            self.get_refs('livehost')
        if not self.ref_live['service']:
            self.get_refs('liveservice')

        self.update_first_time(object_type)
        self.update_if_diff(object_type)

    def convert_host(self, host):
        """
        Get mapped properties to send to alignak backend and get properties of host
        and put them in dictionary

        :param host: host object
        :type host: object
        :return: None
        """
        for prop, mapping in self.host_prop.iteritems():
            if not mapping['alignak_field'] == "":
                self.hosts[host.host_name].update({prop: getattr(host,
                                                                 str(mapping['alignak_field']))})

    def convert_service(self, service):
        """
        Get mapped properties to send to alignak backend and get properties of service
        and put them in dictionary

        :param service: service object
        :type service: object
        :return: None
        """
        for prop, mapping in self.service_prop.iteritems():
            if not mapping['alignak_field'] == "":
                self.services[service.get_id()][prop] = getattr(service, mapping['alignak_field'])

    @classmethod
    def prepare_to_send(cls, keys, data):
        """
        Create new dictionary with keys defined (keys) from dictionary (data)

        :param keys: set of keys we want
        :type keys: set
        :param data: dictionary with properties
        :type data: dict
        :return: dictionary like data but only with keys specified in keys
        :rtype: dict
        """
        to_send = {}
        for key in keys:
            to_send.update({key: data[key]})
        return to_send

    def send_to_backend(self, type_data, name, data):
        """
        Send data to alignak backend livehost or liveservice

        :param type_data: host | service
        :type type_data: str
        :param name: name of host or service
        :type name: str
        :param data: dictionary with data to add / update
        :type data: dict
        :return: None
        """
        backend = Backend()
        headers = {
            'Content-Type': 'application/json',
            'If-Match': self.ref_live[type_data][self.mapping[type_data][name]]['_etag']
        }
        if type_data == 'host':
            response = backend.method_patch(
                self.endpoint('livehost/%s'
                              % self.ref_live['host'][self.mapping['host'][name]]['_id']),
                ujson.dumps(data),
                headers=headers
            )
            if response['_status'] == 'ERR':
                logger.error(response['_issues'])
            else:
                self.ref_live[type_data][self.mapping[type_data][name]]['_etag'] = response['_etag']
        elif type_data == 'service':
            response = backend.method_patch(
                self.endpoint('liveservice/%s'
                              % self.ref_live['service'][self.mapping['service'][name]]['_id']),
                ujson.dumps(data),
                headers=headers
            )
            if response['_status'] == 'ERR':
                logger.error(response['_issues'])
            else:
                self.ref_live[type_data][self.mapping[type_data][name]]['_etag'] = response['_etag']

    def hook_load_retention(self, scheduler):
        """
        Load retention data from alignak-backend

        :param scheduler: scheduler instance of alignak
        :type scheduler: object
        :return: None
        """
        backend = Backend()
        all_data = {'hosts': {}, 'services': {}}
        response = backend.method_get(self.endpoint('retentionhost'))
        for host in response:
            all_data['hosts'][host['host']] = host
        response = backend.method_get(self.endpoint('retentionservice'))
        for service in response:
            all_data['services'][(service['service'][0], service['service'][1])] = service

        scheduler.restore_retention_data(all_data)

    def hook_save_retention(self, scheduler):
        """
        Save retention data from alignak-backend

        :param scheduler: scheduler instance of alignak
        :type scheduler: object
        :return: None
        """
        backend = Backend()
        headers = {'Content-Type': 'application/json'}
        data_to_save = scheduler.get_retention_data()
        # clean all hosts first
        backend.method_delete(self.endpoint('retentionhost'))
        # Add all hosts after
        for host in data_to_save['hosts']:
            data_to_save['hosts'][host]['host'] = host
            backend.method_post(self.endpoint('retentionhost'),
                                ujson.dumps(data_to_save['hosts'][host]),
                                headers=headers)

        # clean all services first
        backend.method_delete(self.endpoint('retentionservice'))
        # Add all services after
        for service in data_to_save['services']:
            data_to_save['services'][service]['service'] = service
            backend.method_post(self.endpoint('retentionservice'),
                                ujson.dumps(data_to_save['services'][service]),
                                headers=headers)
