#!/usr/bin/env python
# -*- coding: utf-8 -*-

import unittest2
from alignak_module_backend.arbiter.module import AlignakBackendArbiter
from alignak_module_backend.broker.module import AlignakBackendBroker
from alignak_module_backend.scheduler.module import AlignakBackendScheduler

from alignak.objects.module import Module

# # Set the backend client library log to ERROR level
# import logging
# logging.getLogger("alignak_backend_client.client").setLevel(logging.ERROR)

from alignak.brok import Brok

class Arbiter():
    """Fake Arbiter class, only for tests..."""
    def __init__(self, verify_only=False, arbiter_name=None):
        self.verify_only = verify_only
        self.arbiter_name = arbiter_name


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

        assert self.brokmodule.backendConnection() is False
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
