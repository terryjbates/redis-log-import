#!/usr/bin/env python
#
# process_log_input.py
#
'''
We wish to process Apache web server log data containing a numerical identifier used to ID specific web "collections." 
Ex:
cat access_log| egrep -e ' [[:digit:]]+$' | ./process_tail_input.py
'''

import sys
import datetime
import redis
import time
import random

# We keep track of the collection IDS we have observed already.
known_collids = 'known:'

def process_log_line(pipe, line, epoch_time):
    # Use a callback function to take connection, logline,
    # and epoch time
    #print "\nincoming line is %s\n" % (line)

    # Grab the collid value at end. This should be filtered from the 'tail' command
    collid = line.split()[-1].strip()

    # Push the log entry onto a sorted set, named for the collid
    #collid_key_name = 'logs:collid:' + collid + ":" + str(random.random())
    collid_key_name = 'logs:collid:' + collid

    # Execute command to add log line to correct zset
    pipe.zadd(collid_key_name, epoch_time, line)

    # Execute command to add a 'seen' zset to a counter
    pipe.hincrby(known_collids,'hits:' + collid, 1)

def process_tail_input(conn, process_log_line):

    pipe = conn.pipeline()
    #pipe.zadd('logs:collid:486', 1367132605.0, 'this is a dummy log line with pipe object in process_tail_input '+ str(random.random()))
    
    def update_progress():
        print "executing pipe.execute"
        pipe.execute()                                      
    
    for lno, line in enumerate(sys.stdin):
        # Strip off whitespae
        line = line.strip()
        
        # Use this line in production, due to VIP and X-Forwarded-For
        line_list = line.split()
        
        #for index,line_entry in enumerate(line_list):
            #print "%s %s" % (index, line_entry)
        try:
            log_entry_date = line.split(" ")[4]    
            #date_string = line.split(" ")[4]

            # Convert log entry date to a time structure
            log_entry_time_struct = time.strptime(log_entry_date, "[%d/%b/%Y:%H:%M:%S")

            # Convert time structure to an epoch time
            log_entry_epoch = time.mktime(log_entry_time_struct)

            # Print the line with appended epoch time
            #print line + " " + str(log_entry_epoch)
            process_log_line(pipe, line, log_entry_epoch)

            # Every 100 lines we execute pipeline (though we can adjust to be larger for efficiency)
            if not (lno + 1) % 100:
                print "updating progress"
                update_progress()
        except:
            pass

    # execute pipeline if we are done processing sys.stdin
    print "Updating process after leaving for...stdin"
    update_progress()                                   

            


def main():
    # Connect to redis server as "conn"
    conn = redis.Redis(host='localhost', port=6379, db=0)

    # Call process_logs function
    process_tail_input(conn, process_log_line)

    # Print out the known counters
    try:
        seen_collids = conn.hgetall(known_collids)
        for seen_collid in seen_collids:
            print "seen collid: %s" % (seen_collid)
    except:
        "Problem with seeing seen_collids"
if __name__=='__main__':
    main()

