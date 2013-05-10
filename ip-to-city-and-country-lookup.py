#!/usr/bin/env python
#
# ip-to-city-and-country-lookup.py
#

import redis
import json
import csv

# Code shamelessly copied from
# https://github.com/josiahcarlson/redis-in-action/blob/master/python/ch05_listing_source.py

# Connect to Redis
conn = redis.Redis(host='localhost', port=6379, db=0)


# <start id="_1314_14473_9188"/>
def ip_to_score(ip_address):
    score = 0
    for v in ip_address.split('.'):
        score = score * 256 + int(v, 10)
    return score
# <end id="_1314_14473_9188"/>
#END


# <start id="_1314_14473_9191"/>
def import_ips_to_redis(conn, filename):                #A
    csv_file = csv.reader(open(filename, 'rb'))
    for count, row in enumerate(csv_file):
        start_ip = row[0] if row else ''                #B
        if 'i' in start_ip.lower():
            continue
        if '.' in start_ip:                             #B
            start_ip = ip_to_score(start_ip)            #B
        elif start_ip.isdigit():                        #B
            start_ip = int(start_ip, 10)                #B
        else:
            continue                                    #C

        city_id = row[2] + '_' + str(count)             #D
        conn.zadd('ip2cityid:', city_id, start_ip)      #E
# <end id="_1314_14473_9191"/>
#A Should be run with the location of the GeoLiteCity-Blocks.csv file
#B Convert the IP address to a score as necessary
#C Header row or malformed entry
#D Construct the unique city id
#E Add the IP address score and City ID
#END


# <start id="_1314_14473_9194"/>
def import_cities_to_redis(conn, filename):         #A
    for row in csv.reader(open(filename, 'rb')):
        if len(row) < 4 or not row[0].isdigit():
            continue
        row = [i.decode('latin-1') for i in row]
        city_id = row[0]                            #B
        country = row[1]                            #B
        region = row[2]                             #B
        city = row[3]                               #B
        conn.hset('cityid2city:', city_id,          #C
            json.dumps([city, region, country]))    #C
# <end id="_1314_14473_9194"/>
#A Should be run with the location of the GeoLiteCity-Location.csv file
#B Prepare the information for adding to the hash
#C Actually add the city information to Redis
#END

# <start id="_1314_14473_9197"/>
def find_city_by_ip(conn, ip_address):
    if isinstance(ip_address, str):                        #A
        ip_address = ip_to_score(ip_address)               #A

    city_id = conn.zrevrangebyscore(                       #B
        'ip2cityid:', ip_address, 0, start=0, num=1)       #B

    if not city_id:
        return None

    city_id = city_id[0].partition('_')[0]                 #C
    return json.loads(conn.hget('cityid2city:', city_id))  #D
# <end id="_1314_14473_9197"/>
#A Convert the IP address to a score for zrevrangebyscore
#B Find the uique city ID
#C Convert the unique city ID to the common city ID
#D Fetch the city information from the hash
#END

def main():
    # The following commands presume you have unzipped the 'GeoLiteCity_20130402.zip' file
    # Import IP addresses to Redis. This will take a *LONG* time.
    import_ips_to_redis(conn, 'GeoLiteCity_20130402/GeoLiteCity-Blocks.csv')
    # Import City information to Redis
    import_cities_to_redis(conn, './GeoLiteCity_20130402/GeoLiteCity-Location.csv')


if __name__ == '__main__':
    main()
    
