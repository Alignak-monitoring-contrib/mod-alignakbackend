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

import time
from alignak_backend_client.client import Backend, BackendException
# pylint: disable=wrong-import-order
from alignak.basemodule import BaseModule
from alignak.log import logger


# pylint: disable=C0103
properties = {
    'daemons': ['scheduler'],
    'type': 'backend_scheduler',
    'external': False,
    'phases': ['running'],
}


def get_instance(mod_conf):
    """ Return a module instance for the plugin manager """
    logger.info("[Backend Scheduler] Get a Alignak config module for plugin %s",
                mod_conf.get_name())

    instance = AlignakBackendSched(mod_conf)
    return instance


class AlignakBackendSched(BaseModule):
    """
    This class is used to send live states to alignak-backend
    """

    def __init__(self, modconf):
        BaseModule.__init__(self, modconf)
        self.url = getattr(modconf, 'api_url', 'http://localhost:5000')
        self.backend = Backend(self.url)
        self.backend.token = getattr(modconf, 'token', '')
        if self.backend.token == '':
            self.getToken(getattr(modconf, 'username', ''), getattr(modconf, 'password', ''),
                          getattr(modconf, 'allowgeneratetoken', False))

    # Common functions
    def do_loop_turn(self):
        """This function is called/used when you need a module with
        a loop function (and use the parameter 'external': True)
        """
        logger.info("[Backend Scheduler] In loop")
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

    def hook_load_retention(self, scheduler):
        """
        Load retention data from alignak-backend

        :param scheduler: scheduler instance of alignak
        :type scheduler: object
        :return: None
        """
        all_data = {'hosts': {}, 'services': {}}
        response = self.backend.get_all('retentionhost')
        for host in response['_items']:
            # clean unusable keys
            hostname = host['host']
            for key in ['_created', '_etag', '_id', '_links', '_updated', 'host']:
                del host[key]
            all_data['hosts'][hostname] = host
        response = self.backend.get_all('retentionservice')
        for service in response['_items']:
            # clean unusable keys
            servicename = (service['service'][0], service['service'][1])
            for key in ['_created', '_etag', '_id', '_links', '_updated', 'service']:
                del service[key]
            all_data['services'][servicename] = service

        scheduler.restore_retention_data(all_data)

    def hook_save_retention(self, scheduler):
        """
        Save retention data from alignak-backend

        :param scheduler: scheduler instance of alignak
        :type scheduler: object
        :return: None
        """
        data_to_save = scheduler.get_retention_data()

        # clean hosts we will re-upload the retention
        response = self.backend.get_all('retentionhost')
        for host in response['_items']:
            if host['host'] in data_to_save['hosts']:
                delheaders = {'If-Match': host['_etag']}
                self.backend.delete('/'.join(['retentionhost', host['_id']]), headers=delheaders)

        # Add all hosts after
        for host in data_to_save['hosts']:
            data_to_save['hosts'][host]['host'] = host
            try:
                self.backend.post('retentionhost', data=data_to_save['hosts'][host])
            except BackendException as e:
                logger.error('[Backend Scheduler] Post retentionhost of host has error: %s',
                             str(e))
                logger.error('[Backend Scheduler] Response: %s', e.response)
                return
        logger.info('[Backend Scheduler] %d hosts saved in retention',
                    len(data_to_save['hosts']))

        # clean services we will re-upload the retention
        response = self.backend.get_all('retentionservice')
        for service in response['_items']:
            if (service['service'][0], service['service'][1]) in data_to_save['services']:
                delheaders = {'If-Match': service['_etag']}
                self.backend.delete('/'.join(['retentionservice', service['_id']]),
                                    headers=delheaders)

        # Add all services after
        for service in data_to_save['services']:
            data_to_save['services'][service]['service'] = service
            try:
                self.backend.post('retentionservice', data=data_to_save['services'][service])
            except BackendException as e:
                logger.error('[Backend Scheduler] Post retentionservice of service has error: %s',
                             str(e))
                logger.error('[Backend Scheduler] Response: %s', e.response)
                return
        logger.info('[Backend Scheduler] %d services saved in retention',
                    len(data_to_save['services']))
