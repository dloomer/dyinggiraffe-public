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

import webapp2
import os
import sys
import datetime, time, calendar
import logging

import dygutil
import dygmodel
import dygfantasystatsmodel
import dygsettingsdata
import dygchatdata

from google.appengine.ext.webapp import template
from google.appengine.ext import webapp
from google.appengine.ext import db,search
from google.appengine.api import memcache
from google.appengine.api.labs import taskqueue
#from google.appengine.api import taskqueue

# DeadlineExceededError can live in two different places 
try: 
	# When deployed 
	from google.appengine.runtime import DeadlineExceededError 
except ImportError: 
	# In the development server 
	from google.appengine.runtime.apiproxy_errors import DeadlineExceededError

logdebug = True

class StatsUpdateHandler(webapp.RequestHandler):
	def get(self):
		data_kind = self.request.get("data_kind")
		settings_kind = ""
		update_count = 0
		total_update_count = int(self.request.get("total_update_count",default_value="0"))
		current_exception_count = int(self.request.get("current_exception_count",default_value="0"))
		completion_seconds = 0.0
		data_key = self.request.get("data_key")
		next_key = ""
		prev_settings_data_key = ""
		start_time = datetime.datetime.now()
		step = int(self.request.get("step",default_value="1"))
		try:
			if data_kind == "chatword":
				if data_key:
					count = 0
					while True:
						try:
							msg_chatword = dygmodel.ChatMessageChatWord.get(data_key)
							break
						except db.Timeout:
							count += 1
							if count == 3:
								raise
					if step >= 3:
						# add to totals
						allword_text = "_all_"
						count = 0
						while True:
							try:
								cw_temp = dygmodel.ChatWord.get_or_insert("cw_" + allword_text,word=allword_text, date=msg_chatword.chatmessage.date, hidden=True)
								break
							except db.Timeout:
								count += 1
								if count == 3:
									raise
						dygchatdata.run_chatword_stats(
							chatword = cw_temp,
							datetime = msg_chatword.chatmessage.date,
							team = msg_chatword.chatmessage.team,
							step = step)
					else:
						count = 0
						while True:
							try:
								cw_temp = msg_chatword.chatword
								break
							except db.Timeout:
								count += 1
								if count == 3:
									raise

						count = 0
						while True:
							try:
								dt_temp = msg_chatword.chatmessage.date
								break
							except db.Timeout:
								count += 1
								if count == 3:
									raise

						count = 0
						while True:
							try:
								tm_temp = msg_chatword.chatmessage.team
								break
							except db.Timeout:
								count += 1
								if count == 3:
									raise

						dygchatdata.run_chatword_stats(
							chatword = cw_temp,
							datetime = dt_temp,
							team = tm_temp,
							step = step)
					update_count += 1
					total_update_count += update_count
					data_key = str(msg_chatword.key())
			
					if step >= 4:
						step = 1
						msg_chatword.statscomplete = True
						count = 0
						while True:
							try:
								msg_chatword.put()
								break
							except db.Timeout:
								count += 1
								if count == 3:
									raise
					else:
						step += 1
						next_key = data_key
					
				if step == 1:
					q = dygmodel.ChatMessageChatWord.all()
					q.filter("statscomplete = ", False)
					q.order("messagedate")
					count = 0
					while True:
						try:
							next_msg_chatword = q.get()
							break
						except db.Timeout:
							count += 1
							if count == 3:
								raise
					if next_msg_chatword: next_key = str(next_msg_chatword.key())

			if data_kind == "chatmessage":
				for msg in dygmodel.ChatMessage.all().filter("statscomplete = ", False).order("date").fetch(10):
					t = taskqueue.Task(url='/tasks/chatmessage_stats', params={'msg_key_id': msg.key().id()}, method='GET')
					t.add(queue_name = 'chat-stats')

					msg.statscomplete = True
					msg.put()
					update_count += 1

				total_update_count += update_count

			if data_kind == "pagesettings":
				completion_flag = ""
				prev_settings_data_key = self.request.get("prev_settings_data_key")
				if data_key == "None": return
				if data_key:
					if data_key == "memcache":
						settings = memcache.get("dummy_pagesettings")
					else:
						settings = dygmodel.PageSettings.get(data_key)
					prev_settings = None
					if prev_settings_data_key: prev_settings = dygmodel.PageSettings.get(prev_settings_data_key)
				
					statsruncount = 0
					incompletestatsfound = 0
					LOOP_LIMIT = 1
					if incompletestatsfound == 0 and not settings.titleclosedout:
						if statsruncount == 0:
							logging.debug("Running titlecloseout")
							if dygsettingsdata.run_page_settings_stats(settings, prev_settings, "titlecloseout", LOOP_LIMIT):
								settings.titleclosedout = True
							else:
								incompletestatsfound += 1
							statsruncount += 1
						else:
							incompletestatsfound += 1
					if incompletestatsfound == 0 and not settings.titlestatscomplete:
						if statsruncount == 0:
							logging.debug("Running titlestats")
							if dygsettingsdata.run_page_settings_stats(settings, prev_settings, "titlestats", LOOP_LIMIT):
								settings.titlestatscomplete = True
							else:
								incompletestatsfound += 1
							statsruncount += 1
						else:
							incompletestatsfound += 1
					if incompletestatsfound == 0 and not settings.photosclosedout:
						if statsruncount == 0:
							logging.debug("Running photocloseout")
							if dygsettingsdata.run_page_settings_stats(settings, prev_settings, "photocloseout", LOOP_LIMIT):
								settings.photosclosedout = True
							else:
								incompletestatsfound += 1
							statsruncount += 1
						else:
							incompletestatsfound += 1
					if incompletestatsfound == 0 and not settings.photostatscomplete:
						if statsruncount == 0:
							logging.debug("Running photostats")
							if dygsettingsdata.run_page_settings_stats(settings, prev_settings, "photostats", LOOP_LIMIT):
								settings.photostatscomplete = True
							else:
								incompletestatsfound += 1
							statsruncount += 1
						else:
							incompletestatsfound += 1
					if incompletestatsfound == 0 and not settings.videosclosedout:
						if statsruncount == 0:
							logging.debug("Running videocloseout")
							if dygsettingsdata.run_page_settings_stats(settings, prev_settings, "videocloseout", LOOP_LIMIT):
								settings.videosclosedout = True
							else:
								incompletestatsfound += 1
							statsruncount += 1
						else:
							incompletestatsfound += 1
					if incompletestatsfound == 0 and not settings.videostatscomplete:
						if statsruncount == 0:
							logging.debug("Running videostats")
							if dygsettingsdata.run_page_settings_stats(settings, prev_settings, "videostats", LOOP_LIMIT):
								settings.videostatscomplete = True
							else:
								incompletestatsfound += 1
							statsruncount += 1
						else:
							incompletestatsfound += 1
					if incompletestatsfound == 0 and not settings.captionsclosedout:
						if statsruncount == 0:
							logging.debug("Running captioncloseout")
							if dygsettingsdata.run_page_settings_stats(settings, prev_settings, "captioncloseout", LOOP_LIMIT):
								settings.captionsclosedout = True
							else:
								incompletestatsfound += 1
							statsruncount += 1
						else:
							incompletestatsfound += 1
					if incompletestatsfound == 0 and not settings.captionstatscomplete:
						if statsruncount == 0:
							logging.debug("Running captionstats")
							if dygsettingsdata.run_page_settings_stats(settings, prev_settings, "captionstats", LOOP_LIMIT):
								settings.captionstatscomplete = True
							else:
								incompletestatsfound += 1
							statsruncount += 1
						else:
							incompletestatsfound += 1
					if incompletestatsfound == 0 and not settings.themeclosedout:
						if statsruncount == 0:
							logging.debug("Running themecloseout")
							if dygsettingsdata.run_page_settings_stats(settings, prev_settings, "themecloseout", LOOP_LIMIT):
								settings.themeclosedout = True
							else:
								incompletestatsfound += 1
							statsruncount += 1
						else:
							incompletestatsfound += 1
					if incompletestatsfound == 0 and not settings.themestatscomplete:
						if statsruncount == 0:
							logging.debug("Running themestats")
							if dygsettingsdata.run_page_settings_stats(settings, prev_settings, "themestats", LOOP_LIMIT):
								settings.themestatscomplete = True
							else:
								incompletestatsfound += 1
							statsruncount += 1
						else:
							incompletestatsfound += 1
				
					if incompletestatsfound == 0: 
						settings.allstatscomplete = True
						update_count += 1
						total_update_count += update_count

					if data_key != "memcache":
						settings.put()
						data_key = str(settings.key())

				if (not data_key) or settings.allstatscomplete:
					if data_key == "memcache":
						next_key = "None"
					else:
						q = dygmodel.PageSettings.all()
						q.filter("allstatscomplete = ", False)
						q.order("date")
						next_settings = q.get()
						if next_settings: 
							next_key = str(next_settings.key())
							prev_settings = dygsettingsdata.get_latest_settings(next_settings.date)
							if prev_settings: prev_settings_data_key = str(prev_settings.key())
						else:
							next_settings = dygsettingsdata.get_latest_settings()
							if datetime.datetime.now() - next_settings.date > datetime.timedelta(minutes=30):
								next_settings.date = datetime.datetime.now()
								next_settings.titlestatscomplete = False
								next_settings.photostatscomplete = False
								next_settings.videostatscomplete = False
								next_settings.captionstatscomplete = False
								next_settings.themestatscomplete = False
								next_settings.allstatscomplete = False
								memcache.set("dummy_pagesettings", next_settings)
								next_key = "memcache"
				else:
					next_key = data_key
			current_exception_count = 0
		except DeadlineExceededError:
			logging.info("catching exception")
			current_exception_count += 1
			if current_exception_count > 5:
				raise
			else:
				logging.error(str(sys.exc_info()[0]), exc_info=sys.exc_info())
				next_key = data_key
			
		end_time = datetime.datetime.now()
		td = end_time-start_time
		completion_seconds = td.seconds + float(td.microseconds) / 1000000
		template_values = {
			'data_kind': data_kind,
			'settings_kind': settings_kind,
			'data_key': data_key,
			'next_url': "/batch/stats_update?data_kind=" + data_kind + "&total_update_count=" + str(total_update_count) + "&current_exception_count=" + str(current_exception_count) + "&data_key=" + next_key + "&prev_settings_data_key=" + prev_settings_data_key + "&step=" + str(step),
			'update_count': update_count,
			'total_update_count': total_update_count,
			'completion_seconds': completion_seconds,
			'current_time': str(datetime.datetime.now()),
		}
		path = os.path.join(os.path.dirname(__file__), 'templates', 'stats_update_output.html')
		self.response.out.write(template.render(path, template_values))

