#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from google.appengine.ext import db,search
from google.appengine.api import memcache
try:
    from google.appengine.api import taskqueue
except ImportError:
    from google.appengine.api.labs import taskqueue

import logging
import datetime

import dygutil
import dygmodel

logdebug = False

def allocate_keys(entity_kind, key_count=10):
    handmade_key = db.Key.from_path(entity_kind, 1)
    return list(db.allocate_ids(handmade_key, key_count))

def fetch_chat_messages(limit):
    cachedmessages = memcache.get("chatmessages")
    #newestsortindex = memcache.get("newestsortindex")
    #logging.info("fetch_chat_messages: memcache.get(\"newestsortindex\")=%s" % memcache.get("newestsortindex"))
    if cachedmessages:
        if logdebug: logging.debug("fetch_chat_messages 1: len(memcache.get(\"chatmessages\"))=" + str(len(cachedmessages)))
        #logging.info("cachedmessages[:5]=%s" % cachedmessages[:5])
    else:
        if logdebug: logging.debug("fetch_chat_messages 1: memcache.get(\"chatmessages\")=" + str(cachedmessages))
    if not cachedmessages:
        if logdebug: logging.debug("fetch_chat_messages: querying datastore without sortindex ")
        q = db.GqlQuery("SELECT * FROM ChatMessage " +
                    "ORDER BY sortindex DESC")
        chatmessages = q.fetch(limit)
        cachedmessages = [m.to_dict() for m in chatmessages]

        import time
        memcache_client = memcache.Client()

        for i in range(20):
            newestsortindex = memcache_client.gets("newestsortindex")
            if not newestsortindex:
                memcache.set("newestsortindex", newestsortindex)
                memcache.set("chatmessages",cachedmessages)
                break
            if cachedmessages[0]['sortindex'] <= newestsortindex:
                break
            newestsortindex = cachedmessages[0]['sortindex']
            if memcache_client.cas("newestsortindex", newestsortindex):
                memcache.set("chatmessages",cachedmessages)
                break
            time.sleep(0.1)

    # if not (cachedmessages and newestsortindex and newestsortindex <= cachedmessages[0]['sortindex']):
    #     if cachedmessages:
    #         if logdebug: logging.debug("fetch_chat_messages: querying datastore with sortindex " + cachedmessages[0].sortindex)
    #         q = db.GqlQuery("SELECT * FROM ChatMessage " +
    #                     "WHERE sortindex > :1 " +
    #                     "ORDER BY sortindex DESC",cachedmessages[0]['sortindex'])
    #         chatmessages = q.fetch(limit)
    #         if chatmessages:
    #             newcachedmessages = [m.to_dict() for m in chatmessages]
    #             logging.info("newcachedmessages=%s" % newcachedmessages)
    #             newcachedmessages.extend(cachedmessages)
    #             cachedmessages = newcachedmessages
    #         else:
    #             logging.info("no newcachedmessages")
    #     else:
    #         if logdebug: logging.debug("fetch_chat_messages: querying datastore without sortindex ")
    #         q = db.GqlQuery("SELECT * FROM ChatMessage " +
    #                     "ORDER BY sortindex DESC")
    #         chatmessages = q.fetch(limit)
    #         cachedmessages = [m.to_dict() for m in chatmessages]
    #
    #
    #     if cachedmessages and newestsortindex:
    #         # HRD delays can prevent latest message(s) from being returned by the query. Abort if necessary to prevent corrupting memcache.
    #         assert len([m for m in cachedmessages if m['sortindex'] == newestsortindex]) > 0
    #         assert cachedmessages[0]['sortindex'] >= newestsortindex
    #
    #     if len(cachedmessages) > limit: cachedmessages = cachedmessages[:limit]
    #     memcache.set("chatmessages",cachedmessages)
    #     if cachedmessages:
    #         memcache.set("newestsortindex", cachedmessages[0]['sortindex'])
    #         logging.info("fetch_chat_messages: Set newestsortindex to %s in memcache; memcache.get(\"newestsortindex\")=%s" % (cachedmessages[0]['sortindex'], memcache.get("newestsortindex")))

    if cachedmessages:
        if logdebug: logging.debug("fetch_chat_messages 2: len(memcache.get(\"chatmessages\"))=" + str(len(cachedmessages)))
    else:
        if logdebug: logging.debug("fetch_chat_messages 2: memcache.get(\"chatmessages\")=" + str(cachedmessages))
    return cachedmessages


