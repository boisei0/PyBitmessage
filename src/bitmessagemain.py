#!/usr/bin/env python2.7
# coding=utf-8
# Copyright (c) 2012 Jonathan Warren
# Copyright (c) 2012 The Bitmessage developers
# Distributed under the MIT/X11 software license. See the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

# Right now, PyBitmessage only support connecting to stream 1. It doesn't
# yet contain logic to expand into further streams.

# The software version variable is now held in shared.py

import signal  # Used to capture a Ctrl-C keypress so that Bitmessage can shutdown gracefully.
# The next 3 are used for the API
import singleton
import os
import socket
import ctypes
from struct import pack

from SimpleXMLRPCServer import SimpleXMLRPCServer
from api import MySimpleXMLRPCRequestHandler
from helper_startup import isOurOperatingSystemLimitedToHavingVeryFewHalfOpenConnections

import shared
from helper_sql import sqlQuery
import threading

# Classes
#from helper_sql import *
#from class_sqlThread import *
from class_sqlThread import sqlThread
from class_singleCleaner import singleCleaner
#from class_singleWorker import *
from class_objectProcessor import objectProcessor
from class_outgoingSynSender import outgoingSynSender
from class_singleListener import singleListener
from class_singleWorker import singleWorker
#from class_addressGenerator import *
from class_addressGenerator import addressGenerator
from debug import logger

# Helper Functions
import helper_bootstrap
import helper_generic

from subprocess import call
import time

# OSX python version check
import sys
if 'win' in sys.platform:
    if float("{1}.{2}".format(*sys.version_info)) < 7.5:
        msg = "You should use python 2.7.5 or greater. Your version: %s", "{0}.{1}.{2}".format(*sys.version_info)
        logger.critical(msg)
        print(msg)
        sys.exit(0)


def connect_to_stream(stream_number):
    shared.streamsInWhichIAmParticipating[stream_number] = 'no data'
    self_initiated_connections[stream_number] = {}
    shared.inventorySets[stream_number] = set()
    query_data = sqlQuery('''SELECT hash FROM inventory WHERE streamnumber=?''', stream_number)
    for row in query_data:
        shared.inventorySets[stream_number].add(row[0])

    if isOurOperatingSystemLimitedToHavingVeryFewHalfOpenConnections():
        # Some XP and Vista systems can only have 10 outgoing connections at a time.
        maximum_number_of_half_open_connections = 9
    else:
        maximum_number_of_half_open_connections = 64
    for i in range(maximum_number_of_half_open_connections):
        a = outgoingSynSender()
        a.setup(stream_number, self_initiated_connections)
        a.start()


def _fix_winsock():
    if not ('win32' in sys.platform) and not ('win64' in sys.platform):
        return

    # Python 2 on Windows doesn't define a wrapper for
    # socket.inet_ntop but we can make one ourselves using ctypes
    if not hasattr(socket, 'inet_ntop'):
        address_to_string = ctypes.windll.ws2_32.WSAAddressToStringA

        def inet_ntop(family, host):
            if family == socket.AF_INET:
                if len(host) != 4:
                    raise ValueError("invalid IPv4 host")
                host = pack("hH4s8s", socket.AF_INET, 0, host, "\0" * 8)
            elif family == socket.AF_INET6:
                if len(host) != 16:
                    raise ValueError("invalid IPv6 host")
                host = pack("hHL16sL", socket.AF_INET6, 0, 0, host, 0)
            else:
                raise ValueError("invalid address family")
            buf = "\0" * 64
            length_buf = pack("I", len(buf))
            address_to_string(host, len(host), None, buf, length_buf)
            return buf[0:buf.index("\0")]

        socket.inet_ntop = inet_ntop

    # Same for inet_pton
    if not hasattr(socket, 'inet_pton'):
        string_to_address = ctypes.windll.ws2_32.WSAStringToAddressA

        def inet_pton(family, host):
            buf = "\0" * 28
            length_buf = pack("I", len(buf))
            if string_to_address(str(host), int(family), None, buf, length_buf) != 0:
                raise socket.error("illegal IP address passed to inet_pton")
            if family == socket.AF_INET:
                return buf[4:8]
            elif family == socket.AF_INET6:
                return buf[8:24]
            else:
                raise ValueError("invalid address family")

        socket.inet_pton = inet_pton

    # These sockopts are needed on for IPv6 support
    if not hasattr(socket, 'IPPROTO_IPV6'):
        socket.IPPROTO_IPV6 = 41
    if not hasattr(socket, 'IPV6_V6ONLY'):
        socket.IPV6_V6ONLY = 27


