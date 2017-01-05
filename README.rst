Alignak Backend Modules
=======================

*Alignak modules for the Alignak Backend*

.. image:: https://travis-ci.org/Alignak-monitoring-contrib/alignak-module-backend.svg?branch=develop
    :target: https://travis-ci.org/Alignak-monitoring-contrib/alignak-module-backend
    :alt: Develop branch build status

.. image:: https://landscape.io/github/Alignak-monitoring-contrib/alignak-module-backend/develop/landscape.svg?style=flat
    :target: https://landscape.io/github/Alignak-monitoring-contrib/alignak-module-backend/develop
    :alt: Development code static analysis

.. image:: https://coveralls.io/repos/Alignak-monitoring-contrib/alignak-module-backend/badge.svg?branch=develop
    :target: https://coveralls.io/r/Alignak-monitoring-contrib/alignak-module-backend
    :alt: Development code tests coverage

.. image:: https://badge.fury.io/py/alignak_module_backend.svg
    :target: https://badge.fury.io/py/alignak-module-backend
    :alt: Most recent PyPi version

.. image:: https://img.shields.io/badge/IRC-%23alignak-1e72ff.svg?style=flat
    :target: http://webchat.freenode.net/?channels=%23alignak
    :alt: Join the chat #alignak on freenode.net

.. image:: https://img.shields.io/badge/License-AGPL%20v3-blue.svg
    :target: http://www.gnu.org/licenses/agpl-3.0
    :alt: License AGPL v3

Installation
------------

The installation of this module will copy some configuration files in the Alignak default configuration directory (eg. */usr/local/etc/alignak*). The copied files are located in the default sub-directory used for the modules (eg. *arbiter/modules*).

From PyPI
~~~~~~~~~
To install the module from PyPI:
::

   sudo pip install alignak-module-backend


From source files
~~~~~~~~~~~~~~~~~
To install the module from the source files (for developing purpose):
::

   git clone https://github.com/Alignak-monitoring-contrib/alignak-module-backend
   cd alignak-module-backend
   sudo pip install . -e

**Note:** *using `sudo python setup.py install` will not correctly manage the package configuration files! The recommended way is really to use `pip`;)*


Short description
-----------------

This meta-module for Alignak contains 3 modules:

* Arbiter module, which features are:

    * get configuration from Alignak backend
    * manages acknowledgements, downtimes schedule and re-checks

* Scheduler module, which features are:

    * manage retention (load and save)

* Broker module, which features are:

    * update live state of hosts and services in the Alignak backend
    * update log for hosts and services checks in the Alignak backend

Configuration
-------------

Each module has its own configuration file and its configuration parameters.
The configuration files are documented to help setting the right configuration.

* Arbiter module:

    * configure the Alignak backend connection (url and login)
    * configure periodical configuration modification check
    * configure periodical required actions (ack, downtime, ...)

* Scheduler module:

    * configure the Alignak backend connection (url and login)

* Broker module:

    * configure the Alignak backend connection (url and login)


Bugs, issues and contributing
-----------------------------

Contributions to this project are welcome and encouraged ... `issues in the project repository <https://github.com/alignak-monitoring-contrib/alignak-module-backend/issues>`_ are the common way to raise an information.
