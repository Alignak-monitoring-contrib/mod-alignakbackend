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
# pylint: disable=F0401
from alignak.basemodule import BaseModule
# pylint: disable=F0401
from alignak.log import logger
from alignak_backend_client.client import Backend


# pylint: disable=C0103
properties = {
    'daemons': ['scheduler'],
    'type': 'alignakbackendsched',
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
        for host in response:
            all_data['hosts'][host['host']] = host
        response = self.backend.get_all('retentionservice')
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
        headers = {'Content-Type': 'application/json'}
        data_to_save = scheduler.get_retention_data()
        # clean all hosts first
        self.backend.delete('retentionhost', headers)
        # Add all hosts after
        for host in data_to_save['hosts']:
            data_to_save['hosts'][host]['host'] = host
            self.backend.post('retentionhost', data_to_save['hosts'][host], headers)

        # clean all services first
        self.backend.delete('retentionservice', headers)
        # Add all services after
        for service in data_to_save['services']:
            data_to_save['services'][service]['service'] = service
            self.backend.post('retentionservice', data_to_save['services'][service], headers)