def create_chat_message(team, local_id, text, ipaddress, is_retry, dt=None, mancow=False, chat_page_size=100, from_slack=False):
    msg = None
    if is_retry:
        msg = dygmodel.ChatMessage.all().filter("local_id = ", local_id).get()
        if not msg:
            # handle HRD latency, since we've queried on an indexed value and the index might just not be up to date.
            cachedmessages = memcache.get("chatmessages")
            if cachedmessages:
                filtered = [m for m in cachedmessages if m['local_id'] == local_id]
                if filtered:
                    cached_msg = filtered[0]
                    msg = dygmodel.ChatMessage.get_by_id(cached_msg['id'])
    if not msg:
        import time
        memcache_client = memcache.Client()
        msg = None

        chat_message_keys = []
        logging.info("1")
        for i in range(20):
            while True:
                cachedmessages = memcache_client.gets("chatmessages")
                if cachedmessages is not None:
                    break
                fetch_chat_messages(chat_page_size+1)
            _dt = datetime.datetime.now()
            if not chat_message_keys:
                chat_message_keys = allocate_keys("ChatMessage", 2)
            msg = dygmodel.ChatMessage(
                key=db.Key.from_path('ChatMessage', chat_message_keys.pop(0)),
                team=team,
                local_id=local_id,
                text=text,
                ipaddress=ipaddress,
                date=_dt,
                mancow=mancow,
                sortindex = str(dygutil.string_to_datetime(str(_dt))) + "|" + team.key().name() + "|" + str(get_team_post_index(team.key())),
                from_slack=from_slack,
            )
            newcachedmessages = [msg.to_dict()]
            newcachedmessages.extend(cachedmessages)
            newcachedmessages = sorted(newcachedmessages, key=lambda (m): m['sortindex'], reverse=True)
            if memcache_client.cas("chatmessages", newcachedmessages):
                for i in range(20):
                    newestsortindex = memcache_client.gets("newestsortindex")
                    if not newestsortindex:
                        memcache.set("newestsortindex", newestsortindex)
                        break
                    if newcachedmessages[0]['sortindex'] <= newestsortindex:
                        break
                    newestsortindex = newcachedmessages[0]['sortindex']
                    if memcache_client.cas("newestsortindex", newestsortindex):
                        break
                    time.sleep(0.1)
                break
            time.sleep(0.1)
        msg.put()

    t = taskqueue.Task(url='/tasks/slack_sync', params={'msg_key_id': msg.key().id()}, method='GET')
    t.add(queue_name = 'chat-stats')

    t = taskqueue.Task(url='/tasks/record_chatwords', params={'msg_key_id': msg.key().id()}, method='GET')
    t.add(queue_name = 'post-words')

    t = taskqueue.Task(url='/tasks/chatmessage_stats', params={'msg_key_id': msg.key().id()}, method='GET')
    t.add(queue_name = 'chat-stats')

    # delete these lines once we're caught up.
    #msg.statscomplete = True
    #msg.put()

    #memcache.set("newestsortindex", msg.sortindex)
    #logging.info("create_chat_message: Set newestsortindex to %s in memcache; memcache.get(\"newestsortindex\")=%s" % (msg.sortindex, memcache.get("newestsortindex")))
    return msg.to_dict()

def record_chat_words(key_id):
    logging.info("record_chat_words: enter")

    msg = dygmodel.ChatMessage.get_by_id(key_id)

    # Make sure there are no chatwords hanging around from a previously failed task.
    entitylist = dygmodel.ChatMessageChatWord.all().filter("chatmessage = ", msg).fetch(1000)
    db.delete(entitylist)

    # Now insert the chatwords.
    entitylist = []
    for word in dygutil.words_from_text(msg.text, minlength=3, stopwords=dygutil.fetch_stopwords(), unique=True):
        chatword = dygmodel.ChatWord.get_or_insert("cw_" + word, word=word, date=msg.date, hidden=False)
        msgchatword = dygmodel.ChatMessageChatWord(chatword=chatword,chatmessage=msg)
        msgchatword.set_calculated_fields()
        entitylist.append(msgchatword)
    db.put(entitylist)

