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

import os
import shlex
import time
import subprocess
import json
import unittest2
from alignak_module_backend.broker.module import AlignakBackendBroker
from alignak.objects.module import Module
from alignak.acknowledge import Acknowledge
from alignak.downtime import Downtime
from alignak_backend_client.client import Backend

from calendar import timegm
from datetime import datetime, timedelta


class TestBrokerAckDowntime(unittest2.TestCase):

    @classmethod
    def setUpClass(cls):
        # Set test mode for alignak backend
        os.environ['TEST_ALIGNAK_BACKEND'] = '1'
        os.environ['ALIGNAK_BACKEND_MONGO_DBNAME'] = 'alignak-module-backend-test'

        # Delete used mongo DBs
        print ("Deleting Alignak backend DB...")
        exit_code = subprocess.call(
            shlex.split(
                'mongo %s --eval "db.dropDatabase()"' % os.environ[
                    'ALIGNAK_BACKEND_MONGO_DBNAME'])
        )
        assert exit_code == 0

        cls.p = subprocess.Popen(['uwsgi', '--plugin', 'python', '-w', 'alignakbackend:app',
                                  '--socket', '0.0.0.0:5000',
                                  '--protocol=http', '--enable-threads', '--pidfile',
                                  '/tmp/uwsgi.pid'])
        time.sleep(3)

        cls.backend = Backend('http://127.0.0.1:5000')
        cls.backend.login("admin", "admin", "force")
        realms = cls.backend.get_all('realm')
        for cont in realms['_items']:
            cls.realm_all = cont['_id']

        # add commands
        data = json.loads(open('cfg/command_ping.json').read())
        data['_realm'] = cls.realm_all
        data_cmd_ping = cls.backend.post("command", data)
        data = json.loads(open('cfg/command_http.json').read())
        data['_realm'] = cls.realm_all
        data_cmd_http = cls.backend.post("command", data)
        # add host
        data = json.loads(open('cfg/host_srv001.json').read())
        data['check_command'] = data_cmd_ping['_id']
        del data['realm']
        data['_realm'] = cls.realm_all
        cls.data_host = cls.backend.post("host", data)
        # add 2 services
        data = json.loads(open('cfg/service_srv001_ping.json').read())
        data['host'] = cls.data_host['_id']
        data['check_command'] = data_cmd_ping['_id']
        data['_realm'] = cls.realm_all
        cls.data_srv_ping = cls.backend.post("service", data)

        data = json.loads(open('cfg/service_srv001_http.json').read())
        data['host'] = cls.data_host['_id']
        data['check_command'] = data_cmd_http['_id']
        data['_realm'] = cls.realm_all
        cls.data_srv_http = cls.backend.post("service", data)

        users = cls.backend.get_all('user')
        cls.user_id = users['_items'][0]['_id']

        # Start broker module
        modconf = Module()
        modconf.module_alias = "backend_broker"
        modconf.username = "admin"
        modconf.password = "admin"
        modconf.api_url = 'http://127.0.0.1:5000'
        cls.brokmodule = AlignakBackendBroker(modconf)

    @classmethod
    def tearDownClass(cls):
        cls.p.kill()

    @classmethod
    def tearDown(cls):
        """
        Delete resources in backend

        :return: None
        """
        for resource in ['actionacknowledge', 'actiondowntime']:
            cls.backend.delete(resource, {})

    def test_brok_acknowledge_raise_backend(self):
        """Test with a brok acknowledge_raise come from backend

        :return: None
        """
        data_ack = {
            'action': 'add',
            'host': self.data_host['_id'],
            'service': None,
            'user': self.user_id,
            'comment': 'Ack from the backend',
            'processed': True
        }
        self.backend.post("actionacknowledge", data_ack)

        actionack = self.backend.get_all('actionacknowledge')
        self.assertEqual(len(actionack['_items']), 1)
        self.assertEqual(actionack['_items'][0]['notified'], False)

        # send acknowledge_raise brok to our broker module
        data = {'ref': '90843789574897', 'sticky': actionack['_items'][0]['sticky'],
                'persistent': actionack['_items'][0]['persistent'], 'author': 'admin',
                'comment': actionack['_items'][0]['comment'], 'end_time': 0,
                'notify': actionack['_items'][0]['notify']}
        ack = Acknowledge(data)
        b = ack.get_raise_brok('srv001')
        b.prepare()
        self.brokmodule.get_refs()
        self.brokmodule.manage_brok(b)

        actionack = self.backend.get_all('actionacknowledge')
        self.assertEqual(len(actionack['_items']), 1)
        self.assertEqual(actionack['_items'][0]['notified'], True)

        hosts = self.backend.get_all('host')
        self.assertEqual(len(hosts['_items']), 2)
        self.assertEqual(hosts['_items'][1]['name'], 'srv001')
        self.assertEqual(hosts['_items'][1]['ls_acknowledged'], True)

    def test_brok_acknowledge_raise_extcommand_hknown(self):
        """Test with a brok acknowledge_raise come from external command (so not from backend).
        The host name is known in the backend

        :return: None
        """
        actionack = self.backend.get_all('actionacknowledge')
        self.assertEqual(len(actionack['_items']), 0)

        # send acknowledge_raise brok to our broker module
        data = {'ref': '90843789574897', 'sticky': 2,
                'persistent': 1, 'author': 'admin',
                'comment': 'blablabla1', 'end_time': 0,
                'notify': 1}
        ack = Acknowledge(data)
        b = ack.get_raise_brok('srv001')
        b.prepare()
        self.brokmodule.get_refs()
        self.brokmodule.manage_brok(b)

        actionack = self.backend.get_all('actionacknowledge')
        self.assertEqual(len(actionack['_items']), 1)
        self.assertEqual(actionack['_items'][0]['comment'], 'blablabla1')
        self.assertEqual(actionack['_items'][0]['notified'], True)
        self.assertEqual(actionack['_items'][0]['sticky'], False)

        hosts = self.backend.get_all('host')
        self.assertEqual(len(hosts['_items']), 2)
        self.assertEqual(hosts['_items'][1]['name'], 'srv001')
        self.assertEqual(hosts['_items'][1]['ls_acknowledged'], True)

    def test_brok_acknowledge_raise_extcommand_hunknown(self):
        """Test with a brok acknowledge_raise come from external command (so not from backend).
        The host name is unknown (not exist) in the backend

        :return: None
        """
        actionack = self.backend.get_all('actionacknowledge')
        self.assertEqual(len(actionack['_items']), 0)

        # send acknowledge_raise brok to our broker module
        data = {'ref': '90843789574897', 'sticky': 1,
                'persistent': 1, 'author': 'admin',
                'comment': 'blablabla1', 'end_time': 0,
                'notify': 1}
        ack = Acknowledge(data)
        b = ack.get_raise_brok('srv050')
        b.prepare()
        self.brokmodule.get_refs()
        self.brokmodule.manage_brok(b)

        actionack = self.backend.get_all('actionacknowledge')
        self.assertEqual(len(actionack['_items']), 0)

