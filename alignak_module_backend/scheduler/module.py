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
This module is used to manage retention and livestate to alignak-backend with scheduler
"""

import time
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
        logger.info(
            "Number of processes used by backend client: %s", self.client_processes
        )

        self.backend_count = int(getattr(mod_conf, 'backend_count', '50'))
        logger.info("backend pagination count: %d items", self.backend_count)

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

    # Common functions
    def do_loop_turn(self):
        """This function is called/used when you need a module with
        a loop function (and use the parameter 'external': True)
        """
        logger.info("[Backend Scheduler] In loop")
        time.sleep(1)

    def getToken(self):
        """Authenticate and get the token

        :return: None
        """
        generate = 'enabled'
        if not self.backend_generate:
            generate = 'disabled'

        try:
            start = time.time()
            self.backend_connected = self.backend.login(self.backend_username,
                                                        self.backend_password,
                                                        generate)
            self.statsmgr.counter('backend-login', 1)
            self.statsmgr.timer('backend-login-time', time.time() - start)
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
                return None

        if not self.backend_connected:
            return None

        # Get data from the backend
        try:
            start = time.time()
            params = {"max_results": self.backend_count}
            response = self.backend.get_all('alignakretention', params)
            for host in response['_items']:
                # clean unusable keys
                hostname = host['host']
                if 'retention_services' in host:
                    for service in host['retention_services']:
                        all_data['services'][(host['host'], service)] = \
                            host['retention_services'][service]
                for key in ['_created', '_etag', '_id', '_links', '_updated', 'host',
                            'retention_services', '_user', 'schema_version']:
                    if key in host:
                        del host[key]
                all_data['hosts'][hostname] = host

            logger.info('%d hosts loaded from retention', len(all_data['hosts']))
            self.statsmgr.counter('retention-load.hosts', len(all_data['hosts']))
            logger.info('%d services loaded from retention', len(all_data['services']))
            self.statsmgr.counter('retention-load.services', len(all_data['services']))
            self.statsmgr.timer('retention-load.time', time.time() - start)

            scheduler.restore_retention_data(all_data)
        except BackendException:
            self.backend_connected = False
            self.backend_errors_count += 1
            logger.warning("Alignak backend connection fails. Check and fix your configuration")
            return False

        return True

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
                return None

        if not self.backend_connected:
            return None

        try:
            data_to_save = scheduler.get_retention_data()
            start_time = time.time()

            # get list of retention_data
            params = {"max_results": self.backend_count}
            response = self.backend.get_all('alignakretention', params)
            db_hosts = {}
            for host in response['_items']:
                db_hosts[host['host']] = host

            # add services in the hosts
            for host in data_to_save['hosts']:
                data_to_save['hosts'][host]['retention_services'] = {}
                data_to_save['hosts'][host]['host'] = host
            if 'services' in data_to_save:
                # Scheduler old-school: two separate dictionaries!
                for service in data_to_save['services']:
                    data_to_save['hosts'][service[0]]['retention_services'][service[1]] = \
                        data_to_save['services'][service]

            for host in data_to_save['hosts']:
                if host in db_hosts:
                    # if host in retention_data, PUT
                    headers = {'Content-Type': 'application/json'}
                    headers['If-Match'] = db_hosts[host]['_etag']
                    try:
                        logger.debug('Host retention data: %s', data_to_save['hosts'][host])
                        self.backend.put('alignakretention/%s' % (db_hosts[host]['_id']),
                                         data_to_save['hosts'][host], headers, True)
                    except BackendException as exp:  # pragma: no cover - should not happen
                        logger.error('Put alignakretention error')
                        logger.error('Response: %s', exp.response)
                        logger.exception("Exception: %s", exp)
                        self.backend_connected = False
                        return False
                else:
                    # if not host in retention_data, POST
                    try:
                        logger.debug('Host retention data: %s', data_to_save['hosts'][host])
                        self.backend.post('alignakretention', data=data_to_save['hosts'][host])
                    except BackendException as exp:  # pragma: no cover - should not happen
                        logger.error('Post alignakretention error')
                        logger.error('Response: %s', exp.response)
                        logger.exception("Exception: %s", exp)
                        self.backend_connected = False
                        return False
            logger.info('%d hosts saved in retention', len(data_to_save['hosts']))
            self.statsmgr.counter('retention-save.hosts', len(data_to_save['hosts']))
            logger.info('%d services saved in retention', len(data_to_save['services']))
            self.statsmgr.counter('retention-save.services', len(data_to_save['services']))
            self.statsmgr.timer('retention-save.time', time.time() - start_time)

            now = time.time()
            logger.info("Retention saved in %s seconds", (now - start_time))
        except BackendException:
            self.backend_connected = False
            self.backend_errors_count += 1
            logger.warning("Alignak backend connection fails. Check and fix your configuration")
            return False

        return True