class PageTitleTempHandler(webapp.RequestHandler):
	def get(self):
		total_calc_count = int(self.request.get("total_calc_count",default_value="0"))
		last_key = self.request.get("last_key")
		data_kind = "Photo"
		
		# Steps: 1. Change first 142 from UTC to Central; 2. Change first 819 from Central to UTC; 3. Change from UTC to Central based on date
		
		# Current: Step 1
		
		if last_key == "None": return
		
		last_dt = datetime.datetime(year=2007,month=3,day=23,hour=22,minute=33,second=52)
		#last_dt = datetime.datetime(year=2007,month=3,day=23,hour=17,minute=33,second=52)
		if last_key:
			q = db.GqlQuery("SELECT * FROM " + data_kind + " WHERE __key__ > :1 ORDER BY __key__", db.Key(last_key))
		else:
			q = db.GqlQuery("SELECT * FROM " + data_kind + " ORDER BY __key__")
		entities = q.fetch(1)
		
		last_key = None
		if entities and len(entities) > 0: last_key = str(entities[-1].key())
		calc_count = 0
		for entity in entities:
			#if entity.date < last_dt:
			if calc_count < 142:
				entity.date = entity.date.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)
				#entity.date = entity.date.replace(tzinfo=dygutil.Central_tzinfo()).astimezone(dygutil.UTC_tzinfo()).replace(tzinfo=None)
				calc_count += 1
		db.put(entities)

		calc_count = len(entities)
		total_calc_count += calc_count
		template_values = {
			'data_kind': data_kind,
			'next_url': "/batch/pagetitle_temp?data_kind=" + data_kind + "&total_calc_count=" + str(total_calc_count) + "&last_key=" + str(last_key),
			'calc_count': calc_count,
			'total_calc_count': total_calc_count,
			'current_time': str(datetime.datetime.now()),
		}
		path = os.path.join(os.path.dirname(__file__), 'templates', 'calculated_fields_output.html')
		self.response.out.write(template.render(path, template_values))


