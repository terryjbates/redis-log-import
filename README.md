redis-log-import
================

Use Redis to store and easily sort log files from multiple web servers

# Description
Say that you have a website living at "foo.com" with different portions of its URL namespace are owned by varying business units and divisions. For example:


* foo.com/hr
* foo.com/finance
* foo.com/marcomm


Imagine there is an internal content publishing system that associates portions of the URL namespace with a numerical identifier; this idenitifier is present within the web server's access log, stashed at the tail end of a log file entry.

Owners of any collection want to have raw web server log data. They may not want to leak their data to an external analytics provider and hope to avoid the hassle of deploying JavaScript tags onto what could be voluminous amounts of web content. A solution for providing the most recently updated log files for colection can be implemented. 

A sample request:

    99.32.443.66 - [06/May/2013:09:54:52 -0400] "GET /index.php HTTP/1.1" 200 (etc) <numerical ID>

Log lines for a specific collection can be identified by using a utility like `grep`. It becomes challenging if the web presence is served by multiple machines. Simply executing `grep` on multiple systems still means that processing must be done to collate and sort log data. Waiting till day's end, when traffic is not "live" is easiest, but we can do this *while* the data is being collected.

# Data Collection Questions

Executing `tail` on web server access logs on a  particular system:

    /usr/bin/tail -f access_log |egrep " [[:digit:]]+$"

...means we follow the log as lines are added filtering for numerical ID numbers.

Great, but how do we aggregate this data? We *should* have a data collection server to orchestrate pulling this information together. If the networks are trusted between the data collection server and the web servers, `nc` (netcat) might be an option. On the data collection server *web-data.foo.com* :

    nc -l 1234 >> collection_log_lines.txt

This command will append input to the specified output file. While on each individual web server, we do the following:

    /usr/bin/tail -f access_log |egrep " [[:digit:]]+$" | nc web-data.foo.com 1234

On *web-data.foo.com*, we listen on port 1234 for input, while each web server takes the output from tail, filters for lines of interest, then sends its output to the STDIN of `nc` process, which sends data to *web-data-foo.com*. There are some issues with this approach. 

It may be possible that `nc` could silently drop information in transit. Also, a simultaneous `tail` command executed on multiple machines is not guarantee that `collection_log_lines.txt` will be populated in a fashion mirroring the time sequence a request actually occurred. Latency differences between individual web servers and the data collection server, will affect the ordering of log entries in the `collection_log_lines.txt`.

Post-processing of the output file would be needed to adjust for the occurrence of mis-ordered log lines, but doing that makes the solution less "real-time." A long-running SSH tunnel or even stunnel may ensure reliable delivery, but there is still a problem of sorting out of sequence log lines.

# Building a Solution
I poked a stick at this thing called Redis and discovered that it does something called "sorted sets" *ZSETS*. In *ZSETS*, each element has a value and a score. While the values must be unique the scores can repeat. The value, in this case, would be the full content of an entire log line and the score would be a numerical timestamp. Epoch time format fits nicely. We ignore where and when we receive the data and use the score a the criteria for ordering log line output, across *all* the web servers in play.

# Obtaining and Storing Log Data

We construct *ZSETS* for each collection as so:

    logs:collid:<numerical id>

As input arrives, use the numerical identifier to *ZADD* log lines to the corresponding key name. If the *ZSET* does not exist, the *ZADD* operation impicitly create it.

Aftering configuring a convenient SSH method, we remotely execute the "tail" command, piping the output into a script to do the import of data into Redis. Use of the *myThread.py* (stashed in one of my other repos) means this can be fired off on all systems of interest at the same time.

    ssh <host> "tail -f /path/to/access_log| egrep -e ' [[:digit:]]+$' | ./process_log_input.py