def get_team_post_index(key_value):
    def get_index(key_value):
        t = dygmodel.Team.get(key_value)
        t.postindex += 1
        t.put()
        return t.postindex
    return db.run_in_transaction(get_index, key_value)

def run_slack_sync(key_id):
    from google.appengine.api import urlfetch
    import urllib
    msg = dygmodel.ChatMessage.get_by_id(key_id)
    if msg.from_slack:
        return
    token = ""
    channel = "general"
    text = msg.text.encode('utf-8')

    user_mapping = {
       "t_24":{
          "owner_name":"Shellers",
          "email":"williamschet67@yahoo.com"
       },
       "t_27":{
          "owner_name":"Mr. Kolbeck",
          "email":"kolbeck04@gmail.com"
       },
       "t_21":{
          "owner_name":"Joe Schmidt",
          "email":"joe.r.schmidt@gmail.com"
       },
       "t_20":{
          "owner_name":"Jim Ermitage",
          "email":None
       },
       "t_23":{
          "owner_name":"Cyrus Khazai",
          "email":"ckhazai@gmail.com"
       },
       "t_22":{
          "owner_name":"Cory Snyder",
          "email":"patmrclutchtabler@gmail.com"
       },
       "t_18":{
          "owner_name":"Definitely Dogger",
          "email":None
       },
       "t_19":{
          "owner_name":"The DICKtator",
          "email":None
       },
       "t_14":{
          "owner_name":"Noah",
          "email":"noahmontague@yahoo.com"
       },
       "t_15":{
          "owner_name":"matt schuster",
          "email":"mjschuster@fuse.net"
       },
       "t_16":{
          "owner_name":"Les E",
          "email":None
       },
       "t_17":{
          "owner_name":"Pat Pruneau",
          "email":None
       },
       "t_10":{
          "owner_name":"Nate Tormoehlen",
          "email":"joerote@hotmail.com"
       },
       "t_11":{
          "owner_name":"Bart Beatty",
          "email":"btbeatty@hotmail.com"
       },
       "t_12":{
          "owner_name":"Dogger",
          "email":"michael_judy513@hotmail.com"
       },
       "t_13":{
          "owner_name":"KEITH STRADLEY",
          "email":"kstrad@hotmail.com"
       },
       "t_8":{
          "owner_name":"Ben Houg",
          "email":"benhoug@gmail.com"
       },
       "t_9":{
          "owner_name":"Phil Sauer",
          "email":"phil.sauer@ey.com"
       },
       "t_2":{
          "owner_name":"Trent Tormoehlen",
          "email":"ttor68@yahoo.com"
       },
       "t_3":{
          "owner_name":"Erik Peterson",
          "email":"ep2kp2@msn.com"
       },
       "t_1":{
          "owner_name":"Dave Loomer",
          "email":"dloomer@gmail.com"
       },
       "t_6":{
          "owner_name":"Calvin P. Reese",
          "email":"ckhazai@gmail.com"
       },
       "t_7":{
          "owner_name":"Michael Ermitage",
          "email":"mermitage@hotmail.com"
       },
       "t_4":{
          "owner_name":"Andy Peterson",
          "email":"andypt7@gmail.com"
       },
       "t_5":{
          "owner_name":"Sean Disch",
          "email":"sean_disch@hotmail.com"
       },
       "t_28":{
          "owner_name":"Craig McMurtrey",
          "email":"craig@dyinggiraffe.com"
       },
       "t_29":{
          "owner_name":"Jason Ziegler",
          "email":"zieglerrj21@gmail.com"
       },
       "t_30":{
          "owner_name":"Gregdave Barringhausfill",
          "email":None
       },
       "t_31":{
          "owner_name":"DA CHI TOWN PLAYA",
          "email":None
       }
    }

    username = user_mapping[msg.team_key_name]['owner_name'].lower().replace(" ", "_")

    url = "https://slack.com/api/chat.postMessage" + \
        "?token=" + token + \
        "&channel=" + channel + \
        "&text=" + urllib.quote_plus(text) + \
        "&username=" + username + \
        "&unfurl_links=true" + \
        "&unfurl_media=true" + \
        "&as_user=false"
    logging.debug(url)
    response = urlfetch.fetch(url)
    logging.debug(response.content)