class StatsTempHandler(webapp.RequestHandler):
	def get(self):
		data_kind = self.request.get("data_kind")
		settings_kind = ""
		update_count = 0
		total_update_count = int(self.request.get("total_update_count",default_value="0"))
		completion_seconds = 0.0
		data_key = self.request.get("data_key")
		next_key = ""
		prev_settings_data_key = ""
		start_time = datetime.datetime.now()
		step = int(self.request.get("step",default_value="1"))

		if data_kind == "chatmessage":
			last_sort_index = ""
			if data_key:
				msg = dygmodel.ChatMessage.get(data_key)
				if not msg.statscomplete:
					print "done"
					return
					
				dt_central = msg.date.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo())

				hour_central = dt_central.hour
				day_central = dt_central.day
				month_central = dt_central.month
				year_central = dt_central.year

				tshour = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.HOUR_SPAN, year_central, month_central, day_central, hour_central)
				tsday = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.DAY_SPAN, year_central, month_central, day_central, 0)
				tsmonth = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.MONTH_SPAN, year_central, month_central, 1, 0)
				tsyear = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.YEAR_SPAN, year_central, 1, 1, 0)
				tsalltime = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.ALL_TIME_SPAN, 0, 0, 0, 0)

				db.run_in_transaction(dygchatdata.increment_stats_timespan, tshour.key(), dt_central)
				db.run_in_transaction(dygchatdata.increment_stats_timespan, tsday.key(), dt_central)
				db.run_in_transaction(dygchatdata.increment_stats_timespan, tsmonth.key(), dt_central)
				db.run_in_transaction(dygchatdata.increment_stats_timespan, tsyear.key(), dt_central)
				db.run_in_transaction(dygchatdata.increment_stats_timespan, tsalltime.key(), dt_central)

				update_count += 1
				data_key = str(msg.key())
				last_sort_index = msg.sortindex

			total_update_count += update_count

			if last_sort_index == "": last_sort_index = "2007-10-01 03:02:06"
			
			q = dygmodel.ChatMessage.all()
			q.filter("sortindex > ", last_sort_index)
			q.order("sortindex")
			next_msg = q.get()
			if next_msg: next_key = str(next_msg.key())

		end_time = datetime.datetime.now()
		td = end_time-start_time
		completion_seconds = td.seconds + float(td.microseconds) / 1000000
		template_values = {
			'data_kind': data_kind,
			'settings_kind': settings_kind,
			'data_key': data_key,
			'next_url': "/batch/stats_temp?data_kind=" + data_kind + "&total_update_count=" + str(total_update_count) + "&data_key=" + next_key + "&prev_settings_data_key=" + prev_settings_data_key + "&step=" + str(step),
			'update_count': update_count,
			'total_update_count': total_update_count,
			'completion_seconds': completion_seconds,
			'current_time': str(datetime.datetime.now()),
		}
		path = os.path.join(os.path.dirname(__file__), 'templates', 'stats_update_output.html')
		self.response.out.write(template.render(path, template_values))

