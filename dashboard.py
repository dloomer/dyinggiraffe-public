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
import datetime, time, calendar
import logging

import dygutil
import dygmodel
import dygsettingsdata
import dygchatdata

from google.appengine.ext.webapp import template
from google.appengine.ext import webapp
from google.appengine.ext import db,search
from google.appengine.api import memcache

import jinja2
jinja_environment = jinja2.Environment(
		loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
		extensions=['jinja2htmlcompress.SelectiveHTMLCompress'])
logdebug = True
CHAT_ARCHIVE_PAGE_SIZE = 100
PHOTO_ARCHIVE_PAGE_SIZE = 15

global months,days
months = ["January","February","March","April","May","June","July","August","September","October","November","December"]
days = [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31]

class AdminHandler(webapp.RequestHandler):
	def get(self, tab="admin"):
		firefox_win, ie_win, team_owner_name, settingsdict = get_initial_values(self)
		themes = db.GqlQuery("SELECT * FROM Theme " +
						"ORDER BY name")
		template_values = {
			'team_owner_name': team_owner_name,
			'title': settingsdict["pagetitle"],
			'prompt': settingsdict["prompt"],
			'url1': settingsdict["url1"],
			'url2': settingsdict["url2"],
			'url3': settingsdict["url3"],
			'caption1': settingsdict.get("caption1") if settingsdict.get("caption1") else "",
			'caption2': settingsdict.get("caption2") if settingsdict.get("caption2") else "",
			'caption3': settingsdict.get("caption3") if settingsdict.get("caption3") else "",
			'theme': settingsdict["theme"],
			'themes': themes,
			'firefox_win': firefox_win,
			'ie_win': ie_win,
		}
		template = jinja_environment.get_template('templates/admin.html')
		self.response.out.write(template.render(template_values))
	def post(self,tab=None,section=None):
		tab = self.request.get("tab",default_value="admin")
		if tab == "admin":
			if self.request.get("url1") == '' or self.request.get("url2") == '' or self.request.get("url3") == '' or self.request.get("title") == '':
				self.redirect("/")
				return

			if memcache.get("settings_lock") and memcache.get("settings_lock") == True:
				self.redirect("/admin?error=lock")

			memcache.set("settings_lock", True, time=30)
			settings = dygsettingsdata.update_settings(self)

			dygutil.settings_to_memcache(settings)
			memcache.set("settings_lock", False)
			self.redirect("/")
		elif tab == "prefs":
			dygutil.sethidephotos(self,(self.request.get("hide_photos")=="on"))
			dygutil.sethidecountdown(self,(self.request.get("hide_countdown")=="on"))
			self.redirect("/")

class PrefsHandler(webapp.RequestHandler):
	def get(self):
		firefox_win, ie_win, team_owner_name, settingsdict = get_initial_values(self)
		team_key_name = dygutil.getteamid(self,enforce=True)
		team = dygmodel.Team.get_by_key_name(team_key_name)
		hidephotos = dygutil.gethidephotos(self)
		hidecountdown = dygutil.gethidecountdown(self)
		hideinlinemedia = dygutil.gethideinlinemedia(self)
		template_values = {
			'team_owner_name': team_owner_name,
			'google_id': team.google_id,
			'user_google_login': team.user_google_login,
			'hidephotos': hidephotos,
			'hidecountdown': hidecountdown,
			'hideinlinemedia': hideinlinemedia,
			'theme': settingsdict["theme"],
			'firefox_win': firefox_win,
			'ie_win': ie_win,
		}
		template = jinja_environment.get_template('templates/prefs.html')
		self.response.out.write(template.render(template_values))
	def post(self):
		team_key_name = dygutil.getteamid(self,enforce=True)
		team = dygmodel.Team.get_by_key_name(team_key_name)
		team.ownername = self.request.get("team_owner_name")
		google_id = self.request.get("google_id")
		if google_id.find("@") < 1: google_id += "@gmail.com"
		team.google_id = google_id
		team.user_google_login = (self.request.get("user_google_login")=="on")
		team.put()

		teams = memcache.get("teams")
		teams[team_key_name] = team
		memcache.set("teams",teams)

		team_ownernames = memcache.get("team_ownernames")
		if not team_ownernames: team_ownernames = {}
		team_ownernames[team_key_name] = team.ownername
		memcache.set("team_ownernames",team_ownernames)

		dygutil.sethidephotos(self,(self.request.get("hide_photos")=="on"))
		dygutil.sethidecountdown(self,(self.request.get("hide_countdown")=="on"))
		dygutil.sethideinlinemedia(self,(self.request.get("hide_inline_media")=="on"))
		self.redirect("/")