def run_chat_stats(key_id):
    msg = dygmodel.ChatMessage.get_by_id(key_id)

    dt_central = msg.date.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo())

    hour_central = dt_central.hour
    day_central = dt_central.day
    month_central = dt_central.month
    year_central = dt_central.year

    update_past_stats_timespan_durations(msg)

    if not dygmodel.StatsTimeSpan.all().get():
        initialize_stats_timespans(dt_central)

    tshour = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.HOUR_SPAN, year_central, month_central, day_central, hour_central)
    tsday = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.DAY_SPAN, year_central, month_central, day_central, 0)
    tsmonth = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.MONTH_SPAN, year_central, month_central, 1, 0)
    tsyear = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.YEAR_SPAN, year_central, 1, 1, 0)
    tsalltime = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.ALL_TIME_SPAN, 0, 0, 0, 0)

    '''
    def udpate_settings_element_stats_counts(key_val):
        ses = dygmodel.SettingsElementStats.get(key_val)
        ses.postcount = ses.timespan.postcount
        ses.uniqueteamspostingcount = ses.timespan.uniqueteamspostingcount
        ses.put()
    '''
    db.run_in_transaction(increment_stats_timespan, tshour.key(), dt_central)
    #for ses in tshour.settingselementstats_set:
    #    db.run_in_transaction(udpate_settings_element_stats_counts, ses.key())

    db.run_in_transaction(increment_stats_timespan, tsday.key(), dt_central)
    #for ses in tsday.settingselementstats_set:
    #    db.run_in_transaction(udpate_settings_element_stats_counts, ses.key())

    db.run_in_transaction(increment_stats_timespan, tsmonth.key(), dt_central)
    #for ses in tsmonth.settingselementstats_set:
    #    db.run_in_transaction(udpate_settings_element_stats_counts, ses.key())

    db.run_in_transaction(increment_stats_timespan, tsyear.key(), dt_central)
    #for ses in tsyear.settingselementstats_set:
    #    db.run_in_transaction(udpate_settings_element_stats_counts, ses.key())

    db.run_in_transaction(increment_stats_timespan, tsalltime.key(), dt_central)
    #for ses in tsalltime.settingselementstats_set:
    #    db.run_in_transaction(udpate_settings_element_stats_counts, ses.key())

    # unique team posting counts
    teamcount_increment = db.run_in_transaction(update_stats_teamcount, tshour.key(), msg.team.key().name(), 0)
    if teamcount_increment > 0: db.run_in_transaction(update_stats_teamcount, tsday.key(), msg.team.key().name(), teamcount_increment)
    if teamcount_increment > 0: db.run_in_transaction(update_stats_teamcount, tsmonth.key(), msg.team.key().name(), teamcount_increment)
    if teamcount_increment > 0: db.run_in_transaction(update_stats_teamcount, tsyear.key(), msg.team.key().name(), teamcount_increment)
    if teamcount_increment > 0: db.run_in_transaction(update_stats_teamcount, tsalltime.key(), msg.team.key().name(), teamcount_increment)

    #team stats
    tsteamhour = dygmodel.TeamChatMessageStats.get_or_insert_by_values(msg.team,tshour)
    tsteamday = dygmodel.TeamChatMessageStats.get_or_insert_by_values(msg.team,tsday)
    tsteammonth = dygmodel.TeamChatMessageStats.get_or_insert_by_values(msg.team,tsmonth)
    tsteamyear = dygmodel.TeamChatMessageStats.get_or_insert_by_values(msg.team,tsyear)
    tsteamalltime = dygmodel.TeamChatMessageStats.get_or_insert_by_values(msg.team,tsalltime)

    def increment_team_postcount(key_val):
        ts = dygmodel.TeamChatMessageStats.get(key_val)
        ts.postcount += 1
        ts.put()

    logging.debug("run_chat_stats: team=" + msg.team.key().name())
    logging.debug("run_chat_stats: year=" + str(year_central))
    logging.debug("run_chat_stats: month=" + str(month_central))
    logging.debug("run_chat_stats: day=" + str(day_central))
    logging.debug("run_chat_stats: hour=" + str(hour_central))

    logging.debug("run_chat_stats: increment_team_postcount for hour timespan")
    db.run_in_transaction(increment_team_postcount, tsteamhour.key())
    logging.debug("run_chat_stats: increment_team_postcount for day timespan")
    db.run_in_transaction(increment_team_postcount, tsteamday.key())
    logging.debug("run_chat_stats: increment_team_postcount for month timespan")
    db.run_in_transaction(increment_team_postcount, tsteammonth.key())
    logging.debug("run_chat_stats: increment_team_postcount for year timespan")
    db.run_in_transaction(increment_team_postcount, tsteamyear.key())
    logging.debug("run_chat_stats: increment_team_postcount for alltime timespan")
    db.run_in_transaction(increment_team_postcount, tsteamalltime.key())