class EntityPurgeHandler(webapp.RequestHandler):
	def get(self):
		data_kind = self.request.get("data_kind")
		total_delete_count = int(self.request.get("total_delete_count",default_value="0"))
		if data_kind:
			entities = db.GqlQuery("SELECT * FROM " + data_kind).fetch(20)
			delete_count = len(entities)
			total_delete_count += delete_count
			db.delete(entities)
			template_values = {
				'data_kind': data_kind,
				'next_url': "/batch/purge_entities?data_kind=" + data_kind + "&total_delete_count=" + str(total_delete_count),
				'delete_count': delete_count,
				'total_delete_count': total_delete_count,
				'current_time': str(datetime.datetime.now()),
			}
			path = os.path.join(os.path.dirname(__file__), 'templates', 'entity_purge_output.html')
			self.response.out.write(template.render(path, template_values))

class StatsResetHandler(webapp.RequestHandler):
	def get(self):
		data_kind = self.request.get("data_kind")
		total_reset_count = int(self.request.get("total_reset_count",default_value="0"))
		if data_kind:
			if data_kind == "chatword":
				entities = dygmodel.ChatMessageChatWord.all().filter("statscomplete = ", True).fetch(20)
				for entity in entities: entity.statscomplete = False
			if data_kind == "chatmessage":
				entities = dygmodel.ChatMessage.all().filter("statscomplete = ", True).fetch(20)
				for entity in entities: entity.statscomplete = False
			if data_kind == "pagesettings":
				entities = dygmodel.PageSettings.all().filter("date > ", datetime.datetime(year=2008,month=12,day=6)).filter("allstatscomplete = ", True).fetch(20)
				for entity in entities: 
					entity.titlestatscomplete = False
					entity.titleclosedout = False
					entity.photostatscomplete = False
					entity.photosclosedout = False
					entity.videostatscomplete = False
					entity.videosclosedout = False
					entity.captionstatscomplete = False
					entity.captionsclosedout = False
					entity.themestatscomplete = False
					entity.themeclosedout = False
					entity.allstatscomplete = False
			if data_kind == "settingselementstats":
				entities = []
				entities2 = dygmodel.SettingsElementStats.all().filter("timespanvalue = ", dygmodel.StatsTimeSpan.HOUR_SPAN).filter("year_central = ", 2008).filter("month_central = ", 12).fetch(5)
				if entities2: entities.extend(entities2)
				logging.debug("entities2=" + str(entities2))
				entities2 = dygmodel.SettingsElementStats.all().filter("timespanvalue = ", dygmodel.StatsTimeSpan.DAY_SPAN).filter("year_central = ", 2008).filter("month_central = ", 12).fetch(5)
				if entities2: entities.extend(entities2)
				entities2 = dygmodel.SettingsElementStats.all().filter("timespanvalue = ", dygmodel.StatsTimeSpan.MONTH_SPAN).filter("year_central = ", 2008).filter("month_central = ", 12).fetch(5)
				if entities2: entities.extend(entities2)
				entities2 = dygmodel.SettingsElementStats.all().filter("year_central = ", 2009).fetch(5)
				if entities2: entities.extend(entities2)
				db.delete(entities)
					
			if data_kind != "settingselementstats":
				db.put(entities)
			reset_count = len(entities)
			total_reset_count += reset_count
			template_values = {
				'data_kind': data_kind,
				'next_url': "/batch/stats_reset?data_kind=" + data_kind + "&total_reset_count=" + str(total_reset_count),
				'reset_count': reset_count,
				'total_reset_count': total_reset_count,
				'current_time': str(datetime.datetime.now()),
			}
			path = os.path.join(os.path.dirname(__file__), 'templates', 'stats_reset_output.html')
			self.response.out.write(template.render(path, template_values))

