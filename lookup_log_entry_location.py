#!/usr/bin/env python

import redis
import json
import ip_to_city_and_country_lookup

conn = redis.Redis(host='localhost', port=6379, db=0)

# Get a dictionary of seen collections and hit counts
coll_hits_dict = conn.hgetall('known:')

# We then loop through each 'logs:collid:<collid>' ZSET we find.
for hits_keyname in coll_hits_dict.keys():
    # We start out with 'hits:<collection_id>'
    collection_id = hits_keyname.split(':')[1]
    zset_name = 'logs:collid:' + collection_id
    print "zset_name", zset_name
    for log_line in conn.zrange(zset_name, 0, -1):
        # Normally IP adress *should* be the first field, but we adjust for local
        # LogFormat mods done to add info for a load balancer.
        try:
            #ip_addr = log_line.split()[0]
            ip_addr = log_line.split()[1].strip()
            print "IP address", ip_addr
        except:
            continue

        # Now that we have an IP address we do a lookup that returns a list.
        # city, state, country
        location_list = ip_to_city_and_country_lookup.find_city_by_ip(conn, ip_addr)

        # Reverse the list, since we want to see things go from broad to specific.
        location_list.reverse()

        # We can now create data structures tying a collection to location
        # or aspects of the location we are interested in.

        # Craft a location string 'country-state-city' via join
        location_string = '-'.join(location_list)
        #print "country-city-state", location_string
            
        # Craft a hash, using location tuple as a key, increment the value.
        # So hashname 'location:collid:<collection id>'. The value the location
        # tuple, which will be (city, state, country), and value incremented.
        location_keyname = 'location:collid:' + collection_id
        #print "We are incrementing ", location_keyname
        conn.zincrby(location_keyname, location_string, 1)
        #print

        # Since we have the city, state, and country, we can craft more
        # counters via similar convention. Ex: "state:collid:<collection_id>"

        # Increment counters for entire countries, regardless of collection.
        # Country is the first item in the location_list. We create simple counter
        # Ex: requests:country:Singapore
        country_string = location_list[0]
        request_country_string = 'requests:country:' + country_string
        #print "Incrementing ", request_country_string
        conn.incr(request_country_string, 1)
        
        # While we are here, we also create counters based on the country and 
        # the collection ID. 
        conn.incr(request_country_string + ':' + collection_id, 1)