def update_past_stats_timespan_durations(msg):
    dt_central = msg.date.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo())

    hour_central = dt_central.hour
    day_central = dt_central.day
    month_central = dt_central.month
    year_central = dt_central.year

    entitylist = []

    # hour timespan
    tslist = dygmodel.StatsTimeSpan.gql("WHERE timespanvalue=:1 ORDER BY date DESC", dygmodel.StatsTimeSpan.HOUR_SPAN).fetch(limit=2)
    for ts in tslist:
        if ts.year_central != year_central or ts.month_central != month_central or ts.day_central != day_central or ts.hour_central != hour_central:
            if ts.totalduration < 1:
                ts.totalduration = float(1)
                entitylist.append(ts)
            break

    # day timespan
    tslist = dygmodel.StatsTimeSpan.gql("WHERE timespanvalue=:1 ORDER BY date DESC", dygmodel.StatsTimeSpan.DAY_SPAN).fetch(limit=2)
    for ts in tslist:
        if ts.year_central != year_central or ts.month_central != month_central or ts.day_central != day_central or ts.hour_central != hour_central:
            this_datetime_central = datetime.datetime(ts.year_central,ts.month_central,ts.day_central,ts.hour_central)
            next_datetime_central = (this_datetime_central + datetime.timedelta(days=1)).replace(hour=0)
            td = next_datetime_central - this_datetime_central
            new_duration = float(td.days*24 + float(td.seconds)/3600)
            if ts.totalduration != new_duration:
                ts.totalduration = new_duration
                entitylist.append(ts)
            break

    # month timespan
    tslist = dygmodel.StatsTimeSpan.gql("WHERE timespanvalue=:1 ORDER BY date DESC", dygmodel.StatsTimeSpan.MONTH_SPAN).fetch(limit=2)
    for ts in tslist:
        if ts.year_central != year_central or ts.month_central != month_central or ts.day_central != day_central or ts.hour_central != hour_central:
            this_datetime_central = datetime.datetime(ts.year_central,ts.month_central,ts.day_central,ts.hour_central)
            next_datetime_central = dygutil.add_months_to_datetime(this_datetime_central)
            td = next_datetime_central - this_datetime_central
            new_duration = float(td.days*24 + float(td.seconds)/3600)
            if ts.totalduration != new_duration:
                ts.totalduration = new_duration
                entitylist.append(ts)
            break

    # year timespan
    tslist = dygmodel.StatsTimeSpan.gql("WHERE timespanvalue=:1 ORDER BY date DESC", dygmodel.StatsTimeSpan.YEAR_SPAN).fetch(limit=2)
    for ts in tslist:
        if ts.year_central != year_central or ts.month_central != month_central or ts.day_central != day_central or ts.hour_central != hour_central:
            this_datetime_central = datetime.datetime(ts.year_central,ts.month_central,ts.day_central,ts.hour_central)
            next_year_central = this_datetime_central.year + 1
            next_datetime_central = this_datetime_central.replace(year=next_year_central,month=1,day=1,hour=0)
            td = next_datetime_central - this_datetime_central
            new_duration = float(td.days*24 + float(td.seconds)/3600)
            if ts.totalduration != new_duration:
                ts.totalduration = new_duration
                entitylist.append(ts)
            break

    db.put(entitylist)

def increment_stats_timespan(key_val, new_datetime):
    ts = dygmodel.StatsTimeSpan.get(key_val)
    ts_start_datetime = datetime.datetime(ts.year_central,ts.month_central,ts.day_central,ts.hour_central,tzinfo=new_datetime.tzinfo)
    new_duration_delta = new_datetime - ts_start_datetime
    ts.postcount += 1
    ts.totalduration = float(new_duration_delta.days*24 + float(new_duration_delta.seconds)/3600)
    ts.put()

