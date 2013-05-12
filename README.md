redis-log-import
================

Use Redis to store and easily sort log files from multiple web servers

# Description
Say that you have a website living at "foo.com" with different portions of its URL namespace are owned by varying business units and divisions. For example:


* foo.com/hr
* foo.com/finance
* foo.com/marcomm


In spite of URLs being the human-based way to partition the URL namespace, say you have an internal content publishing system that associates a particular URL, top-level or otherwise, with a numerical identifier. So, even though "foo.com/hr" and "foo.com/hr/jobs" might seem to imply a parent-child relationship, they could be two different items within the internal content publishing system; for sake of argument we could call these "collections" within the content publishing system.

Owners of any collection want to have raw web server log data. They don't want to leak their data to an external analytics provider and they don't want the hassle of trying to deploy JavaScript tags onto what could be voluminous amounts of web content. They want access to this log data via the web, so a CGI script presenting them with log data, after they authenticate via an SSO solution is on the cards

The web server logs append a collection's numerical identifier to the end of log lines that are associated  
with requests for content from the collections portion of the URL namespace:

    99.32.443.66 - [06/May/2013:09:54:52 -0400] "GET /index.php HTTP/1.1" 200 (etc) <numerical ID>

Figuring out what log lines are attached to a collection is simple enough by grepping for the numerical identifier through the access log. It becomes challenging if the web presence is served by multiple machines. It is easy to wait until day's end, when traffic is not "live", grep each individual web server's access logs, combine log lines of interest, sort by timestamp and present them. We can do this *while* the data is being collected.

# Data Collection Questions

We could "tail" access logs on a system, filtering out for the numerical ID for a collection:

    /usr/bin/tail -f access_log |egrep " [[:digit:]]+$"

We follow the log as lines are added to it, searching for one or more digits at tail end.

Great, but how do we aggregate this data? We *should* have a data collection server to orchestrate pulling this information together. If the networks are trusted between the data collection server and the web servers, "netcat" might be an option. On the data collection server *web-data.foo.com* :

    nc -l 1234 > collection_log_lines.txt

While on each individual web server, we do the following:

    /usr/bin/tail -f access_log |egrep " [[:digit:]]+$" | nc web-data.foo.com 1234

So, on *web-data.foo.com*, we listen on port 1234 for input, while each web server takes the output from tail, filters for lines of interest, then connects it to the listening "nc" process to send the data to *web-data-foo.com*.There are some issues with this approach. 

First, it may be possible that "nc" could silently drop information in transit. Also, the simultaneous "tail" on multiple machines is not guaranteed to populate the "collection_log_lines.txt" file on the data collection server in an order corresponding to when a request actually occurred. If there is some latency differences between individual web servers and the data collection server, that could affect the appearance of log entries in the "collection_log_lines.txt" file.

Post-processing of the output file would be needed to adjust for the occurrence of mis-ordered log lines, but doing that makes the solution less "real-time." A long-running SSH tunnel or even stunnel may ensure reliable delivery, but there is still a problem of sorting out of sequence log lines.

# Building a Solution
I poked a stick at this thing called Redis and discovered that it does something called "sorted sets" (*ZSET*s). In these data structures, each element has a value and a score. While the values must be unique the scores can repeat. In my mind, the value would be the full content of an entire log line and the score would be something to assist in sorting. Notably, converting the timestamp of a log line to epoch time format fits nicely. We can ignore *when* we get log data for a collection, and use the timestamp information in log line to generate a score, using the score to sort amongst *all* loglines from *all* web servers we have.

# Obtaining and Storing Log Data

We construct *ZSET*s for each collection as so:

    logs:collid:<numerical id>

As input arrives, use the numerical identifier to ZADD log lines to the corresponding key name. If the *ZSET* does not exist, the operation will create it.

If we configure SSH keys or some other method to SSH easily to webservers, we can remotely execute the "tail" command, and pipe the output into a script to do the import of data into Redis. Use of the *myThread.py* (stashed in one of my other repos) means this can be fired off on all systems of interest at the same time.

    ssh <host> "tail -f /path/to/access_log| egrep -e ' [[:digit:]]+$' | ./process_log_input.py

View process_log_input.py for details.

So, we now have a number of *ZSET*S pegged to individual collection numerical ids. To view log entries for a collection with numerical ID of, "1824" for example, within the redis-cli:

    ZRANGE   logs:collid:1824 0 -1

You specify the keyname, the index of the "start" element (0) and the "end" element. "-1" indicates the last element.

Within Python with the redis module ipmorted, to get a list of the log lines, sorted by score:

    for log_line in conn.zrange('logs:collid:' + collid , 0, -1):
        print log_line

View retrieve_log_entries.py here.

