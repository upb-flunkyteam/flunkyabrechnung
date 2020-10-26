===========================
Flunkyball Bookkeeping tool
===========================

|docker-build| |docker-size|

.. |docker-build| image:: https://img.shields.io/docker/cloud/build/upbflunkyteamdev/flunkabrechnung
   :target: https://hub.docker.com/repository/docker/upbflunkyteamdev/flunkabrechnung/builds

.. |docker-size| image:: https://img.shields.io/docker/cloud/build/upbflunkyteamdev/flunkabrechnung/latest
   :target: https://hub.docker.com/repository/docker/upbflunkyteamdev/flunkabrechnung/

Usage
-----

Docker
''''''
The tool is currently in a transition to a Flask website.
This will be achieved via docker

Console
'''''''
- Copy content of :code:`run` to root folder
- Execute::

    pip install -r requirements.txt
    python main.py --help
