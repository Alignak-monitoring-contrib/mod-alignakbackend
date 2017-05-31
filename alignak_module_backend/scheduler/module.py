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
This module is used to manage retention and livestate to alignak-backend with scheduler
"""

import time
import logging

from alignak.basemodule import BaseModule
from alignak_backend_client.client import Backend, BackendException

logger = logging.getLogger('alignak.module')  # pylint: disable=invalid-name

# pylint: disable=C0103
properties = {
    'daemons': ['scheduler'],
    'type': 'backend_scheduler',
    'external': False,
    'phases': ['running'],
}


def get_instance(mod_conf):
    """
    Return a module instance for the modules manager

    :param mod_conf: the module properties as defined globally in this file
    :return:
    """
    logger.info("Give an instance of %s for alias: %s", mod_conf.python_name, mod_conf.module_alias)

    return AlignakBackendScheduler(mod_conf)


class AlignakBackendScheduler(BaseModule):
    """
    This class is used to send live states to alignak-backend
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
        self.backend_errors_count = 0
        self.backend_username = getattr(mod_conf, 'username', '')
        self.backend_password = getattr(mod_conf, 'password', '')
        self.backend_generate = getattr(mod_conf, 'allowgeneratetoken', False)

        if not self.backend.token:
            self.getToken()

    # Common functions
    def do_loop_turn(self):
        """This function is called/used when you need a module with
        a loop function (and use the parameter 'external': True)
        """
        logger.info("[Backend Scheduler] In loop")
        time.sleep(1)

    def getToken(self):
        """
        Authenticate and get the token

        :return: None
        """
        generate = 'enabled'
        if not self.backend_generate:
            generate = 'disabled'

        try:
            self.backend_connected = self.backend.login(self.backend_username,
                                                        self.backend_password,
                                                        generate)
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
        if not self.backend_connected and self.backend_errors_count > errors_count:
            return True

        return False

    def hook_load_retention(self, scheduler):
        """Load retention data from alignak-backend

        :param scheduler: scheduler instance of alignak
        :type scheduler: object
        :return: None
        """

        all_data = {'hosts': {}, 'services': {}}

        if not self.backend_connected:
            self.getToken()
            if self.raise_backend_alert(errors_count=1):
                logger.warning("Alignak backend connection is not available. "
                               "Loading retention data is not possible.")
                return

        # Get data from the backend
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
        """Save retention data to alignak-backend

        :param scheduler: scheduler instance of alignak
        :type scheduler: object
        :return: None
        """
        if not self.backend_connected:
            self.getToken()
            if self.raise_backend_alert(errors_count=1):
                logger.warning("Alignak backend connection is not available. "
                               "Saving objects is not possible.")
                return

        data_to_save = scheduler.get_retention_data()

        # clean hosts we will re-upload the retention
        response = self.backend.get_all('retentionhost')
        for host in response['_items']:
            if host['host'] in data_to_save['hosts']:
                delheaders = {'If-Match': host['_etag']}
                try:
                    self.backend.delete('/'.join(['retentionhost', host['_id']]),
                                        headers=delheaders)
                except BackendException as exp:  # pragma: no cover - should not happen
                    logger.error('Delete retentionhost error')
                    logger.error('Response: %s', exp.response)
                    logger.exception("Backend exception: %s", exp)
                    self.backend_connected = False

        # Add all hosts after
        for host in data_to_save['hosts']:
            data_to_save['hosts'][host]['host'] = host
            try:
                self.backend.post('retentionhost', data=data_to_save['hosts'][host])
            except BackendException as exp:  # pragma: no cover - should not happen
                logger.error('Post retentionhost error')
                logger.error('Response: %s', exp.response)
                logger.exception("Exception: %s", exp)
                self.backend_connected = False
                return
        logger.info('%d hosts saved in retention', len(data_to_save['hosts']))

        # clean services we will re-upload the retention
        response = self.backend.get_all('retentionservice')
        for service in response['_items']:
            if (service['service'][0], service['service'][1]) in data_to_save['services']:
                delheaders = {'If-Match': service['_etag']}
                try:
                    self.backend.delete('/'.join(['retentionservice', service['_id']]),
                                        headers=delheaders)
                except BackendException as exp:  # pragma: no cover - should not happen
                    logger.error('Delete retentionservice error')
                    logger.error('Response: %s', exp.response)
                    logger.exception("Backend exception: %s", exp)
                    self.backend_connected = False

        # Add all services after
        for service in data_to_save['services']:
            data_to_save['services'][service]['service'] = service
            try:
                self.backend.post('retentionservice', data=data_to_save['services'][service])
            except BackendException as exp:  # pragma: no cover - should not happen
                logger.error('Post retentionservice error')
                logger.error('Response: %s', exp.response)
                logger.exception("Exception: %s", exp)
                self.backend_connected = False
                return
        logger.info('%d services saved in retention', len(data_to_save['services']))