##########
    def test_brok_acknowledge_expire_backend(self):
        """Test with a brok acknowledge_expire come from backend

        :return: None
        """
        # update the host with ls_acknowledged = True
        headers = {
            'Content-Type': 'application/json',
            'If-Match': self.data_host['_etag']
        }
        self.backend.patch('host/%s' % self.data_host['_id'], {"ls_acknowledged": True}, headers,
                           True)
        hosts = self.backend.get_all('host')
        self.assertEqual(len(hosts['_items']), 2)
        self.assertEqual(hosts['_items'][1]['name'], 'srv001')
        self.assertEqual(hosts['_items'][1]['ls_acknowledged'], True)

        data_ack = {
            'action': 'delete',
            'host': self.data_host['_id'],
            'service': None,
            'user': self.user_id,
            'comment': 'Ack from the backend',
            'processed': True
        }
        self.backend.post("actionacknowledge", data_ack)

        actionack = self.backend.get_all('actionacknowledge')
        self.assertEqual(len(actionack['_items']), 1)
        self.assertEqual(actionack['_items'][0]['notified'], False)

        # send acknowledge_raise brok to our broker module
        data = {'ref': '90843789574897', 'sticky': actionack['_items'][0]['sticky'],
                'persistent': actionack['_items'][0]['persistent'], 'author': 'admin',
                'comment': actionack['_items'][0]['comment'], 'end_time': 0,
                'notify': actionack['_items'][0]['notify']}
        ack = Acknowledge(data)
        b = ack.get_expire_brok('srv001')
        b.prepare()
        self.brokmodule.get_refs()
        self.brokmodule.manage_brok(b)

        actionack = self.backend.get_all('actionacknowledge')
        self.assertEqual(len(actionack['_items']), 1)
        self.assertEqual(actionack['_items'][0]['notified'], True)

        hosts = self.backend.get_all('host')
        self.assertEqual(len(hosts['_items']), 2)
        self.assertEqual(hosts['_items'][1]['name'], 'srv001')
        self.assertEqual(hosts['_items'][1]['ls_acknowledged'], False)

    def test_brok_acknowledge_expire_extcommand_hknown(self):
        """Test with a brok acknowledge_expire come from external command or scheduler if service/
         host come up or acknowledge is expired (so not from backend). The host name is known in
         the backend

        :return: None
        """
        # update the host with ls_acknowledged = True
        headers = {
            'Content-Type': 'application/json',
            'If-Match': self.data_host['_etag']
        }
        self.backend.patch('host/%s' % self.data_host['_id'], {"ls_acknowledged": True}, headers,
                           True)
        hosts = self.backend.get_all('host')
        self.assertEqual(len(hosts['_items']), 2)
        self.assertEqual(hosts['_items'][1]['name'], 'srv001')
        self.assertEqual(hosts['_items'][1]['ls_acknowledged'], True)

        actionack = self.backend.get_all('actionacknowledge')
        self.assertEqual(len(actionack['_items']), 0)

        # send acknowledge_raise brok to our broker module
        data = {'ref': '90843789574897', 'sticky': 2,
                'persistent': 1, 'author': 'admin',
                'comment': 'blablabla1', 'end_time': 0,
                'notify': 1}
        ack = Acknowledge(data)
        b = ack.get_expire_brok('srv001')
        b.prepare()
        self.brokmodule.get_refs()
        self.brokmodule.manage_brok(b)

        actionack = self.backend.get_all('actionacknowledge')
        self.assertEqual(len(actionack['_items']), 1)
        self.assertEqual(actionack['_items'][0]['comment'], 'blablabla1')
        self.assertEqual(actionack['_items'][0]['notified'], True)
        self.assertEqual(actionack['_items'][0]['sticky'], False)
        self.assertEqual(actionack['_items'][0]['action'], 'delete')

        hosts = self.backend.get_all('host')
        self.assertEqual(len(hosts['_items']), 2)
        self.assertEqual(hosts['_items'][1]['name'], 'srv001')
        self.assertEqual(hosts['_items'][1]['ls_acknowledged'], False)

    def test_brok_acknowledge_expire_extcommand_hunknown(self):
        """Test with a brok acknowledge_expire come from external command or scheduler if service/
         host come up or acknowledge is expired (so not from backend). The host name is unknown
         (not exist) in the backend

        :return: None
        """
        actionack = self.backend.get_all('actionacknowledge')
        self.assertEqual(len(actionack['_items']), 0)

        # send acknowledge_raise brok to our broker module
        data = {'ref': '90843789574897', 'sticky': 1,
                'persistent': 1, 'author': 'admin',
                'comment': 'blablabla1', 'end_time': 0,
                'notify': 1}
        ack = Acknowledge(data)
        b = ack.get_expire_brok('srv050')
        b.prepare()
        self.brokmodule.get_refs()
        self.brokmodule.manage_brok(b)

        actionack = self.backend.get_all('actionacknowledge')
        self.assertEqual(len(actionack['_items']), 0)

    def test_brok_acknowledge_raise_backend_s(self):
        """Test with a brok acknowledge_raise come from backend (service)

        :return: None
        """
        data_ack = {
            'action': 'add',
            'host': self.data_host['_id'],
            'service': self.data_srv_http['_id'],
            'user': self.user_id,
            'comment': 'Ack from the backend',
            'processed': True
        }
        self.backend.post("actionacknowledge", data_ack)

        actionack = self.backend.get_all('actionacknowledge')
        self.assertEqual(len(actionack['_items']), 1)
        self.assertEqual(actionack['_items'][0]['notified'], False)

        # send acknowledge_raise brok to our broker module
        data = {'ref': '90843789574897', 'sticky': actionack['_items'][0]['sticky'],
                'persistent': actionack['_items'][0]['persistent'], 'author': 'admin',
                'comment': actionack['_items'][0]['comment'], 'end_time': 0,
                'notify': actionack['_items'][0]['notify']}
        ack = Acknowledge(data)
        b = ack.get_raise_brok('srv001', 'http toto.com')
        b.prepare()
        self.brokmodule.get_refs()
        self.brokmodule.manage_brok(b)

        actionack = self.backend.get_all('actionacknowledge')
        self.assertEqual(len(actionack['_items']), 1)
        self.assertEqual(actionack['_items'][0]['processed'], True)
        self.assertEqual(actionack['_items'][0]['notified'], True)

        services = self.backend.get_all('service')
        self.assertEqual(len(services['_items']), 2)
        self.assertEqual(services['_items'][1]['name'], 'http toto.com')
        self.assertEqual(services['_items'][1]['host'], self.data_host['_id'])
        self.assertEqual(services['_items'][1]['ls_acknowledged'], True)

    def test_brok_acknowledge_raise_extcommand_sknown(self):
        """Test with a brok acknowledge_raise come from external command (so not from backend).
        The host and service name are known in the backend

        :return: None
        """
        actionack = self.backend.get_all('actionacknowledge')
        self.assertEqual(len(actionack['_items']), 0)

        # send acknowledge_raise brok to our broker module
        data = {'ref': '90843789574897', 'sticky': 2,
                'persistent': 1, 'author': 'admin',
                'comment': 'blablabla1', 'end_time': 0,
                'notify': 1}
        ack = Acknowledge(data)
        b = ack.get_raise_brok('srv001', 'http toto.com')
        b.prepare()
        self.brokmodule.get_refs()
        self.brokmodule.manage_brok(b)

        actionack = self.backend.get_all('actionacknowledge')
        actionack = self.backend.get('actionacknowledge')
        print(("Acjs: %s" % actionack))
        self.assertEqual(len(actionack['_items']), 1)
        self.assertEqual(actionack['_items'][0]['host'], self.data_host['_id'])
        self.assertEqual(actionack['_items'][0]['service'], self.data_srv_http['_id'])
        self.assertEqual(actionack['_items'][0]['notified'], True)

        hosts = self.backend.get_all('service')
        self.assertEqual(len(hosts['_items']), 2)
        self.assertEqual(hosts['_items'][1]['name'], 'http toto.com')
        self.assertEqual(hosts['_items'][1]['host'], self.data_host['_id'])
        self.assertEqual(hosts['_items'][1]['ls_acknowledged'], True)