class CleanChatwordsHandler(webapp.RequestHandler):
	def get(self):
		data_kind = self.request.get("data_kind")
		total_calc_count = int(self.request.get("total_calc_count",default_value="0"))
		last_key = self.request.get("last_key")
		batch_size = 10
		if data_kind:
			if last_key == "None": return
			if last_key:
				q = db.GqlQuery("SELECT * FROM " + data_kind + " WHERE __key__ > :1 ORDER BY __key__", db.Key(last_key))
			else:
				q = db.GqlQuery("SELECT * FROM " + data_kind + " ORDER BY __key__")
			entities = q.fetch(batch_size)
			last_key = None
			if entities and len(entities) > 0: last_key = str(entities[-1].key())
			delete_entities = []
			update_entities = []
			stopwords = dygutil.fetch_stopwords()
			for entity in entities:
				if data_kind == "ChatMessageChatWord":
					try:
						word = entity.chatword.word
					except:
						word = "_deleteme_"
				else:
					word = entity.word
				if word in stopwords or word == "_deleteme_":
					delete_entities.append(entity)
					if data_kind == "ChatWordStats":
						cw_all_key_name = "cw__all_"
						ts_key_name = "ts_" + str(entity.timespanvalue) + "_" + str(entity.year_central) + "_" + str(entity.month_central) + "_" + str(entity.day_central) + "_" + str(entity.hour_central)
						cws_key_name = "cws_" + ts_key_name + "_" + cw_all_key_name
						cws = None
						for update_entity in update_entities:
							if update_entity.key().name() == cws_key_name:
								cws = update_entity
								break
						if not cws:
							cws = dygmodel.ChatWordStats.get_by_key_name(cws_key_name)
							if cws: update_entities.append(cws)
						if cws:
							cws.usagecount -= entity.usagecount
					if data_kind == "TeamChatWordStats":
						cw_all_key_name = "cw__all_"
						ts_key_name = "ts_" + str(entity.timespanvalue) + "_" + str(entity.year_central) + "_" + str(entity.month_central) + "_" + str(entity.day_central) + "_" + str(entity.hour_central)
						cws_key_name = "cws_" + ts_key_name + "_" + cw_all_key_name
						cwsteam_key_name = "tcws_" + entity.team.key().name() + "_" + cws_key_name
						cwsteam = None
						for update_entity in update_entities:
							if update_entity.key().name() == cwsteam_key_name:
								cwsteam = update_entity
								break
						if not cwsteam: 
							cwsteam = dygmodel.TeamChatWordStats.get_by_key_name(cwsteam_key_name)
							if cwsteam: update_entities.append(cwsteam)
						if cwsteam:
							cwsteam.usagecount -= entity.usagecount
						
			db.delete(delete_entities)
			db.put(update_entities)
			
			calc_count = len(delete_entities)
			total_calc_count += calc_count
			template_values = {
				'data_kind': data_kind,
				'next_url': "/batch/clean_chatwords?data_kind=" + data_kind + "&total_calc_count=" + str(total_calc_count) + "&last_key=" + str(last_key),
				'calc_count': calc_count,
				'total_calc_count': total_calc_count,
				'current_time': str(datetime.datetime.now()),
			}
			path = os.path.join(os.path.dirname(__file__), 'templates', 'calculated_fields_output.html')
			self.response.out.write(template.render(path, template_values))

class CalculatedFieldsHandler(webapp.RequestHandler):
	def get(self):
		data_kind = self.request.get("data_kind")
		last_key = self.request.get("last_key")

		from google.appengine.ext import blobstore

		def get_new_blob_key(old_key):
			return blobstore.BlobMigrationRecord.get_new_blob_key(old_key)

		def migrate_photo(db_photo):
			if not db_photo.photo_blob_key:
				#print "no blob key."
				return
			blob_info = blobstore.BlobInfo.get(db_photo.photo_blob_key)
			if blob_info:
				#print "blob is okay."
				return
			else:
				db_photo.photo_blob_key = str(get_new_blob_key(db_photo.photo_blob_key))
			blob_info = blobstore.BlobInfo.get(db_photo.thumbnail_blob_key)
			if not blob_info:
				db_photo.thumbnail_blob_key = str(get_new_blob_key(db_photo.thumbnail_blob_key))
			if blobstore.BlobInfo.get(db_photo.photo_blob_key) and blobstore.BlobInfo.get(db_photo.thumbnail_blob_key):
				pass
			else:
				raise Exception("Blob key conversion failed")

		import dygmodel
		pagesettings = dygmodel.PageSettings.all().order("-date").get()
		migrate_photo(pagesettings.photo1)
		migrate_photo(pagesettings.photo2)
		migrate_photo(pagesettings.photo3)
		pagesettings.put()

		if data_kind:
			if last_key == "None": return
			if last_key:
				q = db.GqlQuery("SELECT * FROM " + data_kind + " WHERE __key__ > :1 ORDER BY __key__", db.Key(last_key))
			else:
				q = db.GqlQuery("SELECT * FROM " + data_kind + " ORDER BY __key__")
			batch_size = 20
			#if data_kind == "Photo" or data_kind == "YouTubeVideo": batch_size = 1
			entities = q.fetch(batch_size)
			last_key = None
			if len(entities) > 0:
				entities_to_put = []
				last_key = entities[-1].key()
				for entity in entities:
					if data_kind == "Photo":
						migrate_photo(entity)
					entity.set_calculated_fields()
					entities_to_put.append(entity)
				db.put(entities_to_put)
	
				t = taskqueue.Task(url='/batch/calculated_fields', params={'data_kind': data_kind, 'last_key': str(last_key)}, method='GET')
				t.add()