class ChatArchiveHandler(webapp.RequestHandler):
	def get(self):
		firefox_win, ie_win, team_owner_name, settingsdict = get_initial_values(self)
		teams,years,months,days = get_dropdown_values()

		if self.request.get("action") == "search" or self.request.get("action") == "ajax_search":
			keywords = self.request.get("keywords")
			year_central = int(self.request.get("year"))
			month_central = int(self.request.get("month",default_value="0"))
			day_central = int(self.request.get("day",default_value="0"))
			hour_central = int(self.request.get("hour",default_value="-1"))
			generate_fake = (self.request.get("generate_fake",default_value="false").lower() == "true")
			team = None
			teamkeyname = self.request.get("team")
			if teamkeyname != "":
				team = dygmodel.Team.get_by_key_name(teamkeyname)
			if self.request.get("firstdate"):
				firstdate = dygutil.string_to_datetime(self.request.get("firstdate"))
			else:
				firstdate = None

			q = dygmodel.ChatMessage.all()
			if keywords != "":
				q.search(keywords)
			if team: q.filter("team = ", team)
			if year_central > 0:
				if month_central > 0:
					if day_central > 0:
						if hour_central > -1:
							startdatetime_central = datetime.datetime(year_central, month_central, day_central, hour_central, 0, 0)
							enddatetime_central = startdatetime_central + datetime.timedelta(hours=1)
						else:
							startdatetime_central = datetime.datetime(year_central, month_central, day_central)
							enddatetime_central = startdatetime_central + datetime.timedelta(days=1)
					else:
						startdatetime_central = datetime.datetime(year_central, month_central, 1)
						enddatetime_central = dygutil.add_months_to_datetime(startdatetime_central)
				else:
					startdatetime_central = datetime.datetime(year_central, 1, 1)
					enddatetime_central = datetime.datetime(year_central + 1, 1, 1)
				startdatetime_utc = startdatetime_central.replace(tzinfo=dygutil.Central_tzinfo()).astimezone(dygutil.UTC_tzinfo()).replace(tzinfo=None)
				enddatetime_utc = enddatetime_central.replace(tzinfo=dygutil.Central_tzinfo()).astimezone(dygutil.UTC_tzinfo()).replace(tzinfo=None)
				q.filter("date >= ", startdatetime_utc)
				q.filter("date < ", enddatetime_utc)
			if firstdate:
				q.filter("date < ", firstdate)
			q.order("-date")
			firstdatestr = ""
			has_more = False
			chatmessages = q.fetch(CHAT_ARCHIVE_PAGE_SIZE + 1)
			if len(chatmessages) > CHAT_ARCHIVE_PAGE_SIZE:
				has_more = True
				chatmessages = chatmessages[:CHAT_ARCHIVE_PAGE_SIZE]
			if chatmessages: firstdatestr = str(chatmessages[-1].date)

			fake_messages = []
			if generate_fake:
				user_message_grouping = {}
				for msg in chatmessages:
					if not msg.team_key_name:
						msg.team_key_name = msg.team.key().name()
					user_message_grouping.setdefault(msg.team_key_name, {}).setdefault('text_posts', []).append(msg.text)
				for team_key_name, user in user_message_grouping.items():
					user['markov'] = dygutil.MarkovChain(user['text_posts'])
					if team_key_name == "t_12":
						user['fake_user_name'] = "Fake DOGGER"
					else:
						real_team_ownername = dygchatdata.fetch_team_ownername(team_key_name)
						user['fake_user_name'] = "Fake " + real_team_ownername
						if real_team_ownername == real_team_ownername.upper():
							user['fake_user_name'] = user['fake_user_name'].upper()
						elif real_team_ownername == real_team_ownername.lower():
							user['fake_user_name'] = user['fake_user_name'].lower()
				for msg in chatmessages:
					user = user_message_grouping[msg.team_key_name]
					fake_messages.append({
						'teamownername': user['fake_user_name'],
						'htmltext': user['markov'].get_random_sentence(),
						'displaydate': msg.displaydate,
					})

			template_values = {
				'team_owner_name': team_owner_name,
				'theme': settingsdict["theme"],
				'teams': teams,
				'years': years,
				'months': months,
				'days': days,
				'year': year_central,
				'month': month_central,
				'day': day_central,
				'hour': hour_central,
				'team': teamkeyname,
				'keywords': keywords,
				'chatmessages': chatmessages,
				'fake_messages': fake_messages,
				'firstdate': firstdatestr,
				'has_more': has_more,
				'firefox_win': firefox_win,
				'ie_win': ie_win,
			}
		else:
			template_values = {
				'team_owner_name': team_owner_name,
				'theme': settingsdict["theme"],
				'teams': teams,
				'years': years,
				'months': months,
				'days': days,
				'year': 0,
				'hour': -1,
				'firefox_win': firefox_win,
				'ie_win': ie_win,
			}
		if self.request.get("action") == "ajax_search":
			#template_values["include_template_name"] = "templates/chat_message_output.html"
			#template = jinja_environment.get_template('templates/ajax_output.html')
			#nextmsgs = template.render(template_values).replace(u"\"", u"\\\"")
			template = jinja_environment.get_template('templates/chat_message_output.html')
			nextmsgs = template.render(template_values).replace(u"\"", u"\\\"").replace("\n", " ")
			self.response.out.write("nextmsgs=\"" + nextmsgs + "\";\r\n")
			self.response.out.write("has_more=" + str(has_more).lower() + ";\r\n")
			self.response.out.write("firstdate=\"" + firstdatestr + "\";\r\n")
		else:
			template = jinja_environment.get_template('templates/chat_archive.html')
			self.response.out.write(template.render(template_values))

