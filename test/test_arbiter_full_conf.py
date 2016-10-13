#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import shlex
import subprocess
import json
import unittest2
from alignak_module_backend.arbiter.module import AlignakBackendArbiter
from alignak.objects.module import Module
from alignak.objects.realm import Realm
from alignak.objects.command import Command
from alignak.objects.timeperiod import Timeperiod
from alignak.objects.contact import Contact
from alignak.objects.contactgroup import Contactgroup
from alignak.objects.host import Host
from alignak.objects.hostgroup import Hostgroup
from alignak.objects.hostdependency import Hostdependency
from alignak.objects.service import Service
from alignak.objects.servicegroup import Servicegroup
from alignak.objects.servicedependency import Servicedependency
from alignak_backend_client.client import Backend


class TestArbiterLoadconf(unittest2.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        # Set test mode for alignak backend
        os.environ['TEST_ALIGNAK_BACKEND'] = '1'
        os.environ['ALIGNAK_BACKEND_MONGO_DBNAME'] = 'alignak-module-backend-test'

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

        print ("Feeding backend...")
        exit_code = subprocess.call(
            shlex.split('alignak-backend-import --delete cfg/default/_main.cfg')
        )
        assert exit_code == 0

        # Start broker module
        modconf = Module()
        modconf.module_alias = "alignakbackendarbit"
        modconf.username = "admin"
        modconf.password = "admin"
        modconf.api_url = 'http://127.0.0.1:5000'
        cls.arbmodule = AlignakBackendArbiter(modconf)
        cls.objects = cls.arbmodule.get_objects()

    @classmethod
    def tearDownClass(cls):
        """
        Kill uwsgi

        :return: None
        """
        subprocess.call(['uwsgi', '--stop', '/tmp/uwsgi.pid'])
        time.sleep(2)

    def test_commands(self):
        self.assertEqual(len(self.objects['commands']), 105)
        for comm in self.objects['commands']:
            for key, value in comm.iteritems():
                self.assertTrue(Command.properties[key])

    def test_hostescalations(self):
        self.assertEqual(len(self.objects['hostescalations']), 0)

    def test_contacts(self):
        self.assertEqual(len(self.objects['contacts']), 5)
        for cont in self.objects['contacts']:
            for key, value in cont.iteritems():
                # problem in alignak because not defined
                if key not in ['can_update_livestate'] and not key.startswith('_'):
                    self.assertTrue(Contact.properties[key])

    def test_timeperiods(self):
        self.assertEqual(len(self.objects['timeperiods']), 4)
        # for item in self.objects['timeperiods']:
        #     for key, value in item.iteritems():
        #         self.assertTrue(Timeperiod.properties[key])

    def test_serviceescalations(self):
        self.assertEqual(len(self.objects['serviceescalations']), 0)

    def test_hostgroups(self):
        self.assertEqual(len(self.objects['hostgroups']), 9)
        for hostgrp in self.objects['hostgroups']:
            for key, value in hostgrp.iteritems():
                # problem in alignak because not defined
                if key not in ['hostgroup_members']:
                    self.assertTrue(Hostgroup.properties[key])

    def test_contactgroups(self):
        self.assertEqual(len(self.objects['contactgroups']), 3)
        for contact in self.objects['contactgroups']:
            for key, value in contact.iteritems():
                # problem in alignak because not defined
                if key not in ['contactgroup_members', 'notes']:
                    self.assertTrue(Contactgroup.properties[key])

    def test_hosts(self):
        self.assertEqual(len(self.objects['hosts']), 13)
        for host in self.objects['hosts']:
            print("Got host: %s" % host)
            for key, value in host.iteritems():
                if not key.startswith('ls_') and not key.startswith('_'):
                    self.assertTrue(Host.properties[key])

    def test_realms(self):
        self.assertEqual(len(self.objects['realms']), 5)
        for realm in self.objects['realms']:
            print("Got realm: %s" % realm)
            for key, value in realm.iteritems():
                self.assertTrue(Realm.properties[key])

    def test_services(self):
        self.assertEqual(len(self.objects['services']), 94)
        for serv in self.objects['services']:
            print("Got service: %s" % serv)
            for key, value in serv.iteritems():
                if not key.startswith('ls_') and not key.startswith('_'):
                    self.assertTrue(Service.properties[key])

    def test_servicegroups(self):
        self.assertEqual(len(self.objects['servicegroups']), 6)
        for grp in self.objects['servicegroups']:
            for key, value in grp.iteritems():
                # problem in alignak because not defined
                if key not in ['servicegroup_members']:
                    self.assertTrue(Servicegroup.properties[key])

    def test_hostdependencies(self):
        self.assertEqual(len(self.objects['hostdependencies']), 3)
        for grp in self.objects['hostdependencies']:
            for key, value in grp.iteritems():
                # Do not exist in Alignak, but do not disturb...
                if key not in ['notes', 'alias']:
                    self.assertTrue(Hostdependency.properties[key])

    def test_servicedependencies(self):
        self.assertEqual(len(self.objects['servicedependencies']), 1)
        for grp in self.objects['servicedependencies']:
            for key, value in grp.iteritems():
                # Do not exist in Alignak, but do not disturb...
                if key not in ['notes', 'alias']:
                    self.assertTrue(Servicedependency.properties[key])
