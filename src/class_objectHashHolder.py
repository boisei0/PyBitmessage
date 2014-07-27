# coding=utf-8
# objectHashHolder is a timer-driven thread. One objectHashHolder thread is used
# by each sendDataThread. The sendDataThread uses it whenever it needs to
# advertise an object to peers in an inv message, or advertise a peer to other
# peers in an addr message. Instead of sending them out immediately, it must
# wait a random number of seconds for each connection so that different peers
# get different objects at different times. Thus an attacker who is
# connecting to many network nodes who receives a message first from Alice
# cannot be sure if Alice is the node who originated the message.

import random
import time
import threading


class ObjectHashHolder(threading.Thread):
    def __init__(self, send_data_thread_mailbox):
        threading.Thread.__init__(self)
        self.shutdown = False
        self.send_data_thread_mailbox = send_data_thread_mailbox  # This queue is used to submit data back to our associated sendDataThread.
        self.collection_of_hash_lists = {}
        self.collection_of_peer_lists = {}
        for i in range(10):
            self.collection_of_hash_lists[i] = []
            self.collection_of_peer_lists[i] = []

    def run(self):
        iterator = 0
        while not self.shutdown:
            if len(self.collection_of_hash_lists[iterator]) > 0:
                self.send_data_thread_mailbox.put((0, 'sendinv', self.collection_of_hash_lists[iterator]))
                self.collection_of_hash_lists[iterator] = []
            if len(self.collection_of_peer_lists[iterator]) > 0:
                self.send_data_thread_mailbox.put((0, 'sendaddr', self.collection_of_peer_lists[iterator]))
                self.collection_of_peer_lists[iterator] = []
            iterator += 1
            iterator %= 10
            time.sleep(1)

    def hold_hash(self, hash):
        self.collection_of_hash_lists[random.randrange(0, 10)].append(hash)

    def hold_peer(self, peerDetails):
        self.collection_of_peer_lists[random.randrange(0, 10)].append(peerDetails)

    def close(self):
        self.shutdown = True