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

import ujson


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


class AlignakBackendSched(BaseModule):
    """
    This class is used to send live states to alignak-backend
    """

    def __init__(self, modconf):
        BaseModule.__init__(self, modconf)
        self.url = getattr(modconf, 'api_url', 'http://localhost:5000')

    def endpoint(self, resource):
        """
        Produce endpoint with base url + the resource

        :param resource: resource value
        :type resource: str
        :return: the complete endpoint
        :rtype: str
        """
        return '%s/%s' % (self.url, resource)

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
