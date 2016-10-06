Alignak Backend Modules
=======================

*Alignak modules for the Alignak Backend*

Build status (stable release)
-----------------------------

.. image:: https://travis-ci.org/Alignak-monitoring-contrib/alignak-module-backend.svg?branch=master
    :target: https://travis-ci.org/Alignak-monitoring-contrib/alignak-module-backend


Build status (development release)
----------------------------------

.. image:: https://travis-ci.org/Alignak-monitoring-contrib/alignak-module-backend.svg?branch=develop
    :target: https://travis-ci.org/Alignak-monitoring-contrib/alignak-module-backend


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

Please report any issue using the project `GitHub repository: <https://github.com/Alignak-monitoring-contrib/alignak-module-backend/issues>`_.

License
-------

Alignak Backend Modules is available under the `GPL version 3 <http://opensource.org/licenses/GPL-3.0>`_.

