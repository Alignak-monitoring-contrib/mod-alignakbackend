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
This file tests the backend login
"""

import os
import time
import shlex
import subprocess
import unittest2
from alignak_module_backend.arbiter.module import AlignakBackendArbiter
from alignak_module_backend.broker.module import AlignakBackendBroker
from alignak_module_backend.scheduler.module import AlignakBackendScheduler

from alignak.objects.module import Module
from alignak_backend_client.client import Backend

# # Set the backend client library log to ERROR level
# import logging
# logging.getLogger("alignak_backend_client.client").setLevel(logging.ERROR)

from alignak.brok import Brok

class Arbiter():
    """Fake Arbiter class, only for tests..."""
    def __init__(self, verify_only=False, arbiter_name=None):
        self.verify_only = verify_only
        self.arbiter_name = arbiter_name

class SchedulerOk():
    """Fake scheduler class used to load retention"""

    def restore_retention_data(self, data):
        assert True

class SchedulerKo():
    """Fake scheduler class used to load retention"""

    def restore_retention_data(self, data):
        assert True


class TestBackendNotAvailableLoginFails(unittest2.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        # Set test mode for alignak backend
        os.environ['TEST_ALIGNAK_BACKEND'] = '1'
        os.environ['ALIGNAK_BACKEND_MONGO_DBNAME'] = 'alignak-module-backend-arbiter-test'

        # Delete used mongo DBs
        print ("Deleting Alignak backend DB...")
        exit_code = subprocess.call(
            shlex.split(
                'mongo %s --eval "db.dropDatabase()"' % os.environ['ALIGNAK_BACKEND_MONGO_DBNAME'])
        )
        assert exit_code == 0

        cls.p = subprocess.Popen(['uwsgi', '--plugin', 'python', '-w', 'alignakbackend:app',
                                  '--socket', '0.0.0.0:5000',
                                  '--protocol=http', '--enable-threads', '--pidfile',
                                  '/tmp/uwsgi.pid'])
        time.sleep(3)
        cls.backend = Backend('http://127.0.0.1:5000')
        cls.backend.login("admin", "admin", "force")
        users = cls.backend.get_all('user')
        for user in users['_items']:
            cls.user_admin = user

    @classmethod
    def tearDownClass(cls):
        """
        Kill uwsgi

        :return: None
        """
        subprocess.call(['uwsgi', '--stop', '/tmp/uwsgi.pid'])
        time.sleep(2)

    def test_arbiter_login_ok(self):
        """Test arbiter module when backend login succeeds

        :return:
        """
        # Start arbiter module
        modconf = Module()
        modconf.module_alias = "backend_arbiter"
        modconf.username = "admin"
        modconf.password = "admin"
        modconf.api_url = 'http://127.0.0.1:5000'
        arbiter_module = AlignakBackendArbiter(modconf)
        assert arbiter_module.backend_connected is True

        # Got objects from the backend ...
        assert arbiter_module.get_objects() != {}
        assert arbiter_module.get_objects() != {
            'commands': [],
            'contactgroups': [],
            'contacts': [],
            'hostdependencies': [],
            'hostescalations': [],
            'hostgroups': [],
            'hosts': [],
            'realms': [],
            'servicedependencies': [],
            'serviceescalations': [],
            'servicegroups': [],
            'services': [],
            'timeperiods': [],
            'triggers': []
        }

    def test_arbiter_login_ko(self):
        """Test arbiter module when backend login fails

        :return:
        """
        # Start arbiter module
        modconf = Module()
        modconf.module_alias = "backend_arbiter"
        modconf.username = "admin"
        modconf.password = "fake_password"
        modconf.api_url = 'http://127.0.0.1:5000'
        arbiter_module = AlignakBackendArbiter(modconf)
        assert arbiter_module.backend_connected is False

        # Got empty objects lists from the backend ...
        assert arbiter_module.get_objects() == {
            'commands': [],
            'contactgroups': [],
            'contacts': [],
            'hostdependencies': [],
            'hostescalations': [],
            'hostgroups': [],
            'hosts': [],
            'realms': [],
            'servicedependencies': [],
            'serviceescalations': [],
            'servicegroups': [],
            'services': [],
            'timeperiods': [],
            'triggers': []
        }

    def test_arbiter_token_ok(self):
        """Test arbiter module when backend login succeeds with a user token

        :return:
        """
        # Start arbiter module
        modconf = Module()
        modconf.module_alias = "backend_arbiter"
        # modconf.username = "admin"
        # modconf.password = "admin"
        modconf.token = self.user_admin["token"]
        modconf.api_url = 'http://127.0.0.1:5000'
        arbiter_module = AlignakBackendArbiter(modconf)
        assert arbiter_module.backend_connected is True

        # Got objects from the backend ...
        assert arbiter_module.get_objects() != {}
        assert arbiter_module.get_objects() != {
            'commands': [],
            'contactgroups': [],
            'contacts': [],
            'hostdependencies': [],
            'hostescalations': [],
            'hostgroups': [],
            'hosts': [],
            'realms': [],
            'servicedependencies': [],
            'serviceescalations': [],
            'servicegroups': [],
            'services': [],
            'timeperiods': [],
            'triggers': []
        }

    def test_arbiter_token_ko(self):
        """Test arbiter module when backend login fails with a user token

        :return:
        """
        # Start arbiter module
        modconf = Module()
        modconf.module_alias = "backend_arbiter"
        # modconf.username = "admin"
        # modconf.password = "admin"
        modconf.token = "fake"
        modconf.api_url = 'http://127.0.0.1:5000'
        arbiter_module = AlignakBackendArbiter(modconf)
        # Module assumes a connection because a token is provided
        assert arbiter_module.backend_connected is True

        # Got empty objects lists from the backend ...
        assert arbiter_module.get_objects() == {
            'commands': [],
            'contactgroups': [],
            'contacts': [],
            'hostdependencies': [],
            'hostescalations': [],
            'hostgroups': [],
            'hosts': [],
            'realms': [],
            'servicedependencies': [],
            'serviceescalations': [],
            'servicegroups': [],
            'services': [],
            'timeperiods': [],
            'triggers': []
        }

    def test_broker_login_ok(self):
        """Test broker module when backend login succeeds

        :return:
        """
        # Start broker module
        modconf = Module()
        modconf.module_alias = "backend_broker"
        modconf.username = "admin"
        modconf.password = "admin"
        modconf.api_url = 'http://127.0.0.1:5000'
        broker_module = AlignakBackendBroker(modconf)
        assert broker_module.backend_connected is True

        # New configuration brok to reload host/services from the backend
        broker_module.loaded_hosts = False
        broker_module.loaded_services = False
        broker_module.loaded_users = False
        b = Brok({'data': {}, 'type': 'new_conf'}, False)
        b.prepare()
        assert broker_module.manage_brok(b) is True
        assert broker_module.loaded_hosts is not 0
        assert broker_module.loaded_services is not 0
        assert broker_module.loaded_users is not 0

    def test_broker_login_ko(self):
        """Test broker module when backend login fails

        :return:
        """
        # Start broker module
        modconf = Module()
        modconf.module_alias = "backend_broker"
        modconf.username = "admin"
        modconf.password = "fake_password"
        modconf.api_url = 'http://127.0.0.1:5000'
        broker_module = AlignakBackendBroker(modconf)
        assert broker_module.backend_connected is False

        # New configuration brok to reload host/services from the backend
        broker_module.loaded_hosts = False
        broker_module.loaded_services = False
        broker_module.loaded_users = False
        b = Brok({'data': {}, 'type': 'new_conf'}, False)
        b.prepare()
        assert broker_module.manage_brok(b) is False
        assert broker_module.loaded_hosts is False
        assert broker_module.loaded_services is False
        assert broker_module.loaded_users is False

    def test_broker_token_ok(self):
        """Test broker module when backend login succeeds with a user token

        :return:
        """
        # Start broker module
        modconf = Module()
        modconf.module_alias = "backend_broker"
        # modconf.username = "admin"
        # modconf.password = "admin"
        modconf.token = self.user_admin["token"]
        modconf.api_url = 'http://127.0.0.1:5000'
        broker_module = AlignakBackendBroker(modconf)
        assert broker_module.backend_connected is True

        # New configuration brok to reload host/services from the backend
        broker_module.loaded_hosts = False
        broker_module.loaded_services = False
        broker_module.loaded_users = False
        b = Brok({'data': {}, 'type': 'new_conf'}, False)
        b.prepare()
        assert broker_module.manage_brok(b) is True
        assert broker_module.loaded_hosts is not 0
        assert broker_module.loaded_services is not 0
        assert broker_module.loaded_users is not 0

    def test_broker_token_ko(self):
        """Test broker module when backend login fails with a user token

        :return:
        """
        # Start broker module
        modconf = Module()
        modconf.module_alias = "backend_broker"
        # modconf.username = "admin"
        # modconf.password = "admin"
        modconf.token = "fake"
        modconf.api_url = 'http://127.0.0.1:5000'
        broker_module = AlignakBackendBroker(modconf)
        assert broker_module.backend_connected is False

        # New configuration brok to reload host/services from the backend
        broker_module.loaded_hosts = False
        broker_module.loaded_services = False
        broker_module.loaded_users = False
        b = Brok({'data': {}, 'type': 'new_conf'}, False)
        b.prepare()
        assert broker_module.manage_brok(b) is False
        assert broker_module.loaded_hosts is False
        assert broker_module.loaded_services is False
        assert broker_module.loaded_users is False

    def test_scheduler_login_ok(self):
        """Test scheduler module when backend login succeeds

        :return:
        """
        # Start scheduler module
        modconf = Module()
        modconf.module_alias = "backend_scheduler"
        modconf.username = "admin"
        modconf.password = "admin"
        modconf.api_url = 'http://127.0.0.1:5000'
        scheduler_module = AlignakBackendScheduler(modconf)
        assert scheduler_module.backend_connected is True

        fake_scheduler = SchedulerOk()
        scheduler_module.hook_load_retention(fake_scheduler)

    def test_scheduler_login_ko(self):
        """Test scheduler module when backend login fails

        :return:
        """
        # Start scheduler module
        modconf = Module()
        modconf.module_alias = "backend_scheduler"
        modconf.username = "admin"
        modconf.password = "fake_password"
        modconf.api_url = 'http://127.0.0.1:5000'
        scheduler_module = AlignakBackendScheduler(modconf)
        assert scheduler_module.backend_connected is False

        fake_scheduler = SchedulerKo()
        scheduler_module.hook_load_retention(fake_scheduler)

    def test_scheduler_token_ok(self):
        """Test scheduler module when backend login succeeds with a user token

        :return:
        """
        # Start scheduler module
        modconf = Module()
        modconf.module_alias = "backend_scheduler"
        # modconf.username = "admin"
        # modconf.password = "admin"
        modconf.token = self.user_admin["token"]
        modconf.api_url = 'http://127.0.0.1:5000'
        scheduler_module = AlignakBackendScheduler(modconf)
        assert scheduler_module.backend_connected is True

        fake_scheduler = SchedulerOk()
        scheduler_module.hook_load_retention(fake_scheduler)

    def test_scheduler_token_ko(self):
        """Test scheduler module when backend login fails with a user token

        :return:
        """
        # Start scheduler module
        modconf = Module()
        modconf.module_alias = "backend_scheduler"
        # modconf.username = "admin"
        # modconf.password = "admin"
        modconf.token = "fake"
        modconf.api_url = 'http://127.0.0.1:5000'
        scheduler_module = AlignakBackendScheduler(modconf)
        assert scheduler_module.backend_connected is True

        fake_scheduler = SchedulerKo()
        scheduler_module.hook_load_retention(fake_scheduler)


class TestBackendNotAvailable(unittest2.TestCase):

    def test_arbiter_errors(self):
        """Test arbiter module when no backend is available

        :return:
        """
        # Start arbiter module
        modconf = Module()
        modconf.module_alias = "backend_arbiter"
        modconf.username = "admin"
        modconf.password = "admin"
        modconf.api_url = 'http://127.0.0.1:5000'
        self.arbmodule = AlignakBackendArbiter(modconf)

        # exception cases - no backend connection
        assert {} == self.arbmodule.get_alignak_configuration()

        # exception cases - arbiter in verify mode and bypass is set
        fake_arb = Arbiter(True)
        self.arbmodule.hook_read_configuration(fake_arb)
        self.arbmodule.backend_connected = True
        self.arbmodule.bypass_verify_mode = True
        assert {} == self.arbmodule.get_alignak_configuration()

        # exception cases - backend import is active
        fake_arb = Arbiter()
        self.arbmodule.hook_read_configuration(fake_arb)
        self.arbmodule.backend_import = True
        self.arbmodule.backend_connected = True
        assert {} == self.arbmodule.get_alignak_configuration()

    def test_broker_errors(self):
        """Test broker module when no backend is available

        :return:
        """
        # Start broker module
        modconf = Module()
        modconf.module_alias = "backend_broker"
        modconf.username = "admin"
        modconf.password = "admin"
        modconf.api_url = 'http://127.0.0.1:5000'
        self.brokmodule = AlignakBackendBroker(modconf)

        assert self.brokmodule.backend_connection() is False
        assert self.brokmodule.logged_in is False

        b = Brok({'data': {}, 'type': 'new_conf'}, False)
        b.prepare()
        assert self.brokmodule.manage_brok(b) is False

    def test_scheduler_errors(self):
        """Test scheduler module when no backend is available

        :return:
        """
        # Start scheduler module
        modconf = Module()
        modconf.module_alias = "backend_scheduler"
        modconf.username = "admin"
        modconf.password = "admin"
        modconf.api_url = 'http://127.0.0.1:5000'
        self.schedmodule = AlignakBackendScheduler(modconf)

        class scheduler(object):
            """Fake scheduler class used to save and load retention"""

            def __init__(self):
                self.data = None

            def get_retention_data(self):
                assert False, "Will never be called!"

            def restore_retention_data(self, data):
                assert False, "Will never be called!"

        self.fake_scheduler = scheduler()

        self.schedmodule.hook_load_retention(self.fake_scheduler)
        self.schedmodule.hook_save_retention(self.fake_scheduler)