##########
    def test_brok_downtime(self):
        """Test with a brok downtime_raise come from backend

        :return: None
        """
        now = datetime.utcnow()
        later = now + timedelta(days=2, hours=4, minutes=3, seconds=12)
        now = timegm(now.timetuple())
        later = timegm(later.timetuple())

        # ---
        # Add downtimes into the backend
        # downtime a service
        data = {
            'action': 'add',
            'host': self.data_host['_id'],
            'service': self.data_srv_http['_id'],
            'user': self.user_id,
            "start_time": now,
            "end_time": later,
            "fixed": False,
            'duration': 86400,
            "comment": "User comment host",
            'processed': True
        }
        resp = self.backend.post("actiondowntime", data)

        actiondowntime = self.backend.get_all('actiondowntime')
        self.assertEqual(len(actiondowntime['_items']), 1)
        self.assertEqual(actiondowntime['_items'][0]['notified'], False)

        # send downtime_raise brok to our broker module
        data = {'ref': '0123456789', 'ref_type': 'host.my_type',
                'start_time': actiondowntime['_items'][0]['start_time'],
                'end_time': actiondowntime['_items'][0]['end_time'],
                'fixed': actiondowntime['_items'][0]['fixed'],
                'trigger_id': '',
                'duration': actiondowntime['_items'][0]['duration'],
                'author': 'me',
                'comment': actiondowntime['_items'][0]['comment']}
        downtime = Downtime(data)
        b = downtime.get_raise_brok('srv001', 'http toto.com')
        b.prepare()
        self.brokmodule.get_refs()
        self.brokmodule.manage_brok(b)

        actiondowntime = self.backend.get_all('actiondowntime')
        self.assertEqual(len(actiondowntime['_items']), 1)
        self.assertEqual(actiondowntime['_items'][0]['notified'], True)

        services = self.backend.get_all('service')
        self.assertEqual(len(services['_items']), 2)
        self.assertEqual(services['_items'][1]['name'], 'http toto.com')
        self.assertEqual(services['_items'][1]['host'], self.data_host['_id'])
        self.assertEqual(services['_items'][1]['ls_downtimed'], True)