def initialize_stats_timespans(new_datetime_central):
    hour_central = new_datetime_central.hour
    day_central = new_datetime_central.day
    month_central = new_datetime_central.month
    year_central = new_datetime_central.year

    entitylist = []

    tshour = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.HOUR_SPAN, year_central, month_central, day_central, hour_central)

    tsday = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.DAY_SPAN, year_central, month_central, day_central, 0)
    tsday.hour_central = hour_central
    entitylist.append(tsday)

    tsmonth = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.MONTH_SPAN, year_central, month_central, 1, 0)
    tsmonth.day_central = day_central
    tsmonth.hour_central = hour_central
    entitylist.append(tsmonth)

    tsyear = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.YEAR_SPAN, year_central, 1, 1, 0)
    tsyear.month_central = month_central
    tsyear.day_central = day_central
    tsyear.hour_central = hour_central
    entitylist.append(tsyear)

    tsalltime = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.ALL_TIME_SPAN, 0, 0, 0, 0)
    tsalltime.year_central = year_central
    tsalltime.month_central = month_central
    tsalltime.day_central = day_central
    tsalltime.hour_central = hour_central
    entitylist.append(tsalltime)

    db.put(entitylist)

def update_stats_teamcount(key_val, team_key_name, inc_value):
    ts = dygmodel.StatsTimeSpan.get(key_val)
    if ts.timespanvalue == dygmodel.StatsTimeSpan.HOUR_SPAN:
        uniqueteamspostings = set(ts.uniqueteamspostings)
        if team_key_name not in uniqueteamspostings: ts.uniqueteamspostings.append(team_key_name)
        inc_value = len(ts.uniqueteamspostings) - ts.uniqueteamspostingcount

    if inc_value > 0:
        ts.uniqueteamspostingcount += inc_value
        ts.put()

    return inc_value

def fetch_team_ownername(key_name):
    team_ownernames = memcache.get("team_ownernames")
    if not team_ownernames: team_ownernames = {}
    if key_name not in team_ownernames:
        team_ownernames[key_name] = fetch_team(key_name).ownername
        memcache.set("team_ownernames",team_ownernames)
    return team_ownernames[key_name]

def fetch_team(key_name):
    teams = memcache.get("teams")
    if not teams: teams = {}
    if key_name not in teams:
        teams[key_name] = dygmodel.Team.get_by_key_name(key_name)
        memcache.set("teams",teams)
    return teams[key_name]