class PhotoArchiveHandler(webapp.RequestHandler):
	def get(self):
		firefox_win, ie_win, team_owner_name, settingsdict = get_initial_values(self)
		teams,years,months,days = get_dropdown_values()
		if self.request.get("action") == "search" or self.request.get("action") == "ajax_search":
			keywords = self.request.get("keywords")
			year_central = int(self.request.get("year"))
			month_central = int(self.request.get("month",default_value="0"))
			day_central = int(self.request.get("day",default_value="0"))
			hour_central = int(self.request.get("hour",default_value="-1"))
			elementkey = self.request.get("elementkey")
			if self.request.get("firstdate"):
				firstdate = dygutil.string_to_datetime(self.request.get("firstdate"))
			else:
				firstdate = None

			q = dygmodel.PageSettings.all()
			if elementkey:
				q.filter("elementkeys = ", elementkey)
			if keywords != "":
				q.search(keywords)
			if year_central > 0:
				if month_central > 0:
					if day_central > 0:
						if hour_central > -1:
							startdatetime_central = datetime.datetime(year_central, month_central, day_central, hour_central, 0, 0)
							enddatetime_central = startdatetime_central + datetime.timedelta(hours=1)
						else:
							startdatetime_central = datetime.datetime(year_central, month_central, day_central)
							enddatetime_central = startdatetime_central + datetime.timedelta(days=1)
					else:
						startdatetime_central = datetime.datetime(year_central, month_central, 1)
						enddatetime_central = dygutil.add_months_to_datetime(startdatetime_central)
				else:
					startdatetime_central = datetime.datetime(year_central, 1, 1)
					enddatetime_central = datetime.datetime(year_central + 1, 1, 1)
				startdatetime_utc = startdatetime_central.replace(tzinfo=dygutil.Central_tzinfo()).astimezone(dygutil.UTC_tzinfo()).replace(tzinfo=None)
				enddatetime_utc = enddatetime_central.replace(tzinfo=dygutil.Central_tzinfo()).astimezone(dygutil.UTC_tzinfo()).replace(tzinfo=None)
				q.filter("date >= ", startdatetime_utc)
				q.filter("date < ", enddatetime_utc)
			if firstdate:
				q.filter("date < ", firstdate)
			q.order("-date")
			firstdatestr = ""
			has_more = False
			settingsrecords = q.fetch(PHOTO_ARCHIVE_PAGE_SIZE + 1)
			if len(settingsrecords) > PHOTO_ARCHIVE_PAGE_SIZE:
				has_more = True
				settingsrecords = settingsrecords[:PHOTO_ARCHIVE_PAGE_SIZE]
			if settingsrecords: firstdatestr = str(settingsrecords[-1].date)

			template_values = {
				'team_owner_name': team_owner_name,
				'theme': settingsdict["theme"],
				'years': years,
				'months': months,
				'days': days,
				'year': year_central,
				'month': month_central,
				'day': day_central,
				'keywords': keywords,
				'elementkey': elementkey,
				'settingsrecords': settingsrecords,
				'has_more': has_more,
				'firstdate': firstdatestr,
				'firefox_win': firefox_win,
				'ie_win': ie_win,
			}
		else:
			template_values = {
				'team_owner_name': team_owner_name,
				'theme': settingsdict["theme"],
				'years': years,
				'months': months,
				'days': days,
				'year': 0,
				'firefox_win': firefox_win,
				'ie_win': ie_win,
			}
		if self.request.get("action") == "ajax_search":
			template_values["include_template_name"] = "photo_archive_record_output.html"
			template = jinja_environment.get_template('templates/ajax_output.html')
			nextdata = unicode(template.render(template_values),'utf-8').replace("\"", "\\\"")
			self.response.out.write("nextdata=\"" + nextdata + "\";\r\n")
			self.response.out.write("has_more=" + str(has_more).lower() + ";\r\n")
			self.response.out.write("firstdate=\"" + firstdatestr + "\";\r\n")
		else:
			template = jinja_environment.get_template('templates/photo_archive.html')
			self.response.out.write(template.render(template_values))

class ChatPostGeneratorHandler(webapp.RequestHandler):
	def get(self):
		teams,years,months,days = get_dropdown_values()
		firefox_win, ie_win, team_owner_name, settingsdict = get_initial_values(self)

		template_values = {
			'team_owner_name': team_owner_name,
			'theme': settingsdict["theme"],
			'teams': teams,
			'firefox_win': firefox_win,
			'ie_win': ie_win,
		}

		template = jinja_environment.get_template('templates/chat_generator.html')
		self.response.out.write(template.render(template_values))

