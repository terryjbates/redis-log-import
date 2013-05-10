#!/usr/bin/env python
#
# retrieve_log_entries.py
#


import sys
import datetime
import redis
import time
import random
import argparse


def get_collid_logs(conn, collid):
    # The log entries are stored in ZSETs. We want to get the log entries
    # scored in ascending order.
    collid_key_name = 'logs:collid:' + collid
    print "collid", collid
    print "our Key name is ", collid_key_name
    print "Connection type", type(conn)
    try:
        # We print out the log lines for the specified collid.
        # Since each line was scored according to its own date/time info
        # the entries will be sorted, no matter the server of origin.
        for log_line in conn.zrange('logs:collid:' + collid, 0, -1):
            print log_line
    except:
        print "We take issue with your request."


def main():
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('collid', help="Name of the collid log entries are wanted for.")
    args = parser.parse_args()

    # Once we have the collid
    if args.collid:
        conn = redis.Redis(host='localhost', port=6379, db=0)
        get_collid_logs(conn, args.collid)

if __name__ == '__main__':
    main()