class AdHocHandler(webapp.RequestHandler):
	def get(self):
		last_key = self.request.get("last_key")

		from google.appengine.ext import blobstore

		if last_key == "None": return
		if last_key:
			q = db.GqlQuery("SELECT * FROM FantasyPlayerSeason WHERE season=KEY('FantasySeason', 'y_2015') AND __key__ > :1 ORDER BY __key__", db.Key(last_key))
		else:
			q = db.GqlQuery("SELECT * FROM FantasyPlayerSeason WHERE season=KEY('FantasySeason', 'y_2015') ORDER BY __key__")
		batch_size = 20
		entities = q.fetch(batch_size)
		last_key = None
		if len(entities) > 0:
			entities_to_put = []
			last_key = entities[-1].key()
			for entity in entities:
				if entity.player.mlbteamcode not in ["DET", "CLE"]: continue
				
				mlbteam = dygfantasystatsmodel.MLBTeam.get_by_key_name(entity.player.mlbteamcode)

				projectionsmultiplier = float(mlbteam.endseasongames) / float(mlbteam.games) if mlbteam.games > 0 else 0.0
				entity.player.fpts_year0_projected = entity.stat_fpts * projectionsmultiplier
				entity.player.set_calculated_fields()
				entities_to_put.append(entity.player)
			db.put(entities_to_put)

			t = taskqueue.Task(url='/batch/adhoc', params={'last_key': str(last_key)}, method='GET')
			t.add()

class CountEntitiesHandler(webapp.RequestHandler):
	def get(self):
		data_kind = self.request.get("data_kind")
		total_count = int(self.request.get("total_count",default_value="0"))
		last_key = self.request.get("last_key")
		if data_kind:
			if last_key == "None":
				self.response.out.write(str(total_count))
				return
			if last_key:
				q = db.GqlQuery("SELECT * FROM " + data_kind + " WHERE __key__ > :1 ORDER BY __key__", db.Key(last_key))
			else:
				q = db.GqlQuery("SELECT * FROM " + data_kind + " ORDER BY __key__")
			entities = q.fetch(100)
			last_key = None
			if entities and len(entities) > 0: last_key = str(entities[-1].key())

			new_count = 0
			for entity in entities: 
				if entity.statscomplete == True or entity.statscomplete == False:
					new_count += 1
			#new_count = len(entities)
			total_count += new_count
			template_values = {
				'data_kind': data_kind,
				'next_url': "/batch/count_entities?data_kind=" + data_kind + "&total_count=" + str(total_count) + "&last_key=" + str(last_key),
				'new_count': new_count,
				'total_count': total_count,
				'current_time': str(datetime.datetime.now()),
			}
			path = os.path.join(os.path.dirname(__file__), 'templates', 'count_entities_output.html')
			self.response.out.write(template.render(path, template_values))

class InitializePropertyHandler(webapp.RequestHandler):
	def get(self):
		total_init_count = int(self.request.get("total_init_count",default_value="0"))
		last_key = self.request.get("last_key")
		if last_key == "None": return
		if last_key:
			q = db.GqlQuery("SELECT * FROM ChatMessage WHERE __key__ > :1 ORDER BY __key__", db.Key(last_key))
		else:
			q = db.GqlQuery("SELECT * FROM ChatMessage ORDER BY __key__")
		entities = q.fetch(50)
		last_key = None
		if entities and len(entities) > 0: last_key = str(entities[-1].key())
		for entity in entities:
			if not entity.statscomplete:
				entity.statscomplete = False
		db.put(entities)

		init_count = len(entities)
		total_init_count += init_count
		template_values = {
			'next_url': "/batch/initialize_property?total_init_count=" + str(total_init_count) + "&last_key=" + str(last_key),
			'init_count': init_count,
			'total_init_count': total_init_count,
			'current_time': str(datetime.datetime.now()),
		}
		path = os.path.join(os.path.dirname(__file__), 'templates', 'initialize_property_output.html')
		self.response.out.write(template.render(path, template_values))

class DateCorrectHandler(webapp.RequestHandler):
	def get(self):
		data_kind = self.request.get("data_kind")
		total_update_count = int(self.request.get("total_update_count",default_value="0"))
		last_key = self.request.get("last_key")
		completion_seconds = 0.0
		update_count = 0
		start_time = datetime.datetime.now()
		if data_kind == "chatword":
			if last_key == "None": return
			if last_key:
				q = db.GqlQuery("SELECT * FROM ChatWord WHERE __key__ > :1 ORDER BY __key__", db.Key(last_key))
			else:
				q = db.GqlQuery("SELECT * FROM ChatWord ORDER BY __key__")
			entities = q.fetch(20)
			last_key = None
			if entities and len(entities) > 0: last_key = str(entities[-1].key())
			for entity in entities: entity.date = entity.date.replace(tzinfo=dygutil.Central_tzinfo()).astimezone(dygutil.UTC_tzinfo()).replace(tzinfo=None)
		elif data_kind == "chatmessage":
			if last_key == "None": return
			if last_key:
				q = db.GqlQuery("SELECT * FROM ChatMessage WHERE __key__ > :1 ORDER BY __key__", db.Key(last_key))
			else:
				q = db.GqlQuery("SELECT * FROM ChatMessage ORDER BY __key__")
			entities = q.fetch(50)
			last_key = None
			if entities and len(entities) > 0: last_key = str(entities[-1].key())
			for entity in entities: 
				entity.date = entity.date.replace(tzinfo=dygutil.Central_tzinfo()).astimezone(dygutil.UTC_tzinfo()).replace(tzinfo=None)
				team_index_str = entity.sortindex[entity.sortindex.find("|")+1:]
				entity.set_calculated_fields()
				entity.sortindex = str(dygutil.string_to_datetime(str(entity.date))) + "|" + team_index_str
		
		db.put(entities)
			
		update_count = len(entities)
		total_update_count += update_count

		end_time = datetime.datetime.now()
		td = end_time-start_time
		completion_seconds = td.seconds + float(td.microseconds) / 1000000
		template_values = {
			'data_kind': data_kind,
			'next_url': "/batch/date_correct?data_kind=" + data_kind + "&total_update_count=" + str(total_update_count) + "&last_key=" + str(last_key),
			'update_count': update_count,
			'total_update_count': total_update_count,
			'completion_seconds': completion_seconds,
			'current_time': str(datetime.datetime.now()),
		}
		path = os.path.join(os.path.dirname(__file__), 'templates', 'date_correct_output.html')
		self.response.out.write(template.render(path, template_values))