class StatsHandler(webapp.RequestHandler):
	def get(self, section="posts"):
		chart = self.request.get("chart",default_value="total")

		year_central = int(self.request.get("year",default_value="0"))
		month_central = int(self.request.get("month",default_value="0"))
		team = None
		teamkeyname = self.request.get("team")
		if teamkeyname != "":
			team = dygmodel.Team.get_by_key_name(teamkeyname)
			if chart == "volume": chart = "total"
		elementkey = self.request.get("elementkey")

		if section == "posts":
			self.handle_posts(chart, team, teamkeyname, year_central, month_central, elementkey)
		elif section == "words":
			word = self.request.get("word",default_value="")
			self.handle_words(chart, team, teamkeyname, year_central, month_central, word)
		elif section == "records":
			self.handle_records()
		elif section in ["videos", "photos", "captions", "titles", "themes"]:
			self.handle_settings_elements(chart, team, teamkeyname, year_central, month_central, section)

	def handle_posts(self, chart, team, teamkeyname, year_central, month_central, elementkey):
		firefox_win, ie_win, team_owner_name, settingsdict = get_initial_values(self)
		teams, years, months, days = get_dropdown_values()

		showpostbyuserchart = False
		showwordtable = False
		showteamsummary = False
		chartresolution = "month"
		showpostchart = True
		showtotal = True
		if chart == "volume":
			charttitle = "User Volume"
		elif chart == "by_user":
			charttitle = "Posts By User"
		elif chart == "participation":
			charttitle = "Participation"
		else:
			charttitle = "Total Posts"

		if (chart == "total" or chart == "by_user") and not team: showteamsummary = True

		team_queries = None

		if team:
			charttitle += " for " + team.ownername
			basequery = dygmodel.TeamChatMessageStats.all().filter("team = ", team)
			q = dygmodel.TeamChatMessageStats.all().filter("team = ", team)
		else:
			basequery = dygmodel.StatsTimeSpan.all()
			if chart == "by_user":
				showpostbyuserchart = True
				showpostchart = False
				team_queries = []
				for t in dygmodel.Team.all().fetch(1000):
					team_queries.append([t,dygmodel.TeamChatMessageStats.all().filter("team = ", t)])
			else:
				if elementkey:
					q = dygmodel.SettingsElementStats.all().filter("element = ", db.get(db.Key(elementkey)))
				else:
					q = dygmodel.StatsTimeSpan.all()

		if chart == "volume" or chart == "participation": showtotal = False

		teamtotals = None

		if year_central > 0:
			if team_queries:
				for q in team_queries:
					q[1].filter("year_central = ", year_central)
				charttitle += " by Month - "
			else:
				q.filter("year_central = ", year_central)
				chartresolution = "day"
				charttitle += " by Day - "
			if month_central > 0:
				charttitle += months[month_central - 1] + " " + str(year_central)
				if team_queries:
					for q in team_queries:
						q[1].filter("month_central = ", month_central)
						q[1].filter("timespanvalue = ", dygmodel.StatsTimeSpan.DAY_SPAN)
				else:
					q.filter("month_central = ", month_central)
					q.filter("timespanvalue = ", dygmodel.StatsTimeSpan.DAY_SPAN)
				tot = 0
				r = basequery.filter("timespanvalue = ", dygmodel.StatsTimeSpan.MONTH_SPAN).filter("year_central = ", year_central).filter("month_central = ", month_central).get()
				if r: tot = r.postcount
				total_message = "Total Posts for Month: " + str(dygutil.format_number(tot))
				if not team: teamtotals = dygmodel.TeamChatMessageStats.all().filter("timespanvalue = ", dygmodel.StatsTimeSpan.MONTH_SPAN).filter("year_central = ", year_central).filter("month_central = ", month_central).order("-postcount").fetch(1000)
			else:
				charttitle += str(year_central)
				if team_queries:
					for q in team_queries:
						q[1].filter("timespanvalue = ", dygmodel.StatsTimeSpan.MONTH_SPAN)
				else:
					q.filter("timespanvalue = ", dygmodel.StatsTimeSpan.DAY_SPAN)
				tot = 0
				r = basequery.filter("timespanvalue = ", dygmodel.StatsTimeSpan.YEAR_SPAN).filter("year_central = ", year_central).get()
				if r: tot = r.postcount
				total_message = "Total Posts for Year: " + str(dygutil.format_number(tot))
				if not team: teamtotals = dygmodel.TeamChatMessageStats.all().filter("timespanvalue = ", dygmodel.StatsTimeSpan.YEAR_SPAN).filter("year_central = ", year_central).order("-postcount").fetch(1000)
		else:
			charttitle += " by Month"
			if team_queries:
				for q in team_queries:
					q[1].filter("timespanvalue = ", dygmodel.StatsTimeSpan.MONTH_SPAN)
			else:
				q.filter("timespanvalue = ", dygmodel.StatsTimeSpan.MONTH_SPAN)
			tot = 0
			r = basequery.filter("timespanvalue = ", dygmodel.StatsTimeSpan.ALL_TIME_SPAN).get()
			if r: tot = r.postcount
			total_message = "Total Posts All-Time: " + str(dygutil.format_number(tot))
			if not team: teamtotals = dygmodel.TeamChatMessageStats.all().filter("timespanvalue = ", dygmodel.StatsTimeSpan.ALL_TIME_SPAN).order("-postcount").fetch(1000)

		if team_queries:
			for q in team_queries:
				q[1].order("statsdate_central")
				q.append(q[1].fetch(1000))
		else:
			q.order("statsdate_central")
			pre_statsrecords = q.fetch(1000)

		def fill_in(pre_statsrecords, start_datetime=None, end_datetime=None):
			statsrecords = []
			if pre_statsrecords and len(pre_statsrecords) > 0:
				if year_central > 0 and month_central > 0:
					resolution = datetime.timedelta(days=1)
				else:
					resolution = datetime.timedelta(days=31)
				if start_datetime:
					if resolution.days == 31:
						last_datetime = dygutil.add_months_to_datetime(start_datetime,-1)
					else:
						last_datetime = start_datetime - resolution
				else:
					last_datetime = datetime.datetime(pre_statsrecords[0].year_central,pre_statsrecords[0].month_central,pre_statsrecords[0].day_central)
				for record in pre_statsrecords:
					this_datetime = datetime.datetime(record.year_central,record.month_central,record.day_central)
					while this_datetime - last_datetime > resolution:
						if resolution == datetime.timedelta(days=31):
							delta = dygutil.add_months_to_datetime(last_datetime) - last_datetime
						else:
							delta = resolution
						new_datetime = last_datetime + delta
						newrecord = dygmodel.StatsTimeSpan(
							timespanvalue=record.timespanvalue,
							year_central=new_datetime.year,
							month_central=new_datetime.month,
							day_central=new_datetime.day,
							hour_central=new_datetime.hour)
						statsrecords.append(newrecord)
						last_datetime = datetime.datetime(newrecord.year_central,newrecord.month_central,newrecord.day_central)
					statsrecords.append(record)
					last_datetime = this_datetime
				if end_datetime:
					if resolution.days == 31:
						resolution2 = datetime.timedelta(days=28)
					else:
						resolution2 = resolution

					this_datetime = datetime.datetime(pre_statsrecords[-1].year_central,pre_statsrecords[-1].month_central,pre_statsrecords[-1].day_central)
					while end_datetime - this_datetime >= resolution2:
						if resolution2.days == 28:
							delta = dygutil.add_months_to_datetime(this_datetime) - this_datetime
						else:
							delta = resolution2
						new_datetime = this_datetime + delta
						#logging.info("delta=" + str(delta))
						newrecord = dygmodel.StatsTimeSpan(
							timespanvalue=pre_statsrecords[-1].timespanvalue,
							year_central=new_datetime.year,
							month_central=new_datetime.month,
							day_central=new_datetime.day,
							hour_central=new_datetime.hour)
						statsrecords.append(newrecord)
						this_datetime = datetime.datetime(newrecord.year_central,newrecord.month_central,newrecord.day_central)
			return statsrecords

		statsrecords = []
		team_results = []
		rows = 0
		if team_queries:
			start_datetime = None
			end_datetime = None
			for q in team_queries:
				if len(q[2]):
					dt = datetime.datetime(q[2][0].year_central,q[2][0].month_central,q[2][0].day_central,q[2][0].hour_central)
					if not start_datetime or dt < start_datetime: start_datetime = dt

					dt = datetime.datetime(q[2][-1].year_central,q[2][-1].month_central,q[2][-1].day_central,q[2][-1].hour_central)
					if not end_datetime or dt > end_datetime: end_datetime = dt

			for q in team_queries:
				q.append(fill_in(q[2],start_datetime,end_datetime))
				if len(q[3]) > 0:
					rows = len(q[3])
					team_results.append(q)
		else:
			statsrecords = fill_in(pre_statsrecords)
			rows = len(statsrecords)

		teamrows = 0
		if teamtotals: teamrows = len(teamtotals)

		template_values = {
			'team_owner_name': team_owner_name,
			'theme': settingsdict["theme"],
			'teams': teams,
			'years': years,
			'months': months,
			'year': year_central,
			'month': month_central,
			'team': teamkeyname,
			'statsrecords': statsrecords,
			'team_results': team_results,
			'rows': rows,
			'section': "posts",
			'charttitle': charttitle,
			'chart': chart,
			'total_message': total_message,
			'showselectorbar': True,
			'showpostchart': showpostchart,
			'showpostbyuserchart': showpostbyuserchart,
			'showwordtable': showwordtable,
			'showteamsummary': showteamsummary,
			'showtotal': showtotal,
			'teamtotals': teamtotals,
			'teamrows': teamrows,
			'showteamdropdown': True,
			'chartresolution': chartresolution,
			'firefox_win': firefox_win,
			'ie_win': ie_win,
		}

		path = os.path.join(os.path.dirname(__file__), 'templates', 'stats.html')
		self.response.write(template.render(path, template_values))

	def handle_words(self, chart, team, teamkeyname, year_central, month_central, word):
		firefox_win, ie_win, team_owner_name, settingsdict = get_initial_values(self)
		teams, years, months, days = get_dropdown_values()

		showpostbyuserchart = False
		showwordtable = False
		showteamsummary = False
		chartresolution = "month"
		showpostchart = False
		showwordchart = False
		showtotal = False
		teamtotals = None
		showwordbyuserchart = False
		teamrows = 0
		charttitle = ""
		total_message = ""
		tabletitle = ""
		team_results = None
		rows = 0
		if word != "":
			team_queries = None
			showwordchart = True
			charttitle = "\\'" + word + "\\' Usage" # as Pct of All Words
			if chart == "by_user":
				charttitle += " By User"

			if team:
				charttitle += " for " + team.ownername
				basequery = dygmodel.TeamChatWordStats.all().filter("word = ", word).filter("team = ", team)
				q = dygmodel.TeamChatWordStats.all().filter("word = ", word).filter("team = ", team)
			else:
				showteamsummary = True
				basequery = dygmodel.ChatWordStats.all().filter("word = ", word)
				if chart == "by_user":
					showwordbyuserchart = True
					showwordchart = False
					team_queries = []
					for t in dygmodel.Team.all().fetch(1000):
						team_queries.append([t,dygmodel.TeamChatWordStats.all().filter("word = ", word).filter("team = ", t)])
				else:
					q = dygmodel.ChatWordStats.all().filter("word = ", word)

			showtotal = True

			if year_central > 0:
				if team_queries:
					for q in team_queries:
						q[1].filter("year_central = ", year_central)
				else:
					q.filter("year_central = ", year_central)
				if month_central > 0:
					charttitle += " by Day - " + months[month_central - 1] + " " + str(year_central)
					if team_queries:
						for q in team_queries:
							q[1].filter("month_central = ", month_central)
							q[1].filter("timespanvalue = ", dygmodel.StatsTimeSpan.DAY_SPAN)
					else:
						q.filter("month_central = ", month_central)
						q.filter("timespanvalue = ", dygmodel.StatsTimeSpan.DAY_SPAN)
					tot_obj = basequery.filter("timespanvalue = ", dygmodel.StatsTimeSpan.MONTH_SPAN).filter("year_central = ", year_central).filter("month_central = ", month_central).get()
					tot = 0
					if tot_obj: tot = tot_obj.usagecount
					total_message = "Total Usage for Month: " + str(dygutil.format_number(tot))
					if not team: teamtotals = dygmodel.TeamChatWordStats.all().filter("word = ", word).filter("timespanvalue = ", dygmodel.StatsTimeSpan.MONTH_SPAN).filter("year_central = ", year_central).filter("month_central = ", month_central).order("-usagecount").fetch(1000)
				else:
					charttitle += " by Month - " + str(year_central)
					if team_queries:
						for q in team_queries:
							q[1].filter("timespanvalue = ", dygmodel.StatsTimeSpan.MONTH_SPAN)
					else:
						q.filter("timespanvalue = ", dygmodel.StatsTimeSpan.MONTH_SPAN)
					tot_obj = basequery.filter("timespanvalue = ", dygmodel.StatsTimeSpan.YEAR_SPAN).filter("year_central = ", year_central).get()
					tot = 0
					if tot_obj: tot = tot_obj.usagecount
					total_message = "Total Posts for Year: " + str(dygutil.format_number(tot))
					if not team: teamtotals = dygmodel.TeamChatWordStats.all().filter("word = ", word).filter("timespanvalue = ", dygmodel.StatsTimeSpan.YEAR_SPAN).filter("year_central = ", year_central).order("-usagecount").fetch(1000)
			else:
				charttitle += " by Month"
				if team_queries:
					for q in team_queries:
						q[1].filter("timespanvalue = ", dygmodel.StatsTimeSpan.MONTH_SPAN)
				else:
					q.filter("timespanvalue = ", dygmodel.StatsTimeSpan.MONTH_SPAN)
				tot = basequery.filter("timespanvalue = ", dygmodel.StatsTimeSpan.ALL_TIME_SPAN).get().usagecount
				total_message = "Total Usage All-Time: " + str(dygutil.format_number(tot))
				if not team: teamtotals = dygmodel.TeamChatWordStats.all().filter("word = ", word).filter("timespanvalue = ", dygmodel.StatsTimeSpan.ALL_TIME_SPAN).order("-usagecount").fetch(1000)

			if team_queries:
				for q in team_queries:
					q[1].order("statsdate_central")
					q.append(q[1].fetch(1000))
			else:
				q.order("statsdate_central")
				pre_statsrecords = q.fetch(1000)


			def fill_in(pre_statsrecords, start_datetime=None, end_datetime=None):
				statsrecords = []

				if pre_statsrecords and len(pre_statsrecords) > 0:
					if year_central > 0 and month_central > 0:
						resolution = datetime.timedelta(days=1)
					else:
						resolution = datetime.timedelta(days=31)
					if start_datetime:
						if resolution.days == 31:
							last_datetime = dygutil.add_months_to_datetime(start_datetime,-1)
						else:
							last_datetime = start_datetime - resolution
					else:
						last_datetime = datetime.datetime(pre_statsrecords[0].year_central,pre_statsrecords[0].month_central,pre_statsrecords[0].day_central)
					for record in pre_statsrecords:
						this_datetime = datetime.datetime(record.year_central,record.month_central,record.day_central)
						while this_datetime - last_datetime > resolution:
							if resolution == datetime.timedelta(days=31):
								delta = dygutil.add_months_to_datetime(last_datetime) - last_datetime
							else:
								delta = resolution
							new_datetime = last_datetime + delta
							newrecord = dygmodel.StatsTimeSpan(
								timespanvalue=record.timespanvalue,
								year_central=new_datetime.year,
								month_central=new_datetime.month,
								day_central=new_datetime.day,
								hour_central=new_datetime.hour)
							statsrecords.append(newrecord)
							last_datetime = datetime.datetime(newrecord.year_central,newrecord.month_central,newrecord.day_central)
						statsrecords.append(record)
						last_datetime = this_datetime
					if end_datetime:
						if resolution.days == 31:
							resolution2 = datetime.timedelta(days=28)
						else:
							resolution2 = resolution

						this_datetime = datetime.datetime(pre_statsrecords[-1].year_central,pre_statsrecords[-1].month_central,pre_statsrecords[-1].day_central)
						while end_datetime - this_datetime >= resolution2:
							if resolution2.days == 28:
								delta = dygutil.add_months_to_datetime(this_datetime) - this_datetime
							else:
								delta = resolution2
							new_datetime = this_datetime + delta
							#logging.info("delta=" + str(delta))
							newrecord = dygmodel.StatsTimeSpan(
								timespanvalue=pre_statsrecords[-1].timespanvalue,
								year_central=new_datetime.year,
								month_central=new_datetime.month,
								day_central=new_datetime.day,
								hour_central=new_datetime.hour)
							statsrecords.append(newrecord)
							this_datetime = datetime.datetime(newrecord.year_central,newrecord.month_central,newrecord.day_central)
				return statsrecords


			statsrecords = []
			team_results = []
			if team_queries:
				start_datetime = None
				end_datetime = None
				for q in team_queries:
					if len(q[2]):
						dt = datetime.datetime(q[2][0].year_central,q[2][0].month_central,q[2][0].day_central,q[2][0].hour_central)
						if not start_datetime or dt < start_datetime: start_datetime = dt

						dt = datetime.datetime(q[2][-1].year_central,q[2][-1].month_central,q[2][-1].day_central,q[2][-1].hour_central)
						if not end_datetime or dt > end_datetime: end_datetime = dt

				for q in team_queries:
					q.append(fill_in(q[2],start_datetime,end_datetime))
					if len(q[3]) > 0:
						rows = len(q[3])
						team_results.append(q)
			else:
				statsrecords = fill_in(pre_statsrecords)
				rows = len(statsrecords)

			if teamtotals: teamrows = len(teamtotals)
		else:
			showwordtable = True
			tabletitle = "Word Usage Counts"
			if team:
				tabletitle += " for " + team.ownername
				q = dygmodel.TeamChatWordStats.all().filter("team = ", team).filter("hiddenword = ", False)
			else:
				q = dygmodel.ChatWordStats.all().filter("hiddenword = ", False)

			if year_central > 0:
				q.filter("year_central = ", year_central)
				if month_central > 0:
					tabletitle += " - " + months[month_central - 1] + " " + str(year_central)
					q.filter("month_central = ", month_central)
					q.filter("timespanvalue = ", dygmodel.StatsTimeSpan.MONTH_SPAN)
				else:
					tabletitle += " - " + str(year_central)
					q.filter("timespanvalue = ", dygmodel.StatsTimeSpan.YEAR_SPAN)
			else:
				q.filter("timespanvalue = ", dygmodel.StatsTimeSpan.ALL_TIME_SPAN)

			q.order("-usagecount")
			statsrecords = q.fetch(100)
			rows = len(statsrecords)

		template_values = {
			'team_owner_name': team_owner_name,
			'theme': settingsdict["theme"],
			'teams': teams,
			'years': years,
			'months': months,
			'year': year_central,
			'month': month_central,
			'team': teamkeyname,
			'statsrecords': statsrecords,
			'team_results': team_results,
			'rows': rows,
			'section': "words",
			'tabletitle': tabletitle,
			'chart': chart,
			'showselectorbar': True,
			'showpostchart': showpostchart,
			'showwordbyuserchart': showwordbyuserchart,
			'showwordtable': showwordtable,
			'showteamsummary': showteamsummary,
			'showtotal': showtotal,
			'word': word,
			'showwordchart': showwordchart,
			'charttitle': charttitle,
			'total_message': total_message,
			'teamtotals': teamtotals,
			'teamrows': teamrows,
			'showteamdropdown': True,
			'firefox_win': firefox_win,
			'ie_win': ie_win,
		}
		path = os.path.join(os.path.dirname(__file__), 'templates', 'stats.html')
		self.response.write(template.render(path, template_values))

	def handle_records(self):
		firefox_win, ie_win, team_owner_name, settingsdict = get_initial_values(self)

		topsiteyears = dygmodel.StatsTimeSpan.all().filter("timespanvalue = ", dygmodel.StatsTimeSpan.YEAR_SPAN).order("-postcount").fetch(2)
		topsitemonths = dygmodel.StatsTimeSpan.all().filter("timespanvalue = ", dygmodel.StatsTimeSpan.MONTH_SPAN).order("-postcount").fetch(2)
		topsitedays = dygmodel.StatsTimeSpan.all().filter("timespanvalue = ", dygmodel.StatsTimeSpan.DAY_SPAN).order("-postcount").fetch(2)
		topsitehours = dygmodel.StatsTimeSpan.all().filter("timespanvalue = ", dygmodel.StatsTimeSpan.HOUR_SPAN).order("-postcount").fetch(2)

		topteamalltime = dygmodel.TeamChatMessageStats.all().filter("timespanvalue = ", dygmodel.StatsTimeSpan.ALL_TIME_SPAN).order("-postcount").fetch(2)
		topteamyears = dygmodel.TeamChatMessageStats.all().filter("timespanvalue = ", dygmodel.StatsTimeSpan.YEAR_SPAN).order("-postcount").fetch(2)
		topteammonths = dygmodel.TeamChatMessageStats.all().filter("timespanvalue = ", dygmodel.StatsTimeSpan.MONTH_SPAN).order("-postcount").fetch(2)
		topteamdays = dygmodel.TeamChatMessageStats.all().filter("timespanvalue = ", dygmodel.StatsTimeSpan.DAY_SPAN).order("-postcount").fetch(2)
		topteamhours = dygmodel.TeamChatMessageStats.all().filter("timespanvalue = ", dygmodel.StatsTimeSpan.HOUR_SPAN).order("-postcount").fetch(2)

		siterows = [topsiteyears,topsitemonths,topsitedays,topsitehours]
		teamrows = [topteamalltime,topteamyears,topteammonths,topteamdays,topteamhours]

		template_values = {
			'team_owner_name': team_owner_name,
			'theme': settingsdict["theme"],
			'siterows': siterows,
			'teamrows': teamrows,
			'section': "records",
			'showselectorbar': False,
			'showrecordstable': True,
			'firefox_win': firefox_win,
			'ie_win': ie_win,
		}

		path = os.path.join(os.path.dirname(__file__), 'templates', 'stats.html')
		self.response.write(template.render(path, template_values))

	def handle_settings_elements(self, chart, team, teamkeyname, year_central, month_central, section):
		firefox_win, ie_win, team_owner_name, settingsdict = get_initial_values(self)
		teams, years, months, days = get_dropdown_values()

		showpostbyuserchart = False
		showwordtable = False
		showteamsummary = False
		chartresolution = "month"
		showpostchart = False
		showwordchart = False
		showtotal = False
		teamtotals = None
		showwordbyuserchart = False

		tabletitle = ""
		if section == "videos":
			tabletitle = "Video Lifetime and Popularity"
			q = dygmodel.SettingsElementStats.all().filter("element_kind = ", dygmodel.SettingsElementStats.VIDEO_KIND)
		elif section == "photos":
			tabletitle = "Photo Lifetime and Popularity"
			q = dygmodel.SettingsElementStats.all().filter("element_kind = ", dygmodel.SettingsElementStats.PHOTO_KIND)
		elif section == "captions":
			tabletitle = "Caption Lifetime and Popularity"
			q = dygmodel.SettingsElementStats.all().filter("element_kind = ", dygmodel.SettingsElementStats.CAPTION_KIND)
		elif section == "titles":
			tabletitle = "Title Lifetime and Popularity"
			q = dygmodel.SettingsElementStats.all().filter("element_kind = ", dygmodel.SettingsElementStats.PAGE_TITLE_KIND)
		elif section == "themes":
			tabletitle = "Theme Lifetime and Popularity"
			q = dygmodel.SettingsElementStats.all().filter("element_kind = ", dygmodel.SettingsElementStats.THEME_KIND)

		if year_central > 0:
			q.filter("year_central = ", year_central)
			if month_central > 0:
				tabletitle += " - " + months[month_central - 1] + " " + str(year_central)
				q.filter("month_central = ", month_central)
				q.filter("timespanvalue = ", dygmodel.StatsTimeSpan.MONTH_SPAN)
			else:
				tabletitle += " - " + str(year_central)
				q.filter("timespanvalue = ", dygmodel.StatsTimeSpan.YEAR_SPAN)
		else:
			q.filter("timespanvalue = ", dygmodel.StatsTimeSpan.ALL_TIME_SPAN)

		q.order("-uniqueteamspostingcount")
		statsrecords = q.fetch(50)
		for record in statsrecords:
			record.element.set_myrating(dygutil.getteamid(self))

		template_values = {
			'team_owner_name': team_owner_name,
			'theme': settingsdict["theme"],
			'years': years,
			'months': months,
			'year': year_central,
			'month': month_central,
			'statsrecords': statsrecords,
			'rows': len(statsrecords),
			'section': section,
			'tabletitle': tabletitle,
			'showselectorbar': True,
			'showsettingselementtable': True,
			'showteamdropdown': False,
			'firefox_win': firefox_win,
			'ie_win': ie_win,
		}
		path = os.path.join(os.path.dirname(__file__), 'templates', 'stats.html')
		self.response.write(template.render(path, template_values))