def run_chatword_stats(chatword,team,datetime,step=0):
    word = chatword.word
    if logdebug: logging.debug("enter run_chatword_stats; word=" + str(word) + ",step=" + str(step))
    dt_central = datetime.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo())

    hour_central = dt_central.hour
    day_central = dt_central.day
    month_central = dt_central.month
    year_central = dt_central.year

    if not dygmodel.StatsTimeSpan.all().get():
        initialize_stats_timespans(dt_central)

    if logdebug: logging.debug("run_chatword_stats (" + word + "): get_or_insert_by_values for tshour")
    tshour = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.HOUR_SPAN, year_central, month_central, day_central, hour_central)
    if logdebug: logging.debug("run_chatword_stats (" + word + "): get_or_insert_by_values for tsday")
    tsday = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.DAY_SPAN, year_central, month_central, day_central, 0)
    if logdebug: logging.debug("run_chatword_stats (" + word + "): get_or_insert_by_values for tsmonth")
    tsmonth = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.MONTH_SPAN, year_central, month_central, 1, 0)
    if logdebug: logging.debug("run_chatword_stats (" + word + "): get_or_insert_by_values for tsyear")
    tsyear = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.YEAR_SPAN, year_central, 1, 1, 0)
    if logdebug: logging.debug("run_chatword_stats (" + word + "): get_or_insert_by_values for tsalltime")
    tsalltime = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.ALL_TIME_SPAN, 0, 0, 0, 0)

    # hacks to get around GAE "ReferenceProperty failed to be resolved" bugs
    '''
    tshour.key()
    tsday.key()
    tsmonth.key()
    tsyear.key()
    tsalltime.key()
    '''

    if logdebug: logging.debug("run_chatword_stats (" + word + "): get_or_insert_by_values for cwshour")
    cwshour = dygmodel.ChatWordStats.get_or_insert_by_values(tshour, chatword)
    if logdebug: logging.debug("run_chatword_stats (" + word + "): get_or_insert_by_values for cwsday")
    cwsday = dygmodel.ChatWordStats.get_or_insert_by_values(tsday, chatword)
    if logdebug: logging.debug("run_chatword_stats (" + word + "): get_or_insert_by_values for cwsmonth")
    cwsmonth = dygmodel.ChatWordStats.get_or_insert_by_values(tsmonth, chatword)
    if logdebug: logging.debug("run_chatword_stats (" + word + "): get_or_insert_by_values for cwsyear")
    cwsyear = dygmodel.ChatWordStats.get_or_insert_by_values(tsyear, chatword)
    if logdebug: logging.debug("run_chatword_stats (" + word + "): get_or_insert_by_values for cwsalltime")
    cwsalltime = dygmodel.ChatWordStats.get_or_insert_by_values(tsalltime, chatword)

    # hacks to get around GAE "ReferenceProperty failed to be resolved" bugs
    '''
    cwshour.chatword.key()
    cwsday.chatword.key()
    cwsmonth.chatword.key()
    cwsyear.chatword.key()
    cwsalltime.chatword.key()
    logging.info("cwsalltime.key()=" + str(cwsalltime.key()))
    cwshour.timespan.key()
    cwsday.timespan.key()
    cwsmonth.timespan.key()
    cwsyear.timespan.key()
    cwsalltime.timespan.key()
    logging.info("cwsalltime.timespan.key()=" + str(cwsalltime.timespan.key()))
    '''

    if step in [0,1,3]:
        if logdebug: logging.debug("run_chatword_stats (" + word + "): increment_chatword_stats_timespan_transaction for cwshour")
        increment_chatword_stats_timespan_transaction(cwshour.key())
        if logdebug: logging.debug("run_chatword_stats (" + word + "): increment_chatword_stats_timespan_transaction for cwsday")
        increment_chatword_stats_timespan_transaction(cwsday.key())
        if logdebug: logging.debug("run_chatword_stats (" + word + "): increment_chatword_stats_timespan_transaction for cwsmonth")
        increment_chatword_stats_timespan_transaction(cwsmonth.key())
        if logdebug: logging.debug("run_chatword_stats (" + word + "): increment_chatword_stats_timespan_transaction for cwsyear")
        increment_chatword_stats_timespan_transaction(cwsyear.key())
        if logdebug: logging.debug("run_chatword_stats (" + word + "): increment_chatword_stats_timespan_transaction for cwsalltime")
        increment_chatword_stats_timespan_transaction(cwsalltime.key())

        # unique team posting counts
        if logdebug: logging.debug("run_chatword_stats (" + word + "): update_chatword_stats_teamcount_transaction for cwshour")
        teamcount_increment = update_chatword_stats_teamcount_transaction(cwshour.key(), team.key().name(), 0)
        if logdebug: logging.debug("run_chatword_stats (" + word + "): update_chatword_stats_teamcount_transaction for cwsday")
        if teamcount_increment > 0: update_chatword_stats_teamcount_transaction(cwsday.key(), team.key().name(), teamcount_increment)
        if logdebug: logging.debug("run_chatword_stats (" + word + "): update_chatword_stats_teamcount_transaction for cwsmonth")
        if teamcount_increment > 0: update_chatword_stats_teamcount_transaction(cwsmonth.key(), team.key().name(), teamcount_increment)
        if logdebug: logging.debug("run_chatword_stats (" + word + "): update_chatword_stats_teamcount_transaction for cwsyear")
        if teamcount_increment > 0: update_chatword_stats_teamcount_transaction(cwsyear.key(), team.key().name(), teamcount_increment)
        if logdebug: logging.debug("run_chatword_stats (" + word + "): update_chatword_stats_teamcount_transaction for cwsalltime")
        if teamcount_increment > 0: update_chatword_stats_teamcount_transaction(cwsalltime.key(), team.key().name(), teamcount_increment)

    if step in [0,2,4]:
        # hacks to get around GAE "ReferenceProperty failed to be resolved" bugs
        cwshour.timespan.key()
        cwsday.timespan.key()
        cwsmonth.timespan.key()
        cwsyear.timespan.key()
        cwsalltime.timespan.key()

        #team stats
        if logdebug: logging.debug("run_chatword_stats (" + word + "): get_or_insert_by_values for cwsteamhour")
        cwsteamhour = dygmodel.TeamChatWordStats.get_or_insert_by_values(team,cwshour,date=datetime)
        if logdebug: logging.debug("run_chatword_stats (" + word + "): get_or_insert_by_values for cwsteamday")
        cwsteamday = dygmodel.TeamChatWordStats.get_or_insert_by_values(team,cwsday,date=datetime)
        if logdebug: logging.debug("run_chatword_stats (" + word + "): get_or_insert_by_values for cwsteammonth")
        cwsteammonth = dygmodel.TeamChatWordStats.get_or_insert_by_values(team,cwsmonth,date=datetime)
        if logdebug: logging.debug("run_chatword_stats (" + word + "): get_or_insert_by_values for cwsteamyear")
        cwsteamyear = dygmodel.TeamChatWordStats.get_or_insert_by_values(team,cwsyear,date=datetime)
        if logdebug: logging.debug("run_chatword_stats (" + word + "): get_or_insert_by_values for cwsteamalltime")
        cwsteamalltime = dygmodel.TeamChatWordStats.get_or_insert_by_values(team,cwsalltime,date=datetime)

        if logdebug: logging.debug("run_chatword_stats (" + word + "): increment_team_chatword_count_transaction for cwsteamhour")
        increment_team_chatword_count_transaction(cwsteamhour.key())
        if logdebug: logging.debug("run_chatword_stats (" + word + "): increment_team_chatword_count_transaction for cwsteamday")
        increment_team_chatword_count_transaction(cwsteamday.key())
        if logdebug: logging.debug("run_chatword_stats (" + word + "): increment_team_chatword_count_transaction for cwsteammonth")
        increment_team_chatword_count_transaction(cwsteammonth.key())
        if logdebug: logging.debug("run_chatword_stats (" + word + "): increment_team_chatword_count_transaction for cwsteamyear")
        increment_team_chatword_count_transaction(cwsteamyear.key())
        if logdebug: logging.debug("run_chatword_stats (" + word + "): increment_team_chatword_count_transaction for cwsteamalltime")
        increment_team_chatword_count_transaction(cwsteamalltime.key())