# This thread, of which there is only one, runs the API.
class SingleAPI(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        se = SimpleXMLRPCServer((shared.config.get('bitmessagesettings', 'apiinterface'),
                                 shared.config.getint('bitmessagesettings', 'apiport')),
                                MySimpleXMLRPCRequestHandler, True, True)
        se.register_introspection_functions()
        se.serve_forever()

# This is a list of current connections (the thread pointers at least)
self_initiated_connections = {}

if shared.useVeryEasyProofOfWorkForTesting:
    shared.networkDefaultProofOfWorkNonceTrialsPerByte = int(
        shared.networkDefaultProofOfWorkNonceTrialsPerByte / 16)
    shared.networkDefaultPayloadLengthExtraBytes = int(
        shared.networkDefaultPayloadLengthExtraBytes / 7000)


class Main:
    def __init__(self):
        pass

    @staticmethod
    def start(daemon=False):
        _fix_winsock()

        shared.daemon = daemon
        # is the application already running?  If yes then exit.
        this_app = singleton.singleinstance()

        # get curses flag
        curses = False
        if '-c' in sys.argv:
            curses = True

        signal.signal(signal.SIGINT, helper_generic.signal_handler)
        # signal.signal(signal.SIGINT, signal.SIG_DFL)

        helper_bootstrap.knownNodes()
        # Start the address generation thread
        address_generator_thread = addressGenerator()
        address_generator_thread.daemon = True  # close the main program even if there are threads left
        address_generator_thread.start()

        # Start the thread that calculates POWs
        single_worker_thread = singleWorker()
        single_worker_thread.daemon = True  # close the main program even if there are threads left
        single_worker_thread.start()

        # Start the SQL thread
        sql_lookup = sqlThread()
        sql_lookup.daemon = False  # DON'T close the main program even if there are threads left. The closeEvent should command this thread to exit gracefully.
        sql_lookup.start()

        # Start the thread that calculates POWs
        object_processor_thread = objectProcessor()
        object_processor_thread.daemon = False  # DON'T close the main program even the thread remains. This thread checks the shutdown variable after processing each object.
        object_processor_thread.start()

        # Start the cleanerThread
        single_cleaner_thread = singleCleaner()
        single_cleaner_thread.daemon = True  # close the main program even if there are threads left
        single_cleaner_thread.start()

        shared.reloadMyAddressHashes()
        shared.reloadBroadcastSendersForWhichImWatching()

        if shared.safeConfigGetBoolean('bitmessagesettings', 'apienabled'):
            try:
                api_notify_path = shared.config.get('bitmessagesettings', 'apinotifypath')
            except:
                api_notify_path = ''
            if api_notify_path != '':
                with shared.printLock:
                    print('Trying to call', api_notify_path)

                call([api_notify_path, "startingUp"])
            single_api_thread = SingleAPI()
            single_api_thread.daemon = True  # close the main program even if there are threads left
            single_api_thread.start()

        connect_to_stream(1)

        single_listener_thread = singleListener()
        single_listener_thread.setup(self_initiated_connections)
        single_listener_thread.daemon = True  # close the main program even if there are threads left
        single_listener_thread.start()

        if not daemon and not shared.safeConfigGetBoolean('bitmessagesettings', 'daemon'):
            if not curses:
                try:
                    from PyQt4 import QtCore, QtGui
                except Exception as err:
                    print('PyBitmessage requires PyQt unless you want to run it as a daemon and interact with it using the API. You can download PyQt from http://www.riverbankcomputing.com/software/pyqt/download   or by searching Google for \'PyQt Download\'. If you want to run in daemon mode, see https://bitmessage.org/wiki/Daemon')
                    print('Error message:', err)
                    print('You can also run PyBitmessage with the new curses interface by providing \'-c\' as a commandline argument.')
                    os._exit(0)  # Boisei0: Why not sys.exit() ?

                import bitmessageqt
                bitmessageqt.run()
            else:
                print('Running with curses')
                import bitmessagecurses
                bitmessagecurses.runwrapper()
        else:
            shared.config.remove_option('bitmessagesettings', 'dontconnect')

            if daemon:
                with shared.printLock:
                    print('Running as a daemon. The main program should exit this thread.')
            else:
                with shared.printLock:
                    print('Running as a daemon. You can use Ctrl+C to exit.')
                while True:
                    time.sleep(20)

    @staticmethod
    def stop():
        with shared.printLock:
            print('Stopping Bitmessage Deamon.')
        shared.doCleanShutdown()

    #TODO: nice function but no one is using this
    @staticmethod
    def get_api_address():
        if not shared.safeConfigGetBoolean('bitmessagesettings', 'apienabled'):
            return None
        address = shared.config.get('bitmessagesettings', 'apiinterface')
        port = shared.config.getint('bitmessagesettings', 'apiport')
        return {
            'address': address,
            'port': port
        }

if __name__ == "__main__":
    main_program = Main()
    main_program.start()


# So far, the creation of and management of the Bitmessage protocol and this
# client is a one-man operation. Bitcoin tips are quite appreciated.
# 1H5XaDA6fYENLbknwZyjiYXYPQaFjjLX2u