def get_dropdown_values():
	teams = db.GqlQuery("SELECT * FROM Team WHERE is_interactive=TRUE " +
					"ORDER BY ownername")
	years = db.GqlQuery("SELECT * FROM StatsTimeSpan " +
					"WHERE timespanvalue=:1 " +
					"ORDER BY year_central", dygmodel.StatsTimeSpan.YEAR_SPAN)
	return teams, years, months, days

def get_initial_values(handler):
	browserinfo = dygutil.get_browser_info(handler.request)
	firefox_win = (browserinfo['browser'] == "firefox" and browserinfo["os"] == "windows")
	ie_win = (browserinfo['browser'] == "ie" and browserinfo["os"] == "windows")

	team_owner_name = dygchatdata.fetch_team_ownername(dygutil.getteamid(handler,enforce=True))

	latestsettings = dygsettingsdata.get_latest_settings()
	if latestsettings:
		settingsdict = latestsettings.to_dict()
	else:
		settingsdict = {
			'pagetitle': "",
			'prompt': "",
			'url1': "",
			'url2': "",
			'url3': "",
			'caption1': "",
			'caption2': "",
			'caption3': "",
			'theme': "basic.css",
		}

	return firefox_win, ie_win, team_owner_name, settingsdict

app = webapp2.WSGIApplication([
	(r'/dashboard/stats/(.*)', StatsHandler), \
	('/dashboard/stats', StatsHandler), \
	('/dashboard/photos', PhotoArchiveHandler), \
	('/dashboard/chat', ChatArchiveHandler), \
	('/dashboard/generator', ChatPostGeneratorHandler), \
	('/dashboard/prefs', PrefsHandler), \
	('/dashboard/admin', AdminHandler), \
	('/dashboard', AdminHandler)], \
									  debug=False)