def increment_chatword_stats_timespan_transaction(key_val):
    count = 0
    while True:
        try:
            db.run_in_transaction(increment_chatword_stats_timespan, key_val)
            break
        except db.Timeout:
            count += 1
            if count==3:
                raise

def increment_chatword_stats_timespan(key_val):
    cws = dygmodel.ChatWordStats.get(key_val)
    cws.usagecount += 1
    cws.put()

def update_chatword_stats_teamcount_transaction(key_val, team_key_name, inc_value):
    count = 0
    while True:
        try:
            return db.run_in_transaction(update_chatword_stats_teamcount, key_val, team_key_name, inc_value)
        except db.Timeout:
            count += 1
            if count==3:
                raise

def update_chatword_stats_teamcount(key_val, team_key_name, inc_value):
    cws = dygmodel.ChatWordStats.get(key_val)
    if cws.timespanvalue == dygmodel.StatsTimeSpan.HOUR_SPAN:
        uniqueteamsusing = set(cws.uniqueteamsusing)
        if team_key_name not in uniqueteamsusing: cws.uniqueteamsusing.append(team_key_name)
        inc_value = len(cws.uniqueteamsusing) - cws.uniqueteamsusagecount

    if inc_value > 0:
        cws.uniqueteamsusagecount += inc_value
        cws.put()

    return inc_value

def increment_team_chatword_count_transaction(key_val):
    count = 0
    while True:
        try:
            db.run_in_transaction(increment_team_chatword_count, key_val)
            break
        except db.Timeout:
            count += 1
            if count==3:
                raise

def increment_team_chatword_count(key_val):
    tcws = dygmodel.TeamChatWordStats.get(key_val)
    tcws.usagecount += 1
    tcws.put()