We also created a *HASH* called "known:", with the keys within it named as so:

    hits:<collid>

Within the redis-cli, let's see how many hits we had for the collection with numerical ID of "1824":

    redis 127.0.0.1:6379> HGET known: hits:1824
    "15"

We are now able to get a gauge on what collections are being heavily trafficked, as well as being able to pluck hits for a particular collection, and get all the log lines associated with it across all web servers. For end-users, we could easily present the log data they needed with some simple CGI scripting and plugging into whatever authentication scheme we have in place to ensure that only users authorized to procure web log data for a particular collection are permitted to do so. For ourselves, we can get a grasp on what is being looked at, almost as it happens, without having to do Kung-Fu on the live web logs by hand. Neat!

We have a *ZSET* for each collection, named for a collection's numerical ID. We have a *HASH* of "known" collections, the keys including the collection's numerical ID and the value being the number of times assets were requested from the collection. 

    known:
        hits:<numerical ID>
        ...
    logs:collid:<numerical ID>
        <log entry>
        <log entry>
        ...


What else can we do?

* Given that we have IP addresses, we could do something interesting if we figured out what cities the visitors were originating from. 

I have begun looking into "grok" possibilities, but realize I *already* have code that can look up cities based on IP address from my interaction with "Redis in Action" book. 

View ip-to-city-and-country-lookup.py here.

    find_city_by_ip(conn, '99.32.443.66')
        returns-->[u'Houston', u'TX', u'US']

We use lookup_log_entry_location.py to process the log entries. This script uses the "known:" *HASH*, so we consult that first to figure out what numerical ids we have:

    coll_hits_dict = conn.hgetall('known:')

The keys contained in "coll_hits_dict" will be of the form:

    hits:<numerical ID>

We use "split" on ":" to grab the numerical ID, figure out what *ZSET*S are available, then iterate over log lines in the individual *ZSET*S, extracting the IP address from each log line. After the IP address is extracted, we can then use our stolen GeoLiteCity code to lookup location information based on IP address and then create new keys. 

We will use *ZSET*s again to represent how often a country-city-state combination appears in a particular collection. *HASH* could be used as well, but I (and maybe we) are only interested in the locations with largest amount of requests. 

We confirm what happens in Redis:

    redis 127.0.0.1:6379> zrevrange   location:collid:762 0 4 withscores
     1) "US--"
     2) "114"
     3) "US-VA-Ashburn"
     4) "27"
     5) "US-PA-Philadelphia"
     6) "28"
    ...

(On a side note, there may be only enough IP information to know that the end-user lives originates from the US, while the state and city are empty).

While we are at it, we could collect info about how many requests, in total, are from any individual country. We store these in keys named: 

    requests:country:<country name>
        
and increment them after we do the location lookup. With an extra line of code, we also increment a counter tying a collection to a country:

    requests:country:<country name>:<numerical id>

We can then do simple math to compute how much traffic from a particular country hit a particular collection. Neat.

Within the redis-cli:

    redis 127.0.0.1:6379> keys requests:country:US:*
         1) "requests:country:US"
         2) "requests:country:US:84332"
         3) "requests:country:US:667883"
         4) "requests:country:US:12212"
         5) "requests:country:US:7879"
         6) "requests:country:US:3242"


In combination with some data visualization tools, we could likely construct some rudimentary info dashboards from just this small amount of data. I have heard of a "maptail" utility which will neatly provide a realtime map view of GeoIP data. 

Since we have this info stashed in Redis, we should be able to easily "replay" the log data, pipe this into maptail, and get some really interesting visualizations of where requests originate from. Since we have the epoch time along with the log entry, we may be able to emit Redis-stored log data, over a truncated time period (minutes/seconds), to maptail. For example, if we want to display log data over a five minute period, a request that occurred at noontime would logically appear at 2:30 of the 5:00 period.

# Issues
* Memory is not finite, and limitations should be set on Redis server so you don't fill memory up. There should be some cron jobs that wipe out keys, resets counters, after they have outlived their usefulness. Presumably, removal of keys at midnight may align with the restart of a new web server log and availability of archived data from file, so no need to keep this in-memory, since the data we are interested in is now non-volatile. 
* As far as I know, *ZSET*s are not compressed, so as much disk the log entries would eat on disk, there would be an equivalent amount of data sitting in RAM. I have seen/heard that use of *HASH*s can be extremely efficient in memory usage, though I am not sure if those structures align with the need for baked-in sorting we are taking advantage of. 
* The SSH command and regex used to grab log lines of interest could be clumsy if more elaborate criteria to select log lines. The "grok" program used for LogStash pops into my mind, but unsure if there is Python wrapper for this or not (not that I care about only using Python). A script to simply the work of connecting and filtering and feeding that data into the import script seems in the offing.