class DevDataHandler(webapp.RequestHandler):
	def get(self):
	
		team = dygmodel.Team(key_name="t_1",
			cbsteamid=5, 
			email="sportsline@loomer.org",
			google_id="dloomer@gmail.com",
			ownername="Dave Loomer",
			postindex=0,
			teamid=1,
			teamname="Staines West End Massive",
			user_google_login=True,
			)
		team.put()
		team = dygmodel.Team(key_name="t_10",
			cbsteamid=8, 
			email="sportsline@loomer.org",
			ownername="Nate Tormoehlen",
			postindex=0,
			teamid=10,
			teamname="Vandelay Importers and Exporters",
			user_google_login=False,
			)
		team.put()
		team = dygmodel.Team(key_name="t_11",
			cbsteamid=13,
			email="sportsline@loomer.org",
			ownername="Bart Beatty",
			postindex=0,
			teamid=11,
			teamname="It's not just a hairstyle, it's a lifestyle",
			user_google_login=False,
			)
		team.put()
		team = dygmodel.Team(key_name="t_12",
			cbsteamid=6, 
			email="michael_judy513@hotmail.com",
			google_id="None@gmail.com",
			ownername="Da Dog",
			postindex=0,
			teamid=12,
			teamname="SHOCKER",
			user_google_login=False,
			)
		team.put()
		team = dygmodel.Team(key_name="t_13",
			cbsteamid=16, 
			email="michael_judy513@hotmail.com",
			google_id="None@gmail.com",
			ownername="KEITH STRADLEY",
			postindex=0,
			teamid=13,
			teamname="1984",
			user_google_login=False,
			)
		team.put()
		team = dygmodel.Team(key_name="t_14",
			cbsteamid=17, 
			email="michael_judy513@hotmail.com",
			google_id="None@gmail.com",
			ownername="Sal Fasano",
			postindex=0,
			teamid=14,
			teamname="The Great Moustachios",
			user_google_login=False,
			)
		team.put()
		team = dygmodel.Team(key_name="t_15",
			cbsteamid=7, 
			email="michael_judy513@hotmail.com",
			google_id="None@gmail.com",
			ownername="matt schuster",
			postindex=0,
			teamid=15,
			teamname="the crappiest team",
			user_google_login=False,
			)
		team.put()
		team = dygmodel.Team(key_name="t_2",
			cbsteamid=14, 
			email="michael_judy513@hotmail.com",
			google_id="None@gmail.com",
			ownername="Trent Tormoehlen",
			postindex=0,
			teamid=2,
			teamname="Circle K's",
			user_google_login=False,
			)
		team.put()
		team = dygmodel.Team(key_name="t_4",
			cbsteamid=1, 
			email="michael_judy513@hotmail.com",
			google_id="None@gmail.com",
			ownername="Andrew P. Peterson",
			postindex=0,
			teamid=4,
			teamname="The Mighty Moobs",
			user_google_login=False,
			)
		team.put()
		team = dygmodel.Team(key_name="t_5",
			cbsteamid=4, 
			email="michael_judy513@hotmail.com",
			google_id="None@gmail.com",
			ownername="Da Dog",
			postindex=0,
			teamid=5,
			teamname="SHOCKER",
			user_google_login=False,
			)
		team.put()
		team = dygmodel.Team(key_name="t_6",
			cbsteamid=12, 
			email="michael_judy513@hotmail.com",
			google_id="None@gmail.com",
			ownername="Calvin P. Reese",
			postindex=0,
			teamid=6,
			teamname="Les Expos de Montreal",
			user_google_login=False,
			)
		team.put()
		team = dygmodel.Team(key_name="t_7",
			cbsteamid=2, 
			email="michael_judy513@hotmail.com",
			google_id="None@gmail.com",
			ownername="Michael Ermitage",
			postindex=0,
			teamid=7,
			teamname="Nuke Laloosh and the Upton Brothers Meat",
			user_google_login=False,
			)
		team.put()
		team = dygmodel.Team(key_name="t_8",
			cbsteamid=15, 
			email="michael_judy513@hotmail.com",
			google_id="None@gmail.com",
			ownername="Ben Houg",
			postindex=0,
			teamid=8,
			teamname="Ben's Bell-Ends",
			user_google_login=False,
			)
		team.put()
		team = dygmodel.Team(key_name="t_9",
			cbsteamid=9, 
			email="michael_judy513@hotmail.com",
			google_id="None@gmail.com",
			ownername="Phil Sauer",
			postindex=0,
			teamid=9,
			teamname="PJ and the Bandits",
			user_google_login=False,
			)
		team.put()

		settings = dygfantasystatsmodel.SalaryCapSettings(capvalue_other=15.0)
		settings.put()
		
		theme = dygmodel.Theme(
			key_name="basic.css",
			name="Basic",
			stylesheet="basic.css",
		)
		theme.put()
		
		season = dygfantasystatsmodel.FantasySeason.get_or_insert_by_values(2010)
		season.startdate=datetime.datetime(2010,4,1)
		season.enddate=datetime.datetime(2010,10,1)
		season.put()

		team = dygfantasystatsmodel.FantasyTeam(year=2010,teamname="Staines West End Massive", cbsteamid=5, franchiseteamid=1)
		team.put()

		team = dygfantasystatsmodel.FantasyTeam(year=2010,teamname="SHOCKER", cbsteamid=8, franchiseteamid=10)
		team.put()

		team = dygfantasystatsmodel.FantasyTeam(year=2010,teamname="SHOCKER", cbsteamid=13, franchiseteamid=11)
		team.put()

		team = dygfantasystatsmodel.FantasyTeam(year=2010,teamname="SHOCKER", cbsteamid=6, franchiseteamid=12)
		team.put()

		team = dygfantasystatsmodel.FantasyTeam(year=2010,teamname="SHOCKER", cbsteamid=16, franchiseteamid=13)
		team.put()

		team = dygfantasystatsmodel.FantasyTeam(year=2010,teamname="SHOCKER", cbsteamid=17, franchiseteamid=14)
		team.put()

		team = dygfantasystatsmodel.FantasyTeam(year=2010,teamname="SHOCKER", cbsteamid=7, franchiseteamid=15)
		team.put()

		team = dygfantasystatsmodel.FantasyTeam(year=2010,teamname="SHOCKER", cbsteamid=14, franchiseteamid=2)
		team.put()

		team = dygfantasystatsmodel.FantasyTeam(year=2010,teamname="SHOCKER", cbsteamid=1, franchiseteamid=4)
		team.put()

		team = dygfantasystatsmodel.FantasyTeam(year=2010,teamname="SHOCKER", cbsteamid=4, franchiseteamid=5)
		team.put()

		team = dygfantasystatsmodel.FantasyTeam(year=2010,teamname="SHOCKER", cbsteamid=12, franchiseteamid=6)
		team.put()

		team = dygfantasystatsmodel.FantasyTeam(year=2010,teamname="SHOCKER", cbsteamid=2, franchiseteamid=7)
		team.put()

		team = dygfantasystatsmodel.FantasyTeam(year=2010,teamname="SHOCKER", cbsteamid=15, franchiseteamid=8)
		team.put()

		team = dygfantasystatsmodel.FantasyTeam(year=2010,teamname="SHOCKER", cbsteamid=9, franchiseteamid=9)
		team.put()