View [process_log_input.py]( https://github.com/terryjbates/redis-log-import/blob/master/process_log_input.py "Title") for details.

We now have a number of *ZSET*S pegged to individual collection numerical ids. To view log entries for a collection with numerical ID of, "1824" for example, we execute the following command in `redis-cli`:

    ZRANGE   logs:collid:1824 0 -1

Specify the keyname, the index of the "start" element (0), and the "end" element (-1).

Using the Python redis cllient, to get a list of the log lines, sorted by score:

    for log_line in conn.zrange('logs:collid:' + collid , 0, -1):
        print log_line

View [retrieve_log_entries.py]( https://github.com/terryjbates/redis-log-import/blob/master/retrieve_log_entries.py "Title") here for a script to present all log entries when a numerical ID is specified on command line.

We also created a *HASH* called "known:", with the keys within it named as so:

    hits:<collid>

Within `redis-cli`, let's see how many hits we had for the collection with numerical ID of "1824":

    redis 127.0.0.1:6379> HGET known: hits:1824
    "15"

We now can gauge on what collections are heavily trafficked, as well pluck out hits for a particular collection, and view all log lines assocaited with a collection, across all web servers. For end-users, we could easily present the log data with CGI scripting, plugging into whatever authentication scheme needed. For ourselves (as sysadmins), we can get a grasp on what is being looked at, as requests hit the web servers, without having to do Kung-Fu on the live web logs by hand. Neat!

We have a *ZSET* for each collection, named for a collection's numerical ID. We have a *HASH* of "known" collections, the keys including the collection's numerical ID and the value being the number of times assets were requested from the collection. 

    known:
        hits:<numerical ID>
        ...
    logs:collid:<numerical ID>
        <log entry>
        <log entry>
        ...


What else can we do?

Given IP address information in a log entry, it would be interesting to see where end-users were browsing from. 

View [ip-to-city-and-country-lookup.py]( https://github.com/terryjbates/redis-log-import/blob/master/ip-to-city-and-country-lookup.py "Title") here.

View  here.

    find_city_by_ip(conn, '99.32.443.66')
        returns-->[u'Houston', u'TX', u'US']

We use lookup_log_entry_location.py to process the log entries. This script uses the "known:" *HASH*, so we consult that first to figure out what numerical ids we have:

    coll_hits_dict = conn.hgetall('known:')

The keys contained in `coll_hits_dict` will be of the form:

    hits:<numerical ID>

"Split" on ":" to grab the numerical ID, figure out what *ZSETS* are available, iterate over log lines in the individual *ZSETS*, extracting the IP address from each log line. After the IP address is extracted, we can then use our stolen GeoLiteCity code to lookup location information based on IP address and then create new keys. 

We use *ZSET* again to represent how often a country-city-state combination appears in a particular collection. *HASH* could be used as well, but I (and maybe we) are only interested in the locations with largest amount of requests for time being; the ordering of *HASH* is arbitrary. 

Within the `redis-cli`:

    redis 127.0.0.1:6379> zrevrange location:collid:762 0 4 withscores
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


In combination with some data visualization tools, we could construct rudimentary info dashboards from just this small amount of data. I have heard of a "maptail" utility which will neatly provide a realtime map view of GeoIP data. 

With ready access to log data in Redis, we could easily "replay" the log data, pipe this into maptail, and get some really interesting visualizations of where requests originate from. We can emit Redis-stored log data, over a truncated time period (minutes/seconds), to maptail, in a controlled fashion. For example, if we want to display log data over a five minute period, a request that occurred at noontime would logically appear at 2:30 of the 5:00 period.

# Issues

* Memory is not finite, and limitations should be set on Redis server so you don't fill memory up. There should be some cron jobs that wipe out keys, resets counters, after they have outlived their usefulness. Presumably, removal of keys at midnight may align with the restart of a new web server log and availability of archived data from file, so no need to keep this in-memory, since the data we are interested in is now non-volatile. 

* *ZSETS* are not compressed, so as much disk the log entries would eat on disk, there would be an equivalent amount of data sitting in RAM. I have seen/heard that use of *HASH*s can be extremely efficient in memory usage, though I am not sure if those structures align with the need for baked-in sorting we are taking advantage of. 

* The SSH command and regex used to grab log lines of interest could be clumsy if more elaborate criteria 
to select log lines. The "grok" program used for LogStash pops into my mind, but unsure if there is Python wrapper for this or not (not that I care about only using Python). A script to simply the work of connecting and filtering and feeding that data into the import script seems in the offing.