class MemcacheAssertionsHandler(webapp.RequestHandler):
	def get(self):
		latestsettings = dygsettingsdata.get_latest_settings()
		if latestsettings is not None:
			dygutil.settings_to_memcache(latestsettings)
		import random
		random.seed()
		rand_num = random.randrange(10000)
		memcache.set("rand", rand_num)
		assert memcache.get("rand") == rand_num

		q = db.GqlQuery("SELECT * FROM ChatMessage " + 
					"ORDER BY sortindex DESC")
		chatmessages = q.fetch(1)
		cachedmessages = [m.to_dict() for m in chatmessages]
		logging.info("cachedmessages[0]['sortindex']=%s; memcache.get(\"newestsortindex\")=%s" % (cachedmessages[0]['sortindex'], memcache.get("newestsortindex")))
		assert cachedmessages[0]['sortindex'] == memcache.get("newestsortindex")

app = webapp2.WSGIApplication([
		('/batch/stats_update', StatsUpdateHandler), \
		('/batch/stats_reset', StatsResetHandler), \
		('/batch/date_correct', DateCorrectHandler), \
		('/batch/purge_entities', EntityPurgeHandler), \
		('/batch/calculated_fields', CalculatedFieldsHandler), \
		('/batch/adhoc', AdHocHandler), \
		('/batch/initialize_property', InitializePropertyHandler), \
		('/batch/clean_chatwords', CleanChatwordsHandler), \
		('/batch/count_entities', CountEntitiesHandler), \
		('/batch/pagetitle_temp', PageTitleTempHandler), \
		('/batch/dev_data', DevDataHandler), \
		('/batch/memcache_assertions', MemcacheAssertionsHandler),
		], \
                                       debug=True)
