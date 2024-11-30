#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#	 http://www.apache.org/licenses/LICENSE-2.0
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
import re
from BeautifulSoup import BeautifulSoup, BeautifulStoneSoup

import dygutil
import dygmodel
import dygfantasystatsmodel
import dygsettingsdata
import dygchatdata

from google.appengine.api import modules
from google.appengine.ext import webapp
from google.appengine.ext import db,search
from google.appengine.api import memcache

from google.appengine.api import taskqueue

logdebug = True

def add_task(t, task_name):
	try:
		t.add(queue_name = 'cbs-data')
	except taskqueue.TombstonedTaskError:
		logging.info("Attempted to add duplicate task %s (tombstoned)" % task_name)
	except taskqueue.TaskAlreadyExistsError:
		logging.info("Attempted to add duplicate task %s" % task_name)

def get_cookie():
	return dygutil.http_login('https://www.cbssports.com/login', 'xurl=http://dyg.baseball.cbssports.com/&userid=roomloo&password=4fbqEKks4S3N')

# Set this once the below season entity is created and we're ready to start pick 'em etc. Usually a few days before season start.
# To load quickly: http://www.dyinggiraffe.com/fantasystatsload/schedule?endtoend=true&backend=true
# TODO -- schedule doesn't appear to be loading properly in 2017 ^^

def manual_latest_season():
	return 2024

class StatsHandler(webapp.RequestHandler):
	def get(self, section="mlbteams"):
		batch_cycle_id = self.request.get("batch_cycle",default_value=datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S"))
		endtoend = (self.request.get("endtoend",default_value="false").lower() == "true")
		run_on_backend = (self.request.get("backend",default_value="false").lower() == "true")
		inseason = (self.request.get("inseason",default_value="false").lower() == "true")
		this_module = modules.get_current_module_name()
		processed_count = int(self.request.get("processed",default_value="0"))

		# Set to True during offseason to force-load missing stats from latest season
		override_final_stats = False

		import logging
		logging.debug("section=%s" % section)

		if run_on_backend and this_module == "default":
			task_name = "fantasystatsload-%s-%s" % (section.replace("_", "-"), batch_cycle_id)
			t = taskqueue.Task(url='/fantasystatsload/' + section, params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason)}, target="batch", name=task_name, method='GET')
			add_task(t, task_name)
			return

		season_2024 = dygfantasystatsmodel.FantasySeason.all().filter("year = ", 2024).get()
		if not season_2024:
			season_2024 = dygfantasystatsmodel.FantasySeason.get_or_insert_by_values(2024)
			season_2024.startdate = datetime.datetime(2024, 3, 20)
			season_2024.enddate = datetime.datetime(2024, 9, 29)
			season_2024.put()

		seasons = dygfantasystatsmodel.FantasySeason.all().order("-enddate").fetch(100)
		for s in seasons:
			if datetime.datetime.now().date() > s.startdate.date() or s.startdate.year == manual_latest_season():
				if datetime.datetime.now().date() <= s.enddate.date() + datetime.timedelta(days=1): inseason = True
				break
		if not inseason: inseason = (self.request.get("inseason",default_value="false").lower() == "true")

		if section == "mlbteams":
			if inseason: self.handle_mlb_teams()
			if endtoend:
				task_name = "fantasystatsload-%s-%s" % ("setupfantasyteams", batch_cycle_id)
				t = taskqueue.Task(url='/fantasystatsload/setupfantasyteams', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason)}, target=this_module, name=task_name, method='GET')
				add_task(t, task_name)
		elif section == "setupfantasyteams":
			if inseason:
				year_str = self.request.get("year",default_value=str(self.get_current_year()))
				year = int(year_str)
				self.handle_setupfantasyteams(year)
			#dygfantasystatsmodel.FantasyTeam(teamname = "Wisconsin Cheese Bats", cbsteamid=1, franchiseteamid=4).put()
			if endtoend:
				task_name = "fantasystatsload-%s-%s" % ("rosters", batch_cycle_id)
				t = taskqueue.Task(url='/fantasystatsload/rosters', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason)}, target=this_module, name=task_name, method='GET')
				add_task(t, task_name)
		elif section == "rosters":
			MAX_TEAMS = 20
			teamnumber = int(self.request.get("team",default_value="1"))
			self.handle_rosters(batch_cycle_id, teamnumber, inseason)
			nextteamnumber = teamnumber + 1
			if nextteamnumber <= MAX_TEAMS:
				task_name = "fantasystatsload-%s-%s-%s" % ("rosters", batch_cycle_id, nextteamnumber)
				t = taskqueue.Task(url='/fantasystatsload/rosters', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason), 'team': nextteamnumber}, target=this_module, name=task_name, method='GET')
				add_task(t, task_name)
			elif endtoend:
				task_name = "fantasystatsload-%s-%s" % ("stats", batch_cycle_id)
				t = taskqueue.Task(url='/fantasystatsload/stats', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason)}, target=this_module, name=task_name, method='GET')
				add_task(t, task_name)
		elif section == "stats":
			if inseason:
				position = self.request.get("pos",default_value="SP")
				self.handle_stats(batch_cycle_id, position, inseason, override_final_stats)
				if position == "SP":
					nextposition = "RP"
				elif position == "RP":
					nextposition = "C"
				elif position == "C":
					nextposition = "1B"
				elif position == "1B":
					nextposition = "2B"
				elif position == "2B":
					nextposition = "3B"
				elif position == "3B":
					nextposition = "SS"
				elif position == "SS":
					nextposition = "OF"
				elif position == "OF":
					nextposition = "DH"
				elif position == "DH":
					nextposition = ""
				if nextposition != "":
					task_name = "fantasystatsload-%s-%s-%s" % ("stats", batch_cycle_id, nextposition)
					t = taskqueue.Task(url='/fantasystatsload/stats', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason), 'pos': nextposition}, target=this_module, name=task_name, method='GET')
					add_task(t, task_name)
				elif endtoend:
					task_name = "fantasystatsload-%s-%s" % ("players", batch_cycle_id)
					t = taskqueue.Task(url='/fantasystatsload/players', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason)}, target=this_module, name=task_name, method='GET')
					add_task(t, task_name)
			elif endtoend:
				task_name = "fantasystatsload-%s-%s" % ("players", batch_cycle_id)
				t = taskqueue.Task(url='/fantasystatsload/players', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason)}, target=this_module, name=task_name, method='GET')
				add_task(t, task_name)
		elif section == "players":
			if inseason:
				last_key = self.request.get("last_key")
				year = self.get_current_year()

				if last_key:
					q = db.GqlQuery("SELECT * FROM FantasyPlayer WHERE most_recent_season_year = :1 AND __key__ > :2 ORDER BY __key__", year, db.Key(last_key))
				else:
					q = db.GqlQuery("SELECT * FROM FantasyPlayer WHERE most_recent_season_year = :1 ORDER BY __key__", year)
				players = q.fetch(1)

				if players and len(players) > 0:
					processed_count += 1
					self.handle_player_details(batch_cycle_id, players[0], override_final_stats)
					last_key = str(players[-1].key())

					task_name = "fantasystatsload-%s-%s-%s" % ("players", batch_cycle_id, last_key.replace("_", "-"))
					t = taskqueue.Task(url='/fantasystatsload/players', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason), 'last_key': last_key, 'processed': processed_count}, target=this_module, name=task_name, method='GET')
					add_task(t, task_name)
				elif endtoend:
					task_name = "fantasystatsload-%s-%s" % ("capvalues", batch_cycle_id)
					t = taskqueue.Task(url='/fantasystatsload/capvalues', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason)}, target=this_module, name=task_name, method='GET')
					add_task(t, task_name)
			elif endtoend:
				task_name = "fantasystatsload-%s-%s" % ("capvalues", batch_cycle_id)
				t = taskqueue.Task(url='/fantasystatsload/capvalues', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason)}, target=this_module, name=task_name, method='GET')
				add_task(t, task_name)
		elif section == "capvalues":
			if inseason:
				self.handle_salary()
			if endtoend:
				task_name = "fantasystatsload-%s-%s" % ("schedule", batch_cycle_id)
				t = taskqueue.Task(url='/fantasystatsload/schedule', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason)}, target=this_module, name=task_name, method='GET')
				add_task(t, task_name)
		elif section == "schedule":
			if inseason:
				year_str = self.request.get("year",default_value=str(self.get_current_year()))
				self.handle_schedule(int(year_str))
			if endtoend:
				task_name = "fantasystatsload-%s-%s" % ("teamsbyweek", batch_cycle_id)
				t = taskqueue.Task(url='/fantasystatsload/teamsbyweek', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason)}, target=this_module, name=task_name, method='GET')
				add_task(t, task_name)
		elif section == "teamsbyweek":
			if inseason:
				currentyear = self.get_current_year()
				year_str = self.request.get("year",default_value=str(currentyear))
				week_str = self.request.get("week",default_value="0")
				year = int(year_str)
				week = int(week_str)

				if year == 0:
					year = currentyear

				# determine current week number for year
				latestweek = self.get_current_week()

				if week == 0:
					if year == currentyear:
						week = latestweek
					else:
						week = 1

				self.handle_teamsbyweek(year, week)
				if week < latestweek:
					task_name = "fantasystatsload-%s-%s-%s-%s" % ("teamsbyweek", batch_cycle_id, year, week + 1)
					t = taskqueue.Task(url='/fantasystatsload/teamsbyweek', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason), 'year': year, 'week': week + 1}, target=this_module, name=task_name, method='GET')
					add_task(t, task_name)
				elif endtoend:
					pass
					'''
					task_name = "fantasystatsload-%s-%s" % ("lineups", batch_cycle_id)
					t = taskqueue.Task(url='/fantasystatsload/lineups', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason)}, target=this_module, name=task_name, method='GET')
					add_task(t, task_name)
					'''
			elif endtoend:
				pass
				'''
				task_name = "fantasystatsload-%s-%s" % ("lineups", batch_cycle_id)
				t = taskqueue.Task(url='/fantasystatsload/lineups', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason)}, target=this_module, name=task_name, method='GET')
				add_task(t, task_name)
				'''
		elif section == "lineups":
			if inseason:
				week_str = self.request.get("week",default_value="0")
				week = int(week_str)
				year = self.get_current_year()

				# determine current week number for year
				latestweek = self.get_current_week()

				if week == 0:
					week = latestweek

				MAX_TEAMS = 20
				teamnumber = int(self.request.get("team",default_value="1"))

				self.handle_lineups(week, teamnumber)
				if teamnumber < MAX_TEAMS:
					task_name = "fantasystatsload-%s-%s-%s-%s" % ("lineups", batch_cycle_id, week, teamnumber + 1)
					t = taskqueue.Task(url='/fantasystatsload/lineups', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason), 'week': week, 'team':  teamnumber + 1}, target=this_module, name=task_name, method='GET')
					add_task(t, task_name)
				elif week < latestweek:
					task_name = "fantasystatsload-%s-%s-%s" % ("lineups", batch_cycle_id, week + 1)
					t = taskqueue.Task(url='/fantasystatsload/lineups', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason), 'week': week + 1}, target=this_module, name=task_name, method='GET')
					add_task(t, task_name)
				elif endtoend:
					task_name = "fantasystatsload-%s-%s" % ("weeklyteamstats", batch_cycle_id)
					t = taskqueue.Task(url='/fantasystatsload/weeklyteamstats', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason)}, target=this_module, name=task_name, method='GET')
					add_task(t, task_name)
			elif endtoend:
				pass
		elif section == "weeklyteamstats":
			if inseason:
				week_str = self.request.get("week",default_value="0")
				week = int(week_str)
				year = self.get_current_year()

				# determine current week number for year
				latestweek = self.get_current_week()

				if week == 0:
					week = latestweek

				MAX_TEAMS = 20
				teamnumber = int(self.request.get("team",default_value="1"))
				totals = (self.request.get("totals",default_value="False") == "True")

				self.handle_weeklyteamstats(week, teamnumber, totals)
				if teamnumber < MAX_TEAMS:
					task_name = "fantasystatsload-%s-%s-%s-%s-%s" % ("weeklyteamstats", batch_cycle_id, week, teamnumber + 1, False)
					t = taskqueue.Task(url='/fantasystatsload/weeklyteamstats', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason), 'week': week, 'team':  teamnumber + 1, 'totals': False}, target=this_module, name=task_name, method='GET')
					add_task(t, task_name)
				elif not totals:
					task_name = "fantasystatsload-%s-%s-%s-%s-%s" % ("weeklyteamstats", batch_cycle_id, week, teamnumber, True)
					t = taskqueue.Task(url='/fantasystatsload/weeklyteamstats', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason), 'week': week, 'team':  teamnumber, 'totals': True}, target=this_module, name=task_name, method='GET')
					add_task(t, task_name)
				elif week < latestweek:
					task_name = "fantasystatsload-%s-%s-%s-%s" % ("weeklyteamstats", batch_cycle_id, week + 1, False)
					t = taskqueue.Task(url='/fantasystatsload/weeklyteamstats', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason), 'week': week + 1, 'totals': False}, target=this_module, name=task_name, method='GET')
					add_task(t, task_name)
				elif endtoend:
					task_name = "fantasystatsload-%s-%s" % ("breakdown", batch_cycle_id)
					t = taskqueue.Task(url='/fantasystatsload/breakdown', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason)}, target=this_module, name=task_name, method='GET')
					add_task(t, task_name)
			elif endtoend:
				pass
		elif section == "breakdown":
			if inseason:
				currentyear = self.get_current_year()
				year_str = self.request.get("year",default_value=str(currentyear))
				teamnumber = int(self.request.get("team",default_value="1"))
				week_str = self.request.get("week",default_value="0")
				year = int(year_str)
				week = int(week_str)

				# determine current week number for year
				latestweek = self.get_current_week()

				if week == 0:
					if year == currentyear:
						week = latestweek
					else:
						week = 1

				if year == 0:
					year = currentyear
				self.handle_breakdown(year, week)
				if week < latestweek:
					task_name = "fantasystatsload-%s-%s-%s-%s" % ("teamtotals", batch_cycle_id, year, week + 1)
					t = taskqueue.Task(url='/fantasystatsload/breakdown', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason), 'year': year, 'week': week + 1}, target=this_module, name=task_name, method='GET')
					add_task(t, task_name)
				elif endtoend:
					task_name = "fantasystatsload-%s-%s" % ("teamtotals", batch_cycle_id)
					t = taskqueue.Task(url='/fantasystatsload/teamtotals', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason)}, target=this_module, name=task_name, method='GET')
					add_task(t, task_name)
			elif endtoend:
				pass
		elif section == "teamtotals":
			if inseason:
				MAX_TEAMS = 20
				currentyear = self.get_current_year()
				year_str = self.request.get("year",default_value=str(currentyear))
				teamnumber = int(self.request.get("team",default_value="1"))
				year = int(year_str)

				if year == 0:
					year = currentyear

				self.handle_teamtotals(teamnumber, year)
				nextteamnumber = teamnumber + 1
				if nextteamnumber <= MAX_TEAMS:
					task_name = "fantasystatsload-%s-%s-%s-%s" % ("teamtotals", batch_cycle_id, year, nextteamnumber)
					t = taskqueue.Task(url='/fantasystatsload/teamtotals', params={'batch_cycle': batch_cycle_id, 'endtoend': str(endtoend), 'inseason': str(inseason), 'year': year, 'team': nextteamnumber}, target=this_module, name=task_name, method='GET')
					add_task(t, task_name)
				elif endtoend:
					pass
			elif endtoend:
				pass
		elif section == "createteams":
			pass
			# import dygmodel
			#t = dygmodel.Team.get_or_insert("t_16", teamid=16, teamname="Clark W. Griswalds", ownername="Chris Clark", postindex=0)
			#t = dygmodel.Team.get_or_insert("t_17", teamid=17, teamname="Birds", ownername="Pat Pruneau", postindex=0)
			#t = dygmodel.Team.get_or_insert("t_18", teamid=18, teamname="Aquarius Burley's Original House of Mirrors", ownername="Mike Fertig", postindex=0)
			#t = dygmodel.Team.get_or_insert("t_19", teamid=19, teamname="Ryno's Pimp Juice", ownername="Ryan Kasten", postindex=0)
			#t = dygmodel.Team.get_or_insert("t_20", teamid=20, teamname="Jimb's Piss Clams", ownername="Jim Ermitage", postindex=0)
			#t = dygmodel.Team.get_or_insert("t_28", teamid=28, teamname="The Mad Hungarian", ownername="Craig McMurtrey", postindex=0)
			#t = dygmodel.Team.get_or_insert("t_29", teamid=29, teamname="JT's Nipplegaters", ownername="Jason Ziegler", postindex=0)

	def get_current_year(self):
		latestyear = datetime.datetime.now().year
		seasons = dygfantasystatsmodel.FantasySeason.all().order("-enddate").fetch(100)
		for s in seasons:
			if datetime.datetime.now().date() > s.startdate.date() or s.startdate.year == manual_latest_season():
				latestyear = s.year
				break
		return latestyear

	def get_current_week(self):
		latestweek = 0
		weeks = dygfantasystatsmodel.FantasyWeek.all().filter("year = ", self.get_current_year()).order("-enddate").fetch(30)
		for w in weeks:
			if datetime.datetime.now().date() > w.enddate.date():
				latestweek = w.weeknumber
				break
		return latestweek

	def getdbteam(self, teamnumber, year):
		thisteamnumber = 0
		for t in dygfantasystatsmodel.FantasyTeam.all().filter("year = ", year).fetch(1000):
			thisteamnumber += 1
			if thisteamnumber == teamnumber:
				return t
		return None

	def handle_rosters(self, batch_cycle_id, teamnumber=1, inseason=False, override_final_stats=False):
		year = self.get_current_year()
		cookie = get_cookie()
		logging.info("cookie=%s" % cookie)

		teams = []

		t = self.getdbteam(teamnumber, year)
		if t == None: return
		if t.cbsteamid == 0: return

		teaminfo = {}

		teaminfo['dbteam'] = t
		teaminfo['cbsteamid'] = t.cbsteamid

		if inseason:
			url = 'http://dyg.baseball.cbssports.com/stats/stats-main/team:' + str(t.cbsteamid) + '/ytd:p/scoring'
		else:
			url = 'http://dyg.baseball.cbssports.com/stats/stats-main/team:' + str(t.cbsteamid) + '/' + str(year) + ':p/scoring'
		page = dygutil.get_page(cookie, url)
		page = re.sub("aria-label='.*?' href=", "href=", page)
		soup = BeautifulSoup(page, convertEntities=BeautifulSoup.HTML_ENTITIES)
		logging.info(url)
		#logging.info(page[50000:])

		stats_tables = soup.find("div", {'id': "sortableStats"}).findAll("table")
		hitters_soup = stats_tables[0]
		pitchers_soup = stats_tables[1]

		header_text = hitters_soup.find("tr").find("td").text
		logging.info("hitters_soup=%s" % hitters_soup)
		logging.info("header_text=%s" % header_text)
		# 2014 Season MLB Scoring Stats
		# Year to Date MLB Scoring Stats
		# Batters: 1984 Players  Season MLB Scoring Categories
		header_text = header_text.replace("  ", " ")
		teamname = header_text[:-43].strip()
		# if inseason:
		# 	teamname = header_text[:-43].strip()
		# else:
		# 	teamname = header_text[:-38].strip()
		if teamname.startswith("Batters:"): teamname = teamname[8:].strip()
		logging.info("teamname=%s" % teamname)
		teaminfo['teamname'] = teamname

		teaminfo['hitters'] = self.parse_player_stats(hitters_soup)
		teaminfo['pitchers'] = self.parse_player_stats(pitchers_soup)

		teams.append(teaminfo)

		season = dygfantasystatsmodel.FantasySeason.get_or_insert_by_values(year)

		entitylist = []
		for fantasyteam in teams:
			dbteam = fantasyteam['dbteam']
			dbteam.teamname = fantasyteam['teamname'].strip()
			dbteam.put()
			dbfranchise = dbteam.franchise
			dbfranchise.teamname = fantasyteam['teamname']
			dbfranchise.put()

			# briefly reset team memberships, for players that have been dropped since last run
			players = dygfantasystatsmodel.FantasyPlayer.all().filter("fantasyteam = ", dbteam).fetch(100)
			players_map = {}
			for i in range(0, len(players)):
				players[i].fantasyteam = None
				players_map[players[i].key().name()] = {'prev_team': dbteam.key(), 'new_team': None}
			db.put(players)

			for pitcher in fantasyteam['pitchers']:
				assert pitcher['mlbteamcode'] is not None and pitcher['mlbteamcode'].strip() != ""
				dbplayer = dygfantasystatsmodel.FantasyPlayer.get_or_insert_by_values(
						pitcher['cbsplayerid'])
				if dbplayer.key().name() not in players_map:
					players_map[dbplayer.key().name()] = {'prev_team': dbplayer.fantasyteam.key() if dbplayer.fantasyteam else None}
				dbplayer.fantasyteam = dbteam
				dbplayer.firstname = pitcher['firstname']
				dbplayer.lastname = pitcher['lastname']
				dbplayer.primaryposition = pitcher['primaryposition']
				dbplayer.mlbteamcode = pitcher['mlbteamcode']
				dbplayer.most_recent_season = season
				dbplayer.set_calculated_fields()
				entitylist.append(dbplayer)
				players_map[dbplayer.key().name()]['new_team'] = dbteam.key()
				if inseason:
					dbplayerseason = dygfantasystatsmodel.FantasyPlayerSeason.get_or_insert_by_values(dbplayer, season)
					if not dbplayerseason.is_final or override_final_stats:
						self.set_pitcher_stats(dbplayerseason, pitcher)
						entitylist.append(dbplayerseason)

			for hitter in fantasyteam['hitters']:
				assert hitter['mlbteamcode'] is not None and hitter['mlbteamcode'].strip() != ""
				dbplayer = dygfantasystatsmodel.FantasyPlayer.get_or_insert_by_values(
						hitter['cbsplayerid'])
				if dbplayer.key().name() not in players_map:
					players_map[dbplayer.key().name()] = {'prev_team': dbplayer.fantasyteam.key() if dbplayer.fantasyteam else None}
				dbplayer.fantasyteam = dbteam
				dbplayer.firstname = hitter['firstname']
				dbplayer.lastname = hitter['lastname']
				dbplayer.primaryposition = hitter['primaryposition']
				dbplayer.mlbteamcode = hitter['mlbteamcode']
				dbplayer.most_recent_season = season
				dbplayer.set_calculated_fields()
				entitylist.append(dbplayer)
				players_map[dbplayer.key().name()]['new_team'] = dbteam.key()
				if inseason:
					dbplayerseason = dygfantasystatsmodel.FantasyPlayerSeason.get_or_insert_by_values(dbplayer, season)
					if not dbplayerseason.is_final or override_final_stats:
						self.set_hitter_stats(dbplayerseason, hitter)
						logging.info("Set FantasyPlayerSeason %s using %s" % (dbplayerseason.key(), hitter))
						entitylist.append(dbplayerseason)

		for key, values in players_map.items():
			if values['new_team'] != values['prev_team']:
				if values['prev_team'] is not None:
					prev_fantasyteam = dygfantasystatsmodel.FantasyTeam(
						key=db.Key.from_path("FantasyTeam", values['prev_team'].id()),
						year=0,
						teamname="temp"
					)
				else:
					prev_fantasyteam = None
				if values['new_team'] is not None:
					new_fantasyteam = dygfantasystatsmodel.FantasyTeam(
						key=db.Key.from_path("FantasyTeam", values['new_team'].id()),
						year=0,
						teamname="temp"
					)
				else:
					new_fantasyteam = None
				player = dygfantasystatsmodel.FantasyPlayer(
					key=db.Key.from_path("FantasyPlayer", key),
					cbsplayerid=0,
					fantasyteam=new_fantasyteam,
				)
				log_player_team_change(player, batch_cycle_id, prev_fantasyteam)
		db.put(entitylist)

	def handle_stats(self, batch_cycle_id, position="C", inseason=False, override_final_stats=False):
		year = self.get_current_year()
		cookie = get_cookie()
		if position == "OF":
			max = 90
		elif position == "SP":
			max = 150
		else:
			max = 30

		if inseason:
			url = 'http://dyg.baseball.cbssports.com/stats/stats-main/all:' + position + '/ytd:p/scoring/?print_rows=%s' % (9999 if max > 100 else 100)
		else:
			url = 'http://dyg.baseball.cbssports.com/stats/stats-main/all:' + position + '/' + str(year) + ':p/scoring/?print_rows=%s' % (9999 if max > 100 else 100)

		page = dygutil.get_page(cookie, url)
		page = re.sub("aria-label='.*?' href=", "href=", page)
		soup = BeautifulSoup(page, convertEntities=BeautifulSoup.HTML_ENTITIES)

		players_soup = soup.find("div", {'id': "sortableStats"}).find("table")
		try:
			players = self.parse_player_stats(players_soup, max=max)
		except:
			logging.info("url=%s" % url)
			raise

		season = dygfantasystatsmodel.FantasySeason.get_or_insert_by_values(year)

		fantasyteams = dygfantasystatsmodel.FantasyTeam.all().filter("year = ", year).fetch(1000)

		def getfantasyteam(fantasyteams, cbsteamid):
			fantasyteam = None
			for t in fantasyteams:
				if t.cbsteamid == cbsteamid:
					fantasyteam = t
			return fantasyteam

		entitylist = []
		logging.info(players)

		for player in players:
			assert player['mlbteamcode'] is not None and player['mlbteamcode'].strip() != ""
			fantasyteam = None
			if 'cbsteamid' not in player:
				logging.warning("player=%s" % player)
			if player['cbsteamid'] != 0:
				fantasyteam = getfantasyteam(fantasyteams, player['cbsteamid'])

			dbplayer = dygfantasystatsmodel.FantasyPlayer.get_or_insert_by_values(
					player['cbsplayerid'])
			prev_fantasyteam = dbplayer.fantasyteam
			dbplayer.fantasyteam = fantasyteam
			if dbplayer.fantasyteam != prev_fantasyteam:
				log_player_team_change(dbplayer, batch_cycle_id, prev_fantasyteam)
			dbplayer.firstname = player['firstname']
			dbplayer.lastname = player['lastname']
			dbplayer.primaryposition = player['primaryposition']
			dbplayer.mlbteamcode = player['mlbteamcode']
			dbplayerseason = dygfantasystatsmodel.FantasyPlayerSeason.get_or_insert_by_values(dbplayer, season)
			if not dbplayerseason.is_final or override_final_stats:
				prev_stat_fpts = dbplayerseason.stat_fpts
				if player['primaryposition'] == "P" or player['primaryposition'] == "SP" or player['primaryposition'] == "RP":
					self.set_pitcher_stats(dbplayerseason, player)
				else:
					self.set_hitter_stats(dbplayerseason, player)
				entitylist.append(dbplayerseason)
			if dbplayerseason.stat_fpts > 0:
				dbplayer.most_recent_season = season
			dbplayer.set_calculated_fields()
			entitylist.append(dbplayer)

		db.put(entitylist)

	def parse_player_stats(self, soup, max=9999):
		players = []

		def getcols(headers_soup):
			cols = headers_soup.findAll("th")
			cols = cols[1:]
			outputcols = [col.text for col in cols]
			return outputcols

		headers_soup = soup.find("tr", {'class': "label"})
		cols = getcols(headers_soup)

		all_rows = soup.findAll("tr")
		all_rows = [row for row in all_rows if len(row.findAll("td")) > 1]
		player_rows = all_rows[:-1]
		player_rows = player_rows[:max]

		def extract_player_info(players_list, cols, player_rows):
			for player_row in player_rows:
				player_info = {}
				logging.info("player_row=%s" % player_row)
				name_col = player_row.findAll("td")[2]
				name_col_anchor = name_col.find("a")
				player_name = name_col_anchor.text
				try:
					href = name_col_anchor['href']
				except:
					logging.info("player_row=%s" % player_row)
					raise
				player_info['cbsplayerid'] = int(href[href.rfind("/")+1:].split('?')[0])

				posteam = name_col.find("span", {'class': "playerPositionAndTeam"}).text
				posteam = posteam.replace('&nbsp;', ' ').strip()
				parts = posteam.split(' | ')
				if len(parts) == 2:
					player_info['primaryposition'] = parts[0]
					player_info['mlbteamcode'] = parts[1]
				else:
					player_info['primaryposition'] = "U"
					player_info['mlbteamcode'] = parts[0].strip()
				if not player_info['mlbteamcode']:
					logging.warning("No mlbteamcode; player_row=%s" % player_row)

				if player_info['primaryposition'] == 'LF' or player_info['primaryposition'] == 'CF' or player_info['primaryposition'] == 'RF':
					player_info['primaryposition'] = "OF"

				player_cols = player_row.findAll("td")
				player_cols = player_cols[1:]

				statsstartcol = 0
				if 'Avail' in cols:
					statsstartcol = 1
					teamname = 'Free Agent'
					cbsteamid = 0
					# <td align="left"><a href='/teams/5'>Staines West End Massive</a></td>
					# <td align="left">Free Agent</td>
					team_col = player_cols[0]
					team_anchor = team_col.find("a")
					if team_anchor:
						href = team_anchor['href']
						cbsteamid = int(href[href.rfind("/")+1:])
						tooltip_span = team_anchor.find("span", {'class': "tooltip"})
						teamname = tooltip_span['title'] if tooltip_span else team_anchor.text
					if teamname.startswith("Owned by ") or teamname.startswith("Owned By "):
						teamname = teamname[len("Owned by "):].strip()
					player_info['cbsteamid'] = cbsteamid
					player_info['teamname'] = teamname

				for i in range(statsstartcol, len(player_cols)):
					if i < len(cols):
						s = player_cols[i].text
						try:
							player_info[cols[i]] = float(s)
						except:
							try:
								logging.info("s=%s; i=%s; cols=%s; player_cols=%s; player_info=%s" % (s, i, cols, player_cols, player_info))
							except:
								pass
							player_info[cols[i]] = 0.0

				player_info['firstname'], _, player_info['lastname'] = player_name.partition(' ')

				players_list.append(player_info)

		extract_player_info(players, cols, player_rows)

		return players

	def handle_mlb_teams(self):
		page = dygutil.get_page(None, 'http://www.cbssports.com/mlb/standings/regular')

		soup = BeautifulSoup(page, convertEntities=BeautifulSoup.HTML_ENTITIES)

		def match_class(node, class_name):
			classes = [value for (key, value) in node.attrs if key=='class']
			if not classes: return False
			class_names = classes[0].strip().split(' ')
			return class_name in class_names

		tables = soup.findAll("table", {'class': "TableBase-table"})[:4]
		tables = [tables[0], tables[2]]
		for table in tables:
			rows = [_ for _ in table.findAll("tr") if match_class(_, 'TableBase-bodyTr')]
			for row in rows:
				cells = row.findAll('td')
				team_anchor = cells[0].findAll('a')[1]
				team_code = team_anchor['href'].split('/')[3]
				dbteam = dygfantasystatsmodel.MLBTeam.get_or_insert(team_code, teamcode=team_code)
				dbteam.teamname = team_anchor.text
				dbteam.wins = int(cells[1].text)
				dbteam.losses = int(cells[2].text)
				dbteam.put()

	def handle_salary(self):
		year = self.get_current_year()
		capvalues = {}
		for i in range(0, 8):
			if i == 0:
				el = "eligible_rp"
				n1 = 25
				n2 = 30
			elif i == 1:
				el = "eligible_sp"
				n1 = 125
				n2 = 150
			elif i == 2:
				el = "eligible_c"
				n1 = 25
				n2 = 30
			elif i == 3:
				el = "eligible_1b"
				n1 = 25
				n2 = 30
			elif i == 4:
				el = "eligible_2b"
				n1 = 25
				n2 = 30
			elif i == 5:
				el = "eligible_3b"
				n1 = 25
				n2 = 30
			elif i == 6:
				el = "eligible_ss"
				n1 = 25
				n2 = 30
			elif i == 7:
				el = "eligible_of"
				n1 = 75
				n2 = 90
			top = dygfantasystatsmodel.FantasyPlayer.all().filter(el + " = ", True).order("-fpts_year0_used").fetch(n2)
			tot1 = 0.0
			tot2 = 0.0
			cnt1 = 0
			cnt2 = 0
			index = 0
			for p in top:
				index += 1
				if index <= n1:
					cnt1 += 1
					tot1 += p.fpts_year0_used
				if index <= n2:
					cnt2 += 1
					tot2 += p.fpts_year0_used
			avg1 = tot1 / float(cnt1)
			avg2 = tot2 / float(cnt2)

			capvalues[el + '_1'] = avg1 / 10.0
			capvalues[el + '_2'] = avg2 / 10.0

		settings = dygfantasystatsmodel.SalaryCapSettings.get_or_insert('MASTER')
		settings.current_year = year
		settings.capvalue_rp_25 = capvalues['eligible_rp_1']
		settings.capvalue_rp_30 = capvalues['eligible_rp_2']
		settings.capvalue_sp_125 = capvalues['eligible_sp_1']
		settings.capvalue_sp_150 = capvalues['eligible_sp_2']
		settings.capvalue_c_25 = capvalues['eligible_c_1']
		settings.capvalue_c_30 = capvalues['eligible_c_2']
		settings.capvalue_1b_25 = capvalues['eligible_1b_1']
		settings.capvalue_1b_30 = capvalues['eligible_1b_2']
		settings.capvalue_2b_25 = capvalues['eligible_2b_1']
		settings.capvalue_2b_30 = capvalues['eligible_2b_2']
		settings.capvalue_3b_25 = capvalues['eligible_3b_1']
		settings.capvalue_3b_30 = capvalues['eligible_3b_2']
		settings.capvalue_ss_25 = capvalues['eligible_ss_1']
		settings.capvalue_ss_30 = capvalues['eligible_ss_2']
		settings.capvalue_of_75 = capvalues['eligible_of_1']
		settings.capvalue_of_90 = capvalues['eligible_of_2']
		settings.put()

	def handle_player_details_temp(self, batch_cycle_id, player):
		if player.cbsplayerid > 1000000000: return

		year = self.get_current_year()

		mlbteamcode = player.mlbteamcode
		if not mlbteamcode:
			logging.warning("No mlbteamcode for player %s %s (%s)" % (player.firstname, player.lastname, player.cbsplayerid))
		mlbteam = dygfantasystatsmodel.MLBTeam.get_by_key_name(mlbteamcode)
		if not mlbteam and mlbteamcode in ["MIA", "LAA", "LAD"]:
			if mlbteamcode == "MIA": mlbteamcode = "FLA"
			if mlbteamcode == "LAA": mlbteamcode = "ANA"
			if mlbteamcode == "LAD": mlbteamcode = "LA"
			mlbteam = dygfantasystatsmodel.MLBTeam.get_by_key_name(mlbteamcode)
		if not mlbteam:
			logging.info("Could not retrieve MLBTeam for team code %s or %s." % (mlbteamcode, player.mlbteamcode))
		headerstarttoken = '<div class="playerHeaderContainer">'
		headerendtoken = '</div>'
		playerbiostarttoken = '<div class="playerBioDetails">'
		playerbioendtoken = '</div>'
		injurystarttoken = '>Injury Report</td>'
		injuryendtoken = '</div>'

		eligibilitystarttoken = '>Eligibility Breakdown</td>'
		eligibilityendtoken = '</table>'

		cookie = get_cookie()

		if player.primaryposition == "P" or player.primaryposition == "RP" or player.primaryposition == "SP":
			headerstoken = '&Pitchers:sort_col=1">Player<'
		else:
			headerstoken = '&Batters:sort_col=1">Player<'
		headersendtoken = '</tr>'
		playertoken = "><a class='playerLink' href="
		playersendtoken = '</table>'

		i = 0
		thisyear = year
		season = dygfantasystatsmodel.FantasySeason.get_or_insert_by_values(thisyear)
		dbplayerseason = dygfantasystatsmodel.FantasyPlayerSeason.get_by_key_name('ps_' + player.key().name() + "_" + season.key().name())
		playerseason_exists = True
		if dbplayerseason == None:
			playerseason_exists = False
		elif dbplayerseason.stat_fpts == None:
			playerseason_exists = False
		elif i >= 1 and not dbplayerseason.is_final:
			playerseason_exists = False
		if not playerseason_exists or not dbplayerseason.is_final:
			dbplayerseason = dygfantasystatsmodel.FantasyPlayerSeason.get_or_insert_by_values(player, season)
			prev_stat_fpts = dbplayerseason.stat_fpts
			url = 'http://dyg.baseball.cbssports.com/stats/stats-main/' + str(player.cbsplayerid) + '/' + str(thisyear) + ':p/scoring/'
			page = dygutil.get_page(cookie, url)
			players = self.parse_player_stats(page, headerstoken, headersendtoken, playertoken, playersendtoken)
			if len(players) > 0:
				if player.primaryposition == "P" or player.primaryposition == "RP" or player.primaryposition == "SP":
					self.set_pitcher_stats(dbplayerseason, players[0])
				else:
					self.set_hitter_stats(dbplayerseason, players[0])
			if i >= 1: dbplayerseason.is_final = True
			if prev_stat_fpts != 0 and dbplayerseason.stat_fpts != prev_stat_fpts:
				raise Exception("stat_fpts has changed from %s to %s for player %s (%s)" % (prev_stat_fpts, dbplayerseason.stat_fpts, dbplayerseason.player.lastname, dbplayerseason.player.cbsplayerid))
			dbplayerseason.put()

		projectionsmultiplier = float(mlbteam.endseasongames) / float(mlbteam.games) if mlbteam.games > 0 else 0.0

		seasons = dygfantasystatsmodel.FantasyPlayerSeason.all().filter("player = ", player)
		fpts_year0_actual = 0.0
		fpts_year0_projected = 0.0
		if not player.dl_season: player.fpts_year0_projected_override = None
		fpts_year0_projected_override = player.fpts_year0_projected_override
		fpts_yearminus1 = 0.0
		fpts_yearminus2 = 0.0
		for season in seasons:
			if season.year == year:
				fpts_year0_actual = season.stat_fpts
				if season.is_final:
					fpts_year0_projected = season.stat_fpts
				else:
					fpts_year0_projected = season.stat_fpts * projectionsmultiplier
				if player.dl_season and fpts_year0_projected_override == None:
					fpts_year0_projected_override = season.stat_fpts
			elif season.year == year-1:
				fpts_yearminus1 = season.stat_fpts
			elif season.year == year-2:
				fpts_yearminus2 = season.stat_fpts
		if player.fpts_year0_actual != 0 and fpts_year0_actual != player.fpts_year0_actual:
			raise Exception("fpts_year0_actual has changed from %s to %s for player %s (%s)" % (player.fpts_year0_actual, fpts_year0_actual, player.lastname, player.cbsplayerid))
		player.fpts_year0_actual = fpts_year0_actual
		player.fpts_year0_projected = fpts_year0_projected
		player.fpts_year0_projected_override = fpts_year0_projected_override
		player.fpts_yearminus1 = fpts_yearminus1
		player.fpts_yearminus2 = fpts_yearminus2
		player.put()

	def handle_player_details(self, batch_cycle_id, player, override_final_stats=False):
		if player.cbsplayerid > 1000000000: return

		year = self.get_current_year()

		mlbteamcode = player.mlbteamcode
		if not mlbteamcode:
			logging.warning("No mlbteamcode for player %s %s (%s)" % (player.firstname, player.lastname, player.cbsplayerid))
		mlbteam = dygfantasystatsmodel.MLBTeam.get_by_key_name(mlbteamcode)
		if not mlbteam and mlbteamcode in ["MIA", "LAA", "LAD"]:
			if mlbteamcode == "MIA": mlbteamcode = "FLA"
			if mlbteamcode == "LAA": mlbteamcode = "ANA"
			if mlbteamcode == "LAD": mlbteamcode = "LA"
			mlbteam = dygfantasystatsmodel.MLBTeam.get_by_key_name(mlbteamcode)
		if not mlbteam:
			logging.info("Could not retrieve MLBTeam for team code %s or %s." % (mlbteamcode, player.mlbteamcode))

		cookie = get_cookie()
		page = dygutil.get_page(cookie, 'http://dyg.baseball.cbssports.com/players/playerpage/' + str(player.cbsplayerid))
		soup = BeautifulSoup(page, convertEntities=BeautifulSoup.HTML_ENTITIES)

		#players_soup = soup.find("div", {'id': "sortableStats"}).find("table")
		#players = self.parse_player_stats(players_soup, max=max)

		#page = unicode(page, errors='ignore')

		player_info = soup.find("div", {'class': "playerInfo"})
		player_details = player_info.find("div", {'class': "player_details"})
		if not player_details: return
		player_name = player_details.find("h1", {'class': "name"})
		if not player_name: return
		if player_name.text != player.firstname + ' ' + player.lastname: return

		status = 'A'
		pro_status = player_details.find("div", {'class': "pro_status"})
		if pro_status:
			ppstatusbar = pro_status.find("div", {'class': "ppstatusbar"})
			if ppstatusbar == "Minors": status = 'M'
		#if headerblock.find('Disabled') > 0: status = 'DL'

		ht_wt_age_table = player_info.find("div", {'class': "player_extras"}).find("table")
		if ht_wt_age_table:
			ht_wt_age = ht_wt_age_table.find("tr").findAll("td")[1].text
			parts = ht_wt_age.split(" | ")
			age_str = parts[-1].strip()
			if age_str.endswith(" years old"):
				try:
					age = int(age_str[:-10].strip())
				except:
					age = 99
			else:
				age = 99
		else:
			age = 99

		injurydetails = ''
		if status == 'DL':
			pass

		dl_15 = False
		dl_60 = False
		dl_season = False

		#if injurydetails.find('15-day DL') > 0: dl_15 = True
		#if injurydetails.find('60-day DL') > 0: dl_60 = True
		#if injurydetails.lower().find('out for season') > 0: dl_season = True

		cbsteamid = 0
		teamname = 'Free Agent'
		fantasy_info = soup.find("div", {'class': "fantasy_info"})
		if fantasy_info:
			team_info = fantasy_info.find("div", {'class': "team_info"})
			if team_info:
				team_anchor = team_info.find("a")
				if team_anchor:
					href = team_anchor['href']
					cbsteamid = int(href[href.rfind("/")+1:])
					teamname = team_anchor.text

		fantasyteams = dygfantasystatsmodel.FantasyTeam.all().filter("year = ", year).fetch(1000)

		def getfantasyteam(fantasyteams, cbsteamid):
			fantasyteam = None
			for t in fantasyteams:
				if t.cbsteamid == cbsteamid:
					fantasyteam = t
			return fantasyteam

		fantasyteam = None
		if cbsteamid != 0:
			fantasyteam = getfantasyteam(fantasyteams, cbsteamid)

		page = dygutil.get_page(cookie, 'http://dyg.baseball.cbssports.com/players/playerpage/eligibility/' + str(player.cbsplayerid))
		soup = BeautifulSoup(page, convertEntities=BeautifulSoup.HTML_ENTITIES)
		eligibility_table = soup.find("tr", {'class': "title"}).findParent("table")
		position_rows = eligibility_table.findAll("tr")[2:]

		thisyear_games_c = 0
		thisyear_games_1b = 0
		thisyear_games_2b = 0
		thisyear_games_3b = 0
		thisyear_games_ss = 0
		thisyear_games_of = 0
		thisyear_games_dh = 0
		thisyear_games_rp = 0
		thisyear_games_sp = 0

		lastyear_games_c = 0
		lastyear_games_1b = 0
		lastyear_games_2b = 0
		lastyear_games_3b = 0
		lastyear_games_ss = 0
		lastyear_games_of = 0
		lastyear_games_dh = 0
		lastyear_games_rp = 0
		lastyear_games_sp = 0

		for position_row in position_rows:
			position_cols = position_row.findAll("td")
			pos = position_cols[0].text
			thisyearcol = position_cols[3]
			lastyearcol = position_cols[2]

			try:
				thisyear_games = int(thisyearcol.text)
			except:
				thisyear_games = 0
			try:
				lastyear_games = int(lastyearcol.text)
			except:
				lastyear_games = 0

			if pos == 'C':
				thisyear_games_c = thisyear_games
				lastyear_games_c = lastyear_games
			elif pos == '1B':
				thisyear_games_1b = thisyear_games
				lastyear_games_1b = lastyear_games
			elif pos == '2B':
				thisyear_games_2b = thisyear_games
				lastyear_games_2b = lastyear_games
			elif pos == '3B':
				thisyear_games_3b = thisyear_games
				lastyear_games_3b = lastyear_games
			elif pos == 'SS':
				thisyear_games_ss = thisyear_games
				lastyear_games_ss = lastyear_games
			elif pos == 'OF':
				thisyear_games_of = thisyear_games
				lastyear_games_of = lastyear_games
			elif pos == 'DH':
				thisyear_games_dh = thisyear_games
				lastyear_games_dh = lastyear_games
			elif pos == 'SP':
				thisyear_games_sp = thisyear_games
				lastyear_games_sp = lastyear_games
			elif pos == 'RP':
				thisyear_games_rp = thisyear_games
				lastyear_games_rp = lastyear_games

		player.status = status
		player.dl_15 = dl_15
		player.dl_60 = dl_60
		player.dl_season = dl_season
		player.age = age

		season = dygfantasystatsmodel.FantasySeason.get_or_insert_by_values(year)
		dbplayerseason = dygfantasystatsmodel.FantasyPlayerSeason.get_or_insert_by_values(player, season)
		dbplayerseason.games_c = thisyear_games_c
		dbplayerseason.games_1b = thisyear_games_1b
		dbplayerseason.games_2b = thisyear_games_2b
		dbplayerseason.games_3b = thisyear_games_3b
		dbplayerseason.games_ss = thisyear_games_ss
		dbplayerseason.games_of = thisyear_games_of
		dbplayerseason.games_dh = thisyear_games_dh
		dbplayerseason.games_sp = thisyear_games_sp
		dbplayerseason.games_rp = thisyear_games_rp
		dbplayerseason.put()

		season = dygfantasystatsmodel.FantasySeason.get_or_insert_by_values(year-1)
		dbplayerseason.games_c = lastyear_games_c
		dbplayerseason.games_1b = lastyear_games_1b
		dbplayerseason.games_2b = lastyear_games_2b
		dbplayerseason.games_3b = lastyear_games_3b
		dbplayerseason.games_ss = lastyear_games_ss
		dbplayerseason.games_of = lastyear_games_of
		dbplayerseason.games_dh = lastyear_games_dh
		dbplayerseason.games_sp = lastyear_games_sp
		dbplayerseason.games_rp = lastyear_games_rp
		dbplayerseason.put()

		for i in range (0, 3):
			thisyear = year - i
			season = dygfantasystatsmodel.FantasySeason.get_or_insert_by_values(thisyear)
			dbplayerseason = dygfantasystatsmodel.FantasyPlayerSeason.get_by_key_name('ps_' + player.key().name() + "_" + season.key().name())
			playerseason_exists = True
			if dbplayerseason == None:
				playerseason_exists = False
			elif dbplayerseason.stat_fpts == None:
				playerseason_exists = False
			elif i >= 1 and not dbplayerseason.is_final:
				playerseason_exists = False
			if not playerseason_exists or not dbplayerseason.is_final or override_final_stats:
				dbplayerseason = dygfantasystatsmodel.FantasyPlayerSeason.get_or_insert_by_values(player, season)
				if thisyear == year and not (dbplayerseason.is_final and override_final_stats):
					url = 'http://dyg.baseball.cbssports.com/stats/stats-main/' + str(player.cbsplayerid) + '/ytd:p/scoring/'
				else:
					url = 'http://dyg.baseball.cbssports.com/stats/stats-main/' + str(player.cbsplayerid) + '/' + str(thisyear) + ':p/scoring/'
				# http://dyg.baseball.cbssports.com/stats/stats-main/1657581/2014:p/scoring/
				page = dygutil.get_page(cookie, url)
				page = re.sub("aria-label='.*?' href=", "href=", page)
				soup = BeautifulSoup(page, convertEntities=BeautifulSoup.HTML_ENTITIES)
				stats_tables = soup.find("div", {'id': "sortableStats"}).findAll("table")
				if player.primaryposition == "P" or player.primaryposition == "RP" or player.primaryposition == "SP":
					players = self.parse_player_stats(stats_tables[1])
				else:
					players = self.parse_player_stats(stats_tables[0])
				if len(players) > 0:
					if player.primaryposition == "P" or player.primaryposition == "RP" or player.primaryposition == "SP":
						self.set_pitcher_stats(dbplayerseason, players[0])
					else:
						self.set_hitter_stats(dbplayerseason, players[0])
				if i >= 1: dbplayerseason.is_final = True
				dbplayerseason.put()

		projectionsmultiplier = float(mlbteam.endseasongames) / float(mlbteam.games) if mlbteam.games > 0 else 0.0

		seasons = dygfantasystatsmodel.FantasyPlayerSeason.all().filter("player = ", player)
		fpts_year0_actual = 0.0
		fpts_year0_projected = 0.0
		if not player.dl_season: player.fpts_year0_projected_override = None
		fpts_year0_projected_override = player.fpts_year0_projected_override
		fpts_yearminus1 = 0.0
		fpts_yearminus2 = 0.0
		for season in seasons:
			if season.year == year:
				fpts_year0_actual = season.stat_fpts
				if season.is_final:
					fpts_year0_projected = season.stat_fpts
				else:
					fpts_year0_projected = season.stat_fpts * projectionsmultiplier
				if player.dl_season and fpts_year0_projected_override == None:
					fpts_year0_projected_override = season.stat_fpts
			elif season.year == year-1:
				fpts_yearminus1 = season.stat_fpts
			elif season.year == year-2:
				fpts_yearminus2 = season.stat_fpts
		player.fpts_year0_actual = fpts_year0_actual
		player.fpts_year0_projected = fpts_year0_projected
		player.fpts_year0_projected_override = fpts_year0_projected_override
		player.fpts_yearminus1 = fpts_yearminus1
		player.fpts_yearminus2 = fpts_yearminus2
		#logging.debug("Player=%s (%s); player.fpts_year0_actual=%s; player.fpts_yearminus1=%s; fantasyteam=%s" % (player.lastname, player.primaryposition, player.fpts_year0_actual, player.fpts_yearminus1, fantasyteam))
		player.eligible_rp = (player.primaryposition == "RP" or thisyear_games_rp >= 10 or lastyear_games_rp >= 10)
		player.eligible_sp = (player.primaryposition == "SP" or thisyear_games_sp >= 5 or lastyear_games_sp >= 5)
		player.eligible_p = (player.primaryposition == 'P')
		player.eligible_c = (player.primaryposition == "C" or thisyear_games_c >= 10 or lastyear_games_c >= 10)
		player.eligible_1b = (player.primaryposition == "1B" or thisyear_games_1b >= 10 or lastyear_games_1b >= 10)
		player.eligible_2b = (player.primaryposition == "2B" or thisyear_games_2b >= 10 or lastyear_games_2b >= 10)
		player.eligible_3b = (player.primaryposition == "3B" or thisyear_games_3b >= 10 or lastyear_games_3b >= 10)
		player.eligible_ss = (player.primaryposition == "SS" or thisyear_games_ss >= 10 or lastyear_games_ss >= 10)
		player.eligible_of = (player.primaryposition == "OF" or thisyear_games_of >= 10 or lastyear_games_of >= 10)
		player.eligible_dh = (player.primaryposition <> 'P' and player.primaryposition <> 'RP' and player.primaryposition <> 'SP' and not player.eligible_c and not player.eligible_1b and not player.eligible_2b and not player.eligible_3b and not player.eligible_ss and not player.eligible_of)
		player.nextyr_eligible_rp = (thisyear_games_rp >= 10)
		player.nextyr_eligible_sp = (thisyear_games_sp >= 5)
		player.nextyr_eligible_p = (player.primaryposition == 'P')
		player.nextyr_eligible_c = (thisyear_games_c >= 10)
		player.nextyr_eligible_1b = (thisyear_games_1b >= 10)
		player.nextyr_eligible_2b = (thisyear_games_2b >= 10)
		player.nextyr_eligible_3b = (thisyear_games_3b >= 10)
		player.nextyr_eligible_ss = (thisyear_games_ss >= 10)
		player.nextyr_eligible_of = (thisyear_games_of >= 10)
		player.nextyr_eligible_dh = (player.primaryposition <> 'P' and player.primaryposition <> 'RP' and player.primaryposition <> 'SP' and not player.nextyr_eligible_c and not player.nextyr_eligible_1b and not player.nextyr_eligible_2b and not player.nextyr_eligible_3b and not player.nextyr_eligible_ss and not player.nextyr_eligible_of)
		prev_fantasyteam = player.fantasyteam
		player.fantasyteam = fantasyteam
		if player.fantasyteam != prev_fantasyteam:
			log_player_team_change(player, batch_cycle_id, prev_fantasyteam)
		player.put()

	def set_hitter_stats(self, dbstats, hitter):
		if '1B' not in hitter: return dbstats

		dbstats.stat_1b = hitter['1B']
		dbstats.stat_2b = hitter['2B']
		dbstats.stat_3b = hitter['3B']
		dbstats.stat_bb = hitter['BB']
		dbstats.stat_cs = hitter['CS']
		dbstats.stat_cyc = hitter['CYC']
		dbstats.stat_e = hitter['E']
		dbstats.stat_gdp = hitter['GDP']
		dbstats.stat_hp = hitter['HP']
		dbstats.stat_hr = hitter['HR']
		dbstats.stat_ko = hitter['K']
		dbstats.stat_ofast = hitter['OFAST']
		dbstats.stat_pbc = hitter['PBC']
		dbstats.stat_r = hitter['R']
		dbstats.stat_rbi = hitter['RBI']
		dbstats.stat_sb = hitter['SB']
		dbstats.stat_sf = hitter['SF']
		dbstats.stat_fpts = hitter['FPTS']
		dbstats.stat_fpts_old = hitter['FPTS']
		if 'WEEKS' in hitter: dbstats.weeks = int(hitter['WEEKS'])
		if 'SEASONS' in hitter: dbstats.seasons = int(hitter['SEASONS'])

		return dbstats

	def get_hitter_stats(self, dbstats, hitter):
		hitter['1B'] = dbstats.stat_1b
		hitter['2B'] = dbstats.stat_2b
		hitter['3B'] = dbstats.stat_3b
		hitter['BB'] = dbstats.stat_bb
		hitter['CS'] = dbstats.stat_cs
		hitter['CYC'] = dbstats.stat_cyc
		hitter['E'] = dbstats.stat_e
		hitter['GDP'] = dbstats.stat_gdp
		hitter['HP'] = dbstats.stat_hp
		hitter['HR'] = dbstats.stat_hr
		hitter['K'] = dbstats.stat_ko
		hitter['OFAST'] = dbstats.stat_ofast
		hitter['PBC'] = dbstats.stat_pbc
		hitter['R'] = dbstats.stat_r
		hitter['RBI'] = dbstats.stat_rbi
		hitter['SB'] = dbstats.stat_sb
		hitter['SF'] = dbstats.stat_sf
		hitter['FPTS'] = dbstats.stat_fpts
		hitter['WEEKS'] = dbstats.weeks
		hitter['SEASONS'] = dbstats.seasons

		return hitter

	def add_to_totals(self, element, totals):
		for k in element.keys():
			try:
				val = float(element[k])
				if k not in totals:
					totals[k] = 0.0
				totals[k] += val
			except:
				pass

	def innings_to_outs(self, innings):
		whole_innings = int(innings)
		partial_innings = innings - float(int(innings))
		whole_inning_outs = whole_innings * 3
		if partial_innings > .6:
			partial_inning_outs = 2
		elif partial_innings >= .3:
			partial_inning_outs = 1
		else:
			partial_inning_outs = 0
		return whole_inning_outs + partial_inning_outs

	def set_pitcher_stats(self, dbstats, pitcher):
		if 'B' not in pitcher: return dbstats

		dbstats.stat_b = pitcher['B']
		dbstats.stat_bbi = pitcher['BB']
		dbstats.stat_bs = pitcher['BS']
		dbstats.stat_cg = pitcher['CG']
		dbstats.stat_er = pitcher['ER']
		dbstats.stat_ha = pitcher['H']
		dbstats.stat_hb = pitcher['HB']
		dbstats.stat_inn = pitcher['INN']
		dbstats.stat_k = pitcher['K']
		dbstats.stat_l = pitcher['L']
		dbstats.stat_nh = pitcher['NH']
		dbstats.stat_pg = pitcher['PG']
		dbstats.stat_pko = pitcher['PKO']
		dbstats.stat_qs = pitcher['QS']
		dbstats.stat_s = pitcher['S']
		dbstats.stat_so = pitcher['SO']
		dbstats.stat_w = pitcher['W']
		dbstats.stat_wp = pitcher['WP']
		dbstats.stat_fpts = pitcher['FPTS']
		if 'FPTS_OLD' in pitcher: dbstats.stat_fpts_old = pitcher['FPTS_OLD']
		if 'WEEKS' in pitcher: dbstats.weeks = int(pitcher['WEEKS'])
		if 'SEASONS' in pitcher: dbstats.seasons = int(pitcher['SEASONS'])

		return dbstats

	def get_pitcher_stats(self, dbstats, pitcher):
		pitcher['B'] = dbstats.stat_b
		pitcher['BB'] = dbstats.stat_bbi
		pitcher['BS'] = dbstats.stat_bs
		pitcher['CG'] = dbstats.stat_cg
		pitcher['ER'] = dbstats.stat_er
		pitcher['H'] = dbstats.stat_ha
		pitcher['HB'] = dbstats.stat_hb
		pitcher['INN'] = dbstats.stat_inn
		pitcher['K'] = dbstats.stat_k
		pitcher['L'] = dbstats.stat_l
		pitcher['NH'] = dbstats.stat_nh
		pitcher['PG'] = dbstats.stat_pg
		pitcher['PKO'] = dbstats.stat_pko
		pitcher['QS'] = dbstats.stat_qs
		pitcher['S'] = dbstats.stat_s
		pitcher['SO'] = dbstats.stat_so
		pitcher['W'] = dbstats.stat_w
		pitcher['WP'] = dbstats.stat_wp
		pitcher['FPTS'] = dbstats.stat_fpts
		pitcher['FPTS_OLD'] = dbstats.stat_fpts_old
		pitcher['WEEKS'] = dbstats.weeks
		pitcher['SEASONS'] = dbstats.seasons

		return pitcher

	def handle_schedule(self, year):
		return	# skip for now
		cookie = get_cookie()

		# for historical:
		# http://dyg.baseball.cbssports.com/api/league/history/results?version=3.0&response_format=JSON&league_id=dyg&SPORT=baseball&period=all&timeframe=2018

		page = dygutil.get_page(cookie, 'http://dyg.baseball.cbssports.com/api/league/schedules-journalists?version=3.0&response_format=JSON&league_id=dyg&SPORT=baseball&period=all')
		# TODO - load JSON
		
		soup = BeautifulSoup(page, convertEntities=BeautifulSoup.HTML_ENTITIES)

		def get_class_lambda(tag_name, class_name):
			return "lambda tag: tag.name == '%s' and \"class\" in [key for (key, value) in tag.attrs] and \"%s\" in [value.split(" ") for (key, value) in tag.attrs if key==\"class\"][0]" % (tag_name, class_name)

		weeks_soup = soup.find("div", {'class': "sc-1ku6h3s-1 fJJqSf"}).findAll(eval(get_class_lambda("div", "iXZywE")))
		weeks = []
		for week_soup in weeks_soup:
			weekinfo = {}
			weekgames = []

			week_table = week_soup.find("table")
			if not week_table:
				break
			header_row = week_table.find("tr", {'class': "label"})
			dates_th = header_row.findAll("th")[0]
			halves = dates_th.text.split(" - ")
			start_date_s = halves[0][halves[0].rfind(" ")+1:].strip()
			end_date_s = halves[1][:halves[1].find(" ")].strip()

			weekinfo['startdate'] = datetime.datetime(*time.strptime(start_date_s, "%m/%d/%y")[:6])
			weekinfo['enddate'] = datetime.datetime(*time.strptime(end_date_s, "%m/%d/%y")[:6])

			def extractgameinfo(games_list, teams, games_soup):
				for game_soup in games_soup:
					#<tr class="row1" align="right" valign="top"><td align="left" width="40%"><a href='/teams/17'>TGM and the Team to be Named Later</a></td><td align="left" width="40%"><a href='/teams/5'>Staines West End Massive</a></td><td align="left" width="20%"></td></tr>
					gameinfo = {}
					visitorinfo = {}
					homeinfo = {}

					team_anchors = game_soup.findAll("a")
					visitor_anchor = team_anchors[0]
					home_anchor = team_anchors[1]
					score_anchor = team_anchors[2] if len(team_anchors) > 2 else None

					visitorinfo['teamid'] = int(visitor_anchor['href'].split('/')[-1])
					visitorinfo['teamname'] = visitor_anchor.text.strip()

					homeinfo['teamid'] = int(home_anchor['href'].split('/')[-1])
					homeinfo['teamname'] = home_anchor.text.strip()

					# TODO once we see how final scores look.
					score_info = score_anchor.findAll(text=True) if score_anchor else [""]
					if score_info[0] not in ["", "View Matchup", "Preview Matchup"]:
						visitorinfo['points'] = int(float(score_info[0]))
						homeinfo['points'] = int(float(score_info[2]))

					if visitorinfo['teamname'] == "Bye" or homeinfo['teamname'] == "Bye" or visitorinfo['teamname'] == "TBA" or homeinfo['teamname'] == "TBA":
						continue

					for t in teams:
						if visitorinfo.get('teamid') and homeinfo.get('teamid'):
							if t.cbsteamid == visitorinfo['teamid']:
								visitorinfo['team'] = t
							elif t.cbsteamid == homeinfo['teamid']:
								homeinfo['team'] = t
						else:
							if t.teamname == visitorinfo['teamname']:
								visitorinfo['team'] = t
							elif t.teamname == homeinfo['teamname']:
								homeinfo['team'] = t
					gameinfo['visitor'] = visitorinfo
					gameinfo['home'] = homeinfo

					games_list.append(gameinfo)

			teams = dygfantasystatsmodel.FantasyTeam.all().filter("year = ", year).fetch(1000)
			extractgameinfo(weekgames, teams, week_table.findAll("tr")[1:])

			weekinfo['games'] = weekgames
			weeks.append(weekinfo)

		season = dygfantasystatsmodel.FantasySeason.get_or_insert_by_values(year)

		for i in range(0, len(weeks)):
			w = weeks[i]

			fantasyweek = dygfantasystatsmodel.FantasyWeek.get_or_insert_by_values(season, i+1)
			fantasyweek.startdate = w['startdate']
			fantasyweek.enddate = w['enddate']
			fantasyweek.put()

			pickem_week = dygfantasystatsmodel.PickEmWeek.get_or_insert_by_values(week=fantasyweek)
			today_date = datetime.date.today()
			if fantasyweek.startdate.date() >= today_date and fantasyweek.startdate.date() < today_date + datetime.timedelta(days=14):
				# make sure we have the correct first_game_datetime.
				saved_first_game_datetime = pickem_week.first_game_datetime
				pickem_week.first_game_datetime = None
				page = dygutil.get_page(None, "http://www.cbssports.com/mlb/schedules/day/%s/regular" % fantasyweek.startdate.strftime("%m%d"))
				soup = BeautifulSoup(page, convertEntities=BeautifulSoup.HTML_ENTITIES)
				time_spans = soup.findAll("span", {'class': "gmtTime"})
				for time_span in time_spans:
					parent_tr = time_span.findParent("tr")
					if len([a for a in parent_tr.findAll("a") if a['href'].startswith("/mlb/teams/schedule/")]) > 0:
						game_datetime = datetime.datetime.fromtimestamp(int(time_span['data-gmt']), tz=dygutil.UTC_tzinfo()).replace(tzinfo=None)
						if pickem_week.first_game_datetime is None or game_datetime < pickem_week.first_game_datetime:
							pickem_week.first_game_datetime = game_datetime
				if not pickem_week.first_game_datetime:
					pickem_week.first_game_datetime = saved_first_game_datetime

			pickem_week.put()

			now_central = datetime.datetime.now().replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)

			week_pickem_matchups = []
			for g in w['games']:
				visitor = g['visitor']
				home = g['home']

				fantasygame = dygfantasystatsmodel.FantasyGame.get_or_insert_by_values(fantasyweek, visitor['team'], home['team'])
				if 'points' in visitor:
					fantasygame.visitorpoints = visitor['points']
				if 'points' in home:
					fantasygame.homepoints = home['points']
				fantasygame.put()

				pickem_matchup = dygfantasystatsmodel.PickEmMatchup.get_or_insert_by_values(game=fantasygame, week=pickem_week)
				pickem_matchup.put()

				week_pickem_matchups.append(pickem_matchup.to_dict())

			#logging.info("week_pickem_matchups=%s" % week_pickem_matchups)
			if now_central.date() <= pickem_week.end_date.date() + datetime.timedelta(days=1):
				pickem_week.matchups = week_pickem_matchups
				pickem_week.put()

		season.startdate = weeks[0]['startdate']
		season.enddate = weeks[len(weeks)-1]['enddate']
		season.put()

	def handle_teamsbyweek(self, year, week):
		if week == 0: return

		fantasyweek = dygfantasystatsmodel.FantasyWeek.all().filter("year = ", year).filter("weeknumber = ", week).get()
		logging.info("year=%s; week=%s" % (year, week))
		assert fantasyweek is not None
		games = dygfantasystatsmodel.FantasyGame.all().filter("year = ", year).filter("week = ", fantasyweek).fetch(1000)

		if len(games) == 0: return

		# homecbsteamid	/ visitorcbsteamid	14 -> homefranchiseteamid	/ visitorfranchiseteamid 28 (was 27)
		# homecbsteamid	/ visitorcbsteamid	7 -> homefranchiseteamid	/ visitorfranchiseteamid 22 (was 15)
		# delete everything with homefranchiseteamid	/ visitorfranchiseteamid of 15 or 27

		totalpoints = 0
		totalweeks = 0
		totalpoints14 = 0
		leadergamesabove500 = 0
		# for each game, need (44 total; 6 new):
		#  home (vs. away) week, season, and career totals as of this week (3)
		#  home (vs. all) season and career totals as of this season (2, 0 unique)
		#  home (vs. all) career totals (1, 0 unique)
		#  home (vs. all) week and season rolling-3 averages as of this season (2)
		#  home (vs. all) season and career per-game averages as of this season (2)
		#  home (vs. all) career per-game averages (1)
		#  home (vs. away) season and career totals as of this season (2)
		#  home (vs. away) career totals (1)
		#  all (vs. away) season and career totals as of this season (2)
		#  all (vs. away) career totals (1)
		#  all (vs. away) week and season rolling-3 averages as of this season (2)
		#  all (vs. away) season and career per-game averages as of this season (2)
		#  all (vs. away) career per-game averages (1)
		#  away (vs. home) week, season, and career totals as of this week (3)
		#  away (vs. all) season and career totals as of this season (2)
		#  away (vs. all) career totals (1)
		#  away (vs. all) week and season rolling-3 averages as of this season (2)
		#  away (vs. all) season and career per-game averages as of this season (2)
		#  away (vs. all) career per-game averages (1)
		#  away (vs. home) season and career totals as of this season (2)
		#  away (vs. home) career totals (1)
		#  all (vs. home) season and career totals as of this season (2)
		#  all (vs. home) career totals (1)
		#  all (vs. home) week and season rolling-3 averages as of this season (2)
		#  all (vs. home) season and career per-game averages as of this season (2)
		#  all (vs. home) career per-game averages (1)
		#
		#  for this method, need:
		#  home, (vs) away, WEEK_SPAN  , WEEK_SPAN  , TOTALS
		#  away, (vs) home, WEEK_SPAN  , WEEK_SPAN  , TOTALS

		season = dygfantasystatsmodel.FantasySeason.get_or_insert_by_values(year)
		teamweek_all = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, None, None, season, fantasyweek)

		median_totalpoints = dygutil.MedianCalculator()
		median_totalpoints14 = dygutil.MedianCalculator()

		for game in games:
			visitorwins = 0.0
			visitorlosses = 0.0
			visitorties = 0.0
			homewins = 0.0
			homelosses = 0.0
			hometies = 0.0

			totalpoints += game.visitorpoints + game.homepoints
			totalweeks += 2
			median_totalpoints.add_entry(game.visitorpoints)
			median_totalpoints.add_entry(game.homepoints)
			median_totalpoints14.add_entry(int(float(game.visitorpoints) * (float(len(games) * 2) / 14.0)))
			median_totalpoints14.add_entry(int(float(game.homepoints) * (float(len(games) * 2) / 14.0)))

			if datetime.date.today() > fantasyweek.enddate.date():
				if game.visitorpoints > game.homepoints:
					visitorwins = 1.0
					homelosses = 1.0
				elif game.visitorpoints < game.homepoints:
					visitorlosses = 1.0
					homewins = 1.0
				else:
					visitorties = 1.0
					hometies = 1.0

				if (homewins - homelosses) > leadergamesabove500:
					leadergamesabove500 = int(homewins - homelosses)
				if (visitorwins - visitorlosses) > leadergamesabove500:
					leadergamesabove500 = int(visitorwins - visitorlosses)

		medianpoints = median_totalpoints.median()
		medianpoints14 = median_totalpoints14.median()
		if len(games) > 0: totalpoints14 = int(float(totalpoints) * (float(len(games) * 2) / 14.0))
		fantasyweek.games = len(games)
		fantasyweek.totalpoints = totalpoints
		fantasyweek.totalpoints14 = totalpoints14
		fantasyweek.mediantotalpoints = medianpoints
		fantasyweek.mediantotalpoints14 = medianpoints14
		fantasyweek.leadergamesabove500 = leadergamesabove500
		fantasyweek.totalweeks = totalweeks
		fantasyweek.put()
		entitylist = []
		for game in games:
			visitorweek = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, game.visitor, game.home, fantasyweek.season, fantasyweek)
			homeweek = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, game.home, game.visitor, fantasyweek.season, fantasyweek)
			if datetime.date.today() > fantasyweek.enddate.date():
				if year < 2009:
					visitorweek.is_final = True
					homeweek.is_final = True
				if game.visitorpoints > game.homepoints:
					visitorweek.wins = 1.0
					visitorweek.losses = 0.0
					visitorweek.ties = 0.0
					homeweek.wins = 0.0
					homeweek.losses = 1.0
					homeweek.ties = 0.0
				elif game.visitorpoints < game.homepoints:
					visitorweek.wins = 0.0
					visitorweek.losses = 1.0
					visitorweek.ties = 0.0
					homeweek.wins = 1.0
					homeweek.losses = 0.0
					homeweek.ties = 0.0
				else:
					visitorweek.wins = 0.0
					visitorweek.losses = 0.0
					visitorweek.ties = 1.0
					homeweek.wins = 0.0
					homeweek.losses = 0.0
					homeweek.ties = 1.0

				def getbreakdown(games, points, team):
					wins = 0.0
					losses = 0.0
					ties = 0.0
					for g in games:
						if g.visitor.franchiseteamid <> team.franchiseteamid:
							if points > g.visitorpoints:
								wins += 1.0
							elif points < g.visitorpoints:
								losses += 1.0
							else:
								ties += 1.0
						if g.home.franchiseteamid <> team.franchiseteamid:
							if points > g.homepoints:
								wins += 1.0
							elif points < g.homepoints:
								losses += 1.0
							else:
								ties += 1.0
					return wins, losses, ties
				visitorweek.breakdownwins, visitorweek.breakdownlosses, visitorweek.breakdownties = getbreakdown(games, game.visitorpoints, game.visitor)
				homeweek.breakdownwins, homeweek.breakdownlosses, homeweek.breakdownties = getbreakdown(games, game.homepoints, game.home)
				visitorweek.vsbreakdownwins = homeweek.breakdownwins
				visitorweek.vsbreakdownlosses = homeweek.breakdownlosses
				visitorweek.vsbreakdownties = homeweek.breakdownties
				homeweek.vsbreakdownwins = visitorweek.breakdownwins
				homeweek.vsbreakdownlosses = visitorweek.breakdownlosses
				homeweek.vsbreakdownties = visitorweek.breakdownties
				if homeweek.breakdownlosses == 0.0:
					homeweek.highpointweeks = 1.0 / (float(homeweek.breakdownties) + 1.0)
				if homeweek.breakdownwins == 0.0:
					homeweek.lowpointweeks = 1.0 / (float(homeweek.breakdownties) + 1.0)
				if visitorweek.breakdownlosses == 0.0:
					visitorweek.highpointweeks = 1.0 / (float(visitorweek.breakdownties) + 1.0)
				if visitorweek.breakdownwins == 0.0:
					visitorweek.lowpointweeks = 1.0 / (float(visitorweek.breakdownties) + 1.0)
				homeweek.vshighpointweeks = visitorweek.highpointweeks
				homeweek.vslowpointweeks = visitorweek.lowpointweeks
				visitorweek.vshighpointweeks = homeweek.highpointweeks
				visitorweek.vslowpointweeks = homeweek.lowpointweeks
			visitorweek.totalpoints = float(game.visitorpoints)
			visitorweek.vstotalpoints = float(game.homepoints)
			visitorweek.totalpoints14 = float(game.visitorpoints) * (float(len(games) * 2) / 14.0)
			visitorweek.vstotalpoints14 = float(game.homepoints) * (float(len(games) * 2) / 14.0)
			visitorweek.league_totalpoints = float(totalpoints)
			visitorweek.league_totalpoints14 = float(totalpoints14)
			visitorweek.league_mediantotalpoints = float(medianpoints)
			visitorweek.league_mediantotalpoints14 = float(medianpoints14)
			visitorweek.leadergamesabove500 = float(leadergamesabove500)
			visitorweek.set_calculated_fields()
			homeweek.totalpoints = float(game.homepoints)
			homeweek.vstotalpoints = float(game.visitorpoints)
			homeweek.totalpoints14 = float(game.homepoints) * (float(len(games) * 2) / 14.0)
			homeweek.vstotalpoints14 = float(game.visitorpoints) * (float(len(games) * 2) / 14.0)
			homeweek.league_totalpoints = float(totalpoints)
			homeweek.league_totalpoints14 = float(totalpoints14)
			homeweek.league_mediantotalpoints = float(medianpoints)
			homeweek.league_mediantotalpoints14 = float(medianpoints14)
			homeweek.leadergamesabove500 = float(leadergamesabove500)
			homeweek.set_calculated_fields()
			entitylist.append(visitorweek)
			entitylist.append(homeweek)

		teamweek_all.stat_fpts = float(totalpoints)
		teamweek_all.totalpoints = float(totalpoints)
		teamweek_all.totalpoints14 = float(totalpoints14)
		teamweek_all.league_totalpoints = teamweek_all.totalpoints
		teamweek_all.league_totalpoints14 = teamweek_all.totalpoints14
		teamweek_all.league_mediantotalpoints = float(medianpoints)
		teamweek_all.league_mediantotalpoints14 = float(medianpoints14)
		teamweek_all.weeks = totalweeks
		teamweek_all.set_calculated_fields()
		entitylist.append(teamweek_all)
		db.put(entitylist)

	def handle_breakdown(self, year, week):
		# get week's stats from FantasyTeamStats and store in memory
		# create/retrieve 13x14 [(teams-1) x teams] BreakdownStats records, update based on FantasyTeamStats
		# totals to be handled in handle_teamtotals, or in potential new handle_breakdowntotals method
		if week == 0: return
		fantasyweek = dygfantasystatsmodel.FantasyWeek.all().filter("year = ", year).filter("weeknumber = ", week).get()
		assert fantasyweek is not None
		weekstats = dygfantasystatsmodel.FantasyTeamStats.all().filter("week = ", fantasyweek).fetch(1000)

		def do_breakdown(teamweekstats, weekstats, fantasyweek):
			for ws in weekstats:
				if ws.grouping == teamweekstats.grouping and ws.franchiseteamid <> teamweekstats.franchiseteamid:
					wins = 0.0
					losses = 0.0
					ties = 0.0
					breakdownwins = 0.0
					breakdownlosses = 0.0
					breakdownties = 0.0
					if teamweekstats.totalpoints > ws.totalpoints:
						breakdownwins = 1.0
						if ws.vsfranchiseteamid == teamweekstats.franchiseteamid:
							wins = 1.0
					elif teamweekstats.totalpoints < ws.totalpoints:
						breakdownlosses = 1.0
						if ws.vsfranchiseteamid == teamweekstats.franchiseteamid:
							losses = 1.0
					elif teamweekstats.totalpoints == ws.totalpoints:
						breakdownties = 1.0
						if ws.vsfranchiseteamid == teamweekstats.franchiseteamid:
							ties = 1.0
					bd = dygfantasystatsmodel.BreakdownStats.get_or_insert_by_values(dygfantasystatsmodel.BreakdownStats.WEEK_SPAN, dygfantasystatsmodel.BreakdownStats.WEEK_SPAN, teamweekstats.fantasyteam, ws.fantasyteam, fantasyweek.season, fantasyweek, teamweekstats.grouping)
					bd.weeklystats = teamweekstats
					bd.vsweeklystats = ws
					bd.wins = wins
					bd.losses = losses
					bd.ties = ties
					bd.breakdownwins = breakdownwins
					bd.breakdownlosses = breakdownlosses
					bd.breakdownties = breakdownties
					bd.put()
		for ws in weekstats:
			do_breakdown(ws, weekstats, fantasyweek)

	def handle_lineups(self, week=1, teamnumber=1):
		if week == 0: return
		year = self.get_current_year()
		fantasyweek = dygfantasystatsmodel.FantasyWeek.all().filter("year = ", year).filter("weeknumber = ", week).get()
		assert fantasyweek is not None
		cookie = get_cookie()

		teams = []
		t = self.getdbteam(teamnumber, year)
		if t == None: return
		if t.cbsteamid == 0: return

		teaminfo = {}
		teaminfo['fantasyteam'] = t

		page = dygutil.get_page(cookie, 'http://dyg.baseball.cbssports.com/teams/page/' + str(t.cbsteamid) + '/' + str(week) + '/')
		table_start_token = '<div id="lineup_views"><table '
		table_end_token = '</table></div>'

		page = page[page.find(table_start_token):]
		page = page[:page.find(table_end_token)]

		rows = page.split('<tr')

		players = []
		for row in rows:
			token = "/players/playerpage/"
			if row.find(token) > 0:
				player = {}

				ptr = row.find('<td ')
				s = row[ptr:]
				s = s[s.find('>') + 1:]
				anchor_start_token = '<a href="#" class="changePos">'
				anchor_end_token = '</a>'
				ptr1 = s.find(anchor_start_token)
				ptr2 = s.find(anchor_end_token)
				if ptr1 > 0:
					s = s[:ptr1] + s[ptr1+len(anchor_start_token):ptr2] + s[ptr2+len(anchor_end_token):]

				ptr = s.find('<')
				pos_status = s[:ptr]
				if pos_status.find("(") < 0:
					player['Status'] = "A"
					player['Pos'] = pos_status
				else:
					player['Status'] = pos_status[0]
					if player['Status'] == "B": player['Status'] = "RS"
					if player['Status'] == "M": player['Status'] = "ML"
					player['Pos'] = pos_status[pos_status.find('(')+1:-1]

				ptr = s.find(token) + len(token)
				p = s[ptr:]
				ptr = p.find('\'>')
				player['cbsplayerid'] = int(p[:ptr])
				s = p[ptr + 2:]
				ptr = s.find('<')
				playername = s[:ptr]
				parts = playername.split(' ')
				if len(parts) < 2:
					logging.info("row=%s" % row)
					logging.info("parts=%s" % parts)
				player['firstname'] = parts[0]
				player['lastname'] = parts[1]

				s = s[ptr:]
				s = s[s.find('>') + 1:].strip()
				s = s[s.find('>') + 1:].strip()
				ptr = s.find('<')
				if ptr > 0:
					posteam = s[:ptr]
				else:
					posteam = s
				posteam = posteam.replace('&nbsp;', ' ').strip()
				parts = posteam.split(' | ')
				if len(parts) < 2:
					logging.info("row=%s" % row)
					logging.info("posteam=%s" % posteam)
					logging.info("parts=%s" % parts)
				player['primaryposition'] = parts[0]
				player['mlbteamcode'] = parts[1]
				if not player['mlbteamcode']:
					logging.warning("No mlbteamcode; row=%s" % row)

				if player['primaryposition'] == 'LF' or player['primaryposition'] == 'CF' or player['primaryposition'] == 'RF':
					player['primaryposition'] = "OF"

				players.append(player)
		teaminfo['players'] = players
		teams.append(teaminfo)

		for team in teams:
			fantasyteam = team['fantasyteam']
			teamweek = dygfantasystatsmodel.FantasyTeamStats.all().filter("timespanvalue = ", dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN).filter("runningtotaltimespanvalue = ", dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN).filter("statstype = ", dygfantasystatsmodel.FantasyTeamStats.TOTALS).filter("fantasyteam = ", fantasyteam).filter("year = ", year).filter("weeknumber = ", week).filter("grouping = ", 'ALL').fetch(1)[0]
			for player in team['players']:
				assert player['mlbteamcode'] is not None and player['mlbteamcode'].strip() != ""
				fantasyplayer = dygfantasystatsmodel.FantasyPlayer.get_or_insert_by_values(player['cbsplayerid'])
				fantasyplayer.firstname = player['firstname']
				fantasyplayer.lastname = player['lastname']
				fantasyplayer.primaryposition = player['primaryposition']
				fantasyplayer.mlbteamcode = player['mlbteamcode']
				#if fantasyplayer.fantasyteam == None: fantasyplayer.fantasyteam = fantasyteam
				fantasyplayer.put()
				playerstats = dygfantasystatsmodel.FantasyPlayerStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyPlayerStats.WEEK_SPAN, dygfantasystatsmodel.FantasyPlayerStats.WEEK_SPAN, dygfantasystatsmodel.FantasyPlayerStats.TOTALS, fantasyplayer, fantasyweek.season, fantasyweek)
				playerstats.fantasyteam = fantasyteam
				playerstats.vsfantasyteam = teamweek.vsfantasyteam
				playerstats.positioncode = player['Pos']
				playerstats.lineupstatus = player['Status']
				playerstats.put()

	def do_weeklyteamstats_leaguetotals(self, season, fantasyweek):
		#entitylist = dygfantasystatsmodel.FantasyTeamStats.all().filter("timespanvalue = ", dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN).filter("runningtotaltimespanvalue = ", dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN).filter("statstype = ", dygfantasystatsmodel.FantasyTeamStats.TOTALS).filter("year = ", year).filter("weeknumber = ", week).fetch(1000)
		total_pitchingtotals = {}
		total_pitchingtotals_sp = {}
		total_pitchingtotals_rp = {}
		total_hittingtotals = {}
		total_hittingtotals_c = {}
		total_hittingtotals_1b = {}
		total_hittingtotals_2b = {}
		total_hittingtotals_3b = {}
		total_hittingtotals_ss = {}
		total_hittingtotals_of = {}
		total_hittingtotals_dh = {}

		median_hittingpoints_c = dygutil.MedianCalculator()
		median_hittingpoints_1b = dygutil.MedianCalculator()
		median_hittingpoints_2b = dygutil.MedianCalculator()
		median_hittingpoints_3b = dygutil.MedianCalculator()
		median_hittingpoints_ss = dygutil.MedianCalculator()
		median_hittingpoints_of = dygutil.MedianCalculator()
		median_hittingpoints_dh = dygutil.MedianCalculator()
		median_hittingpoints = dygutil.MedianCalculator()
		median_hittingpoints14 = dygutil.MedianCalculator()
		median_pitchingpoints_rp = dygutil.MedianCalculator()
		median_pitchingpoints_old_rp = dygutil.MedianCalculator()
		median_pitchingpoints_sp = dygutil.MedianCalculator()
		median_pitchingpoints_old_sp = dygutil.MedianCalculator()
		median_pitchingpoints_per_start_sp = dygutil.MedianCalculator()
		median_pitchingpoints_per_start_old_sp = dygutil.MedianCalculator()
		median_pitchingpoints = dygutil.MedianCalculator()
		median_pitchingpoints14 = dygutil.MedianCalculator()
		median_pitchingpoints_old = dygutil.MedianCalculator()
		median_pitchingpoints14_old = dygutil.MedianCalculator()
		median_totalpoints = dygutil.MedianCalculator()
		median_totalpoints14 = dygutil.MedianCalculator()
		median_totalpoints_old = dygutil.MedianCalculator()
		median_totalpoints14_old = dygutil.MedianCalculator()

		teamstats = []
		fantasyplayerstats = dygfantasystatsmodel.FantasyPlayerStats.all().filter("timespanvalue = ", dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN).filter("runningtotaltimespanvalue = ", dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN).filter("statstype = ", dygfantasystatsmodel.FantasyTeamStats.TOTALS).filter("year = ", season.year).filter("weeknumber = ", fantasyweek.weeknumber).fetch(1000)
		fantasyplayerstats = [s for s in fantasyplayerstats if s.lineupstatus == "A"]
		fantasyteams = dygfantasystatsmodel.FantasyTeam.all().filter("year = ", season.year).fetch(1000)
		for t in fantasyteams:
			if t.cbsteamid == 0: continue

			teamweek = dygfantasystatsmodel.FantasyTeamStats.all().filter("timespanvalue = ", dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN).filter("runningtotaltimespanvalue = ", dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN).filter("statstype = ", dygfantasystatsmodel.FantasyTeamStats.TOTALS).filter("fantasyteam = ", t).filter("year = ", season.year).filter("weeknumber = ", fantasyweek.weeknumber).filter("grouping = ", 'ALL').fetch(1)[0]
			teamweek_c = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, 'C')
			teamweek_1b = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, '1B')
			teamweek_2b = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, '2B')
			teamweek_3b = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, '3B')
			teamweek_ss = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, 'SS')
			teamweek_of = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, 'OF')
			teamweek_dh = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, 'DH')
			teamweek_hitters = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, 'HITTERS')
			teamweek_rp = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, 'RP')
			teamweek_sp = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, 'SP')
			teamweek_pitchers = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, 'PITCHERS')

			teamstats.append(teamweek)
			teamstats.append(teamweek_c)
			teamstats.append(teamweek_1b)
			teamstats.append(teamweek_2b)
			teamstats.append(teamweek_3b)
			teamstats.append(teamweek_ss)
			teamstats.append(teamweek_of)
			teamstats.append(teamweek_dh)
			teamstats.append(teamweek_hitters)
			teamstats.append(teamweek_rp)
			teamstats.append(teamweek_sp)
			teamstats.append(teamweek_pitchers)

			team_pitchingtotals = {}
			self.get_pitcher_stats(teamweek_pitchers, team_pitchingtotals)
			team_pitchingtotals_sp = {}
			self.get_pitcher_stats(teamweek_sp, team_pitchingtotals_sp)
			team_pitchingtotals_sp['GS'] = teamweek_sp.pitchingstarts
			team_pitchingtotals_rp = {}
			self.get_pitcher_stats(teamweek_rp, team_pitchingtotals_rp)
			team_hittingtotals = {}
			self.get_hitter_stats(teamweek_hitters, team_hittingtotals)
			team_hittingtotals_c = {}
			self.get_hitter_stats(teamweek_c, team_hittingtotals_c)
			team_hittingtotals_1b = {}
			self.get_hitter_stats(teamweek_1b, team_hittingtotals_1b)
			team_hittingtotals_2b = {}
			self.get_hitter_stats(teamweek_2b, team_hittingtotals_2b)
			team_hittingtotals_3b = {}
			self.get_hitter_stats(teamweek_3b, team_hittingtotals_3b)
			team_hittingtotals_ss = {}
			self.get_hitter_stats(teamweek_ss, team_hittingtotals_ss)
			team_hittingtotals_of = {}
			self.get_hitter_stats(teamweek_of, team_hittingtotals_of)
			team_hittingtotals_dh = {}
			self.get_hitter_stats(teamweek_dh, team_hittingtotals_dh)

			self.add_to_totals(team_hittingtotals_c, total_hittingtotals_c)
			self.add_to_totals(team_hittingtotals_1b, total_hittingtotals_1b)
			self.add_to_totals(team_hittingtotals_2b, total_hittingtotals_2b)
			self.add_to_totals(team_hittingtotals_3b, total_hittingtotals_3b)
			self.add_to_totals(team_hittingtotals_ss, total_hittingtotals_ss)
			self.add_to_totals(team_hittingtotals_of, total_hittingtotals_of)
			self.add_to_totals(team_hittingtotals_dh, total_hittingtotals_dh)
			self.add_to_totals(team_hittingtotals, total_hittingtotals)
			self.add_to_totals(team_pitchingtotals_rp, total_pitchingtotals_rp)
			self.add_to_totals(team_pitchingtotals_sp, total_pitchingtotals_sp)
			self.add_to_totals(team_pitchingtotals, total_pitchingtotals)

			median_hittingpoints_c.add_entry(team_hittingtotals_c['FPTS'])
			median_hittingpoints_1b.add_entry(team_hittingtotals_1b['FPTS'])
			median_hittingpoints_2b.add_entry(team_hittingtotals_2b['FPTS'])
			median_hittingpoints_3b.add_entry(team_hittingtotals_3b['FPTS'])
			median_hittingpoints_ss.add_entry(team_hittingtotals_ss['FPTS'])
			median_hittingpoints_of.add_entry(team_hittingtotals_of['FPTS'])
			median_hittingpoints_dh.add_entry(team_hittingtotals_dh['FPTS'])
			median_hittingpoints.add_entry(team_hittingtotals['FPTS'])
			median_hittingpoints14.add_entry(team_hittingtotals['FPTS'] * (float(len(fantasyteams)) / 14.0))
			median_pitchingpoints_rp.add_entry(team_pitchingtotals_rp['FPTS'])
			median_pitchingpoints_old_rp.add_entry(team_pitchingtotals_rp['FPTS_OLD'])
			median_pitchingpoints_sp.add_entry(team_pitchingtotals_sp['FPTS'])
			median_pitchingpoints_old_sp.add_entry(team_pitchingtotals_sp['FPTS_OLD'])
			if team_pitchingtotals_sp['GS'] > 0:
				median_pitchingpoints_per_start_sp.add_entry(team_pitchingtotals_sp['FPTS'] / team_pitchingtotals_sp['GS'])
				median_pitchingpoints_per_start_old_sp.add_entry(team_pitchingtotals_sp['FPTS_OLD'] / team_pitchingtotals_sp['GS'])
			else:
				median_pitchingpoints_per_start_sp.add_entry(0.0)
				median_pitchingpoints_per_start_old_sp.add_entry(0.0)
			median_pitchingpoints.add_entry(team_pitchingtotals['FPTS'])
			median_pitchingpoints_old.add_entry(team_pitchingtotals['FPTS_OLD'])
			median_pitchingpoints14.add_entry(team_pitchingtotals['FPTS'] * (float(len(fantasyteams)) / 14.0))
			median_pitchingpoints14_old.add_entry(team_pitchingtotals['FPTS_OLD'] * (float(len(fantasyteams)) / 14.0))
			median_totalpoints.add_entry(team_pitchingtotals['FPTS'] + team_hittingtotals['FPTS'])
			median_totalpoints_old.add_entry(team_pitchingtotals['FPTS_OLD'] + team_hittingtotals['FPTS'])
			median_totalpoints14.add_entry(team_pitchingtotals['FPTS'] * (float(len(fantasyteams)) / 14.0))
			median_totalpoints14_old.add_entry(team_pitchingtotals['FPTS_OLD'] * (float(len(fantasyteams)) / 14.0))

		teamweek_all = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, None, None, season, fantasyweek)
		teamweek_all_c = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, None, None, season, fantasyweek, 'C')
		teamweek_all_1b = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, None, None, season, fantasyweek, '1B')
		teamweek_all_2b = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, None, None, season, fantasyweek, '2B')
		teamweek_all_3b = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, None, None, season, fantasyweek, '3B')
		teamweek_all_ss = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, None, None, season, fantasyweek, 'SS')
		teamweek_all_of = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, None, None, season, fantasyweek, 'OF')
		teamweek_all_dh = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, None, None, season, fantasyweek, 'DH')
		teamweek_all_rp = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, None, None, season, fantasyweek, 'RP')
		teamweek_all_sp = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, None, None, season, fantasyweek, 'SP')

		self.set_hitter_stats(teamweek_all_c, total_hittingtotals_c)
		teamweek_all_c.totalpoints = teamweek_all_c.stat_fpts
		teamweek_all_c.totalpoints_old = teamweek_all_c.stat_fpts_old
		teamweek_all_c.league_hittingpoints = teamweek_all_c.hittingpoints
		teamweek_all_c.league_hittingpoints_old = teamweek_all_c.hittingpoints_old
		teamweek_all_c.league_totalpoints = teamweek_all_c.totalpoints
		teamweek_all_c.league_totalpoints_old = teamweek_all_c.totalpoints_old
		teamweek_all_c.league_medianhittingpoints = median_hittingpoints_c.median()
		teamweek_all_c.league_medianhittingpoints_old = median_hittingpoints_c.median()
		teamweek_all_c.league_mediantotalpoints = median_hittingpoints_c.median()
		teamweek_all_c.league_mediantotalpoints_old = median_hittingpoints_c.median()
		teamweek_all_c.set_calculated_fields()
		teamstats.append(teamweek_all_c)

		self.set_hitter_stats(teamweek_all_1b, total_hittingtotals_1b)
		teamweek_all_1b.totalpoints = teamweek_all_1b.stat_fpts
		teamweek_all_1b.totalpoints_old = teamweek_all_1b.stat_fpts_old
		teamweek_all_1b.league_hittingpoints = teamweek_all_1b.hittingpoints
		teamweek_all_1b.league_hittingpoints_old = teamweek_all_1b.hittingpoints_old
		teamweek_all_1b.league_totalpoints = teamweek_all_1b.totalpoints
		teamweek_all_1b.league_totalpoints_old = teamweek_all_1b.totalpoints_old
		teamweek_all_1b.league_medianhittingpoints = median_hittingpoints_1b.median()
		teamweek_all_1b.league_medianhittingpoints_old = median_hittingpoints_1b.median()
		teamweek_all_1b.league_mediantotalpoints = median_hittingpoints_1b.median()
		teamweek_all_1b.league_mediantotalpoints_old = median_hittingpoints_1b.median()
		teamweek_all_1b.set_calculated_fields()
		teamstats.append(teamweek_all_1b)

		self.set_hitter_stats(teamweek_all_2b, total_hittingtotals_2b)
		teamweek_all_2b.totalpoints = teamweek_all_2b.stat_fpts
		teamweek_all_2b.totalpoints_old = teamweek_all_2b.stat_fpts_old
		teamweek_all_2b.league_hittingpoints = teamweek_all_2b.hittingpoints
		teamweek_all_2b.league_hittingpoints_old = teamweek_all_2b.hittingpoints_old
		teamweek_all_2b.league_totalpoints = teamweek_all_2b.totalpoints
		teamweek_all_2b.league_totalpoints_old = teamweek_all_2b.totalpoints_old
		teamweek_all_2b.league_medianhittingpoints = median_hittingpoints_2b.median()
		teamweek_all_2b.league_medianhittingpoints_old = median_hittingpoints_2b.median()
		teamweek_all_2b.league_mediantotalpoints = median_hittingpoints_2b.median()
		teamweek_all_2b.league_mediantotalpoints_old = median_hittingpoints_2b.median()
		teamweek_all_2b.set_calculated_fields()
		teamstats.append(teamweek_all_2b)

		self.set_hitter_stats(teamweek_all_3b, total_hittingtotals_3b)
		teamweek_all_3b.totalpoints = teamweek_all_3b.stat_fpts
		teamweek_all_3b.totalpoints_old = teamweek_all_3b.stat_fpts_old
		teamweek_all_3b.league_hittingpoints = teamweek_all_3b.hittingpoints
		teamweek_all_3b.league_hittingpoints_old = teamweek_all_3b.hittingpoints_old
		teamweek_all_3b.league_totalpoints = teamweek_all_3b.totalpoints
		teamweek_all_3b.league_totalpoints_old = teamweek_all_3b.totalpoints_old
		teamweek_all_3b.league_medianhittingpoints = median_hittingpoints_3b.median()
		teamweek_all_3b.league_medianhittingpoints_old = median_hittingpoints_3b.median()
		teamweek_all_3b.league_mediantotalpoints = median_hittingpoints_3b.median()
		teamweek_all_3b.league_mediantotalpoints_old = median_hittingpoints_3b.median()
		teamweek_all_3b.set_calculated_fields()
		teamstats.append(teamweek_all_3b)

		self.set_hitter_stats(teamweek_all_ss, total_hittingtotals_ss)
		teamweek_all_ss.totalpoints = teamweek_all_ss.stat_fpts
		teamweek_all_ss.totalpoints_old = teamweek_all_ss.stat_fpts_old
		teamweek_all_ss.league_hittingpoints = teamweek_all_ss.hittingpoints
		teamweek_all_ss.league_hittingpoints_old = teamweek_all_ss.hittingpoints_old
		teamweek_all_ss.league_totalpoints = teamweek_all_ss.totalpoints
		teamweek_all_ss.league_totalpoints_old = teamweek_all_ss.totalpoints_old
		teamweek_all_ss.league_medianhittingpoints = median_hittingpoints_ss.median()
		teamweek_all_ss.league_medianhittingpoints_old = median_hittingpoints_ss.median()
		teamweek_all_ss.league_mediantotalpoints = median_hittingpoints_ss.median()
		teamweek_all_ss.league_mediantotalpoints_old = median_hittingpoints_ss.median()
		teamweek_all_ss.set_calculated_fields()
		teamstats.append(teamweek_all_ss)

		self.set_hitter_stats(teamweek_all_of, total_hittingtotals_of)
		teamweek_all_of.totalpoints = teamweek_all_of.stat_fpts
		teamweek_all_of.totalpoints_old = teamweek_all_of.stat_fpts_old
		teamweek_all_of.league_hittingpoints = teamweek_all_of.hittingpoints
		teamweek_all_of.league_hittingpoints_old = teamweek_all_of.hittingpoints_old
		teamweek_all_of.league_totalpoints = teamweek_all_of.totalpoints
		teamweek_all_of.league_totalpoints_old = teamweek_all_of.totalpoints_old
		teamweek_all_of.league_medianhittingpoints = median_hittingpoints_of.median()
		teamweek_all_of.league_medianhittingpoints_old = median_hittingpoints_of.median()
		teamweek_all_of.league_mediantotalpoints = median_hittingpoints_of.median()
		teamweek_all_of.league_mediantotalpoints_old = median_hittingpoints_of.median()
		teamweek_all_of.set_calculated_fields()
		teamstats.append(teamweek_all_of)

		self.set_hitter_stats(teamweek_all_dh, total_hittingtotals_dh)
		teamweek_all_dh.totalpoints = teamweek_all_dh.stat_fpts
		teamweek_all_dh.totalpoints_old = teamweek_all_dh.stat_fpts_old
		teamweek_all_dh.league_hittingpoints = teamweek_all_dh.hittingpoints
		teamweek_all_dh.league_hittingpoints_old = teamweek_all_dh.hittingpoints_old
		teamweek_all_dh.league_totalpoints = teamweek_all_dh.totalpoints
		teamweek_all_dh.league_totalpoints_old = teamweek_all_dh.totalpoints_old
		teamweek_all_dh.league_medianhittingpoints = median_hittingpoints_dh.median()
		teamweek_all_dh.league_medianhittingpoints_old = median_hittingpoints_dh.median()
		teamweek_all_dh.league_mediantotalpoints = median_hittingpoints_dh.median()
		teamweek_all_dh.league_mediantotalpoints_old = median_hittingpoints_dh.median()
		teamweek_all_dh.set_calculated_fields()
		teamstats.append(teamweek_all_dh)

		self.set_pitcher_stats(teamweek_all_rp, total_pitchingtotals_rp)
		teamweek_all_rp.totalpoints = teamweek_all_rp.stat_fpts
		teamweek_all_rp.totalpoints_old = teamweek_all_rp.stat_fpts_old
		teamweek_all_rp.league_pitchingpoints = teamweek_all_rp.pitchingpoints
		teamweek_all_rp.league_pitchingpoints_old = teamweek_all_rp.pitchingpoints_old
		teamweek_all_rp.league_startingpitchingpoints = teamweek_all_rp.startingpitchingpoints
		teamweek_all_rp.league_startingpitchingpoints_old = teamweek_all_rp.startingpitchingpoints_old
		teamweek_all_rp.league_totalpoints = teamweek_all_rp.totalpoints
		teamweek_all_rp.league_totalpoints_old = teamweek_all_rp.totalpoints_old
		teamweek_all_rp.league_medianpitchingpoints = median_pitchingpoints_rp.median()
		teamweek_all_rp.league_medianpitchingpoints_old = median_pitchingpoints_old_rp.median()
		teamweek_all_rp.league_mediantotalpoints = median_pitchingpoints_rp.median()
		teamweek_all_rp.league_mediantotalpoints_old = median_pitchingpoints_old_rp.median()
		teamweek_all_rp.set_calculated_fields()
		teamstats.append(teamweek_all_rp)

		self.set_pitcher_stats(teamweek_all_sp, total_pitchingtotals_sp)
		teamweek_all_sp.totalpoints = teamweek_all_sp.stat_fpts
		teamweek_all_sp.totalpoints_old = teamweek_all_sp.stat_fpts_old
		teamweek_all_sp.league_pitchingpoints = teamweek_all_sp.pitchingpoints
		teamweek_all_sp.league_pitchingpoints_old = teamweek_all_sp.pitchingpoints_old
		teamweek_all_sp.league_startingpitchingpoints = teamweek_all_sp.startingpitchingpoints
		teamweek_all_sp.league_startingpitchingpoints_old = teamweek_all_sp.startingpitchingpoints_old
		teamweek_all_sp.league_startingpitchingpointsperstart = teamweek_all_sp.pointsperpitchingstart
		teamweek_all_sp.league_startingpitchingpointsperstart_old = teamweek_all_sp.pointsperpitchingstart_old
		teamweek_all_sp.league_totalpoints = teamweek_all_sp.totalpoints
		teamweek_all_sp.league_totalpoints_old = teamweek_all_sp.totalpoints_old
		teamweek_all_sp.league_medianpitchingpoints = median_pitchingpoints_sp.median()
		teamweek_all_sp.league_medianpitchingpoints_old = median_pitchingpoints_old_sp.median()
		teamweek_all_sp.league_medianstartingpitchingpoints = median_pitchingpoints_sp.median()
		teamweek_all_sp.league_medianstartingpitchingpoints_old = median_pitchingpoints_old_sp.median()
		teamweek_all_sp.league_medianstartingpitchingpointsperstart = median_pitchingpoints_per_start_sp.median()
		teamweek_all_sp.league_medianstartingpitchingpointsperstart_old = median_pitchingpoints_per_start_old_sp.median()
		teamweek_all_sp.league_mediantotalpoints = median_pitchingpoints_sp.median()
		teamweek_all_sp.league_mediantotalpoints_old = median_pitchingpoints_old_sp.median()
		teamweek_all_sp.pitchingstarts = total_pitchingtotals_sp['GS']
		teamweek_all_sp.set_calculated_fields()
		teamstats.append(teamweek_all_sp)

		self.set_hitter_stats(teamweek_all, total_hittingtotals)
		self.set_pitcher_stats(teamweek_all, total_pitchingtotals)
		teamweek_all.stat_fpts = teamweek_all.hittingpoints + teamweek_all.pitchingpoints
		teamweek_all.stat_fpts_old = teamweek_all.hittingpoints+ teamweek_all_rp.stat_fpts_old + teamweek_all_sp.stat_fpts_old
		teamweek_all.totalpoints = teamweek_all.stat_fpts
		teamweek_all.totalpoints14 = teamweek_all.totalpoints * (float(len(fantasyteams)) / 14.0)
		teamweek_all.totalpoints_old = teamweek_all.stat_fpts_old
		teamweek_all.totalpoints14_old = teamweek_all.totalpoints_old * (float(len(fantasyteams)) / 14.0)
		teamweek_all.league_hittingpoints = teamweek_all.hittingpoints
		teamweek_all.league_hittingpoints_old = teamweek_all.hittingpoints_old
		teamweek_all.league_hittingpoints14 = teamweek_all.hittingpoints14
		teamweek_all.league_hittingpoints14_old = teamweek_all.hittingpoints14_old
		teamweek_all.league_pitchingpoints = teamweek_all.pitchingpoints
		teamweek_all.league_pitchingpoints_old = teamweek_all.pitchingpoints_old
		teamweek_all.league_pitchingpoints14 = teamweek_all.pitchingpoints14
		teamweek_all.league_pitchingpoints14_old = teamweek_all.pitchingpoints14_old
		teamweek_all.league_startingpitchingpoints = teamweek_all.startingpitchingpoints
		teamweek_all.league_startingpitchingpoints_old = teamweek_all.startingpitchingpoints_old
		teamweek_all.league_startingpitchingpointsperstart = teamweek_all.pointsperpitchingstart
		teamweek_all.league_startingpitchingpointsperstart_old = teamweek_all.pointsperpitchingstart_old
		teamweek_all.league_totalpoints = teamweek_all.totalpoints
		teamweek_all.league_totalpoints_old = teamweek_all.totalpoints_old
		teamweek_all.league_totalpoints14 = teamweek_all.totalpoints14
		teamweek_all.league_totalpoints14_old = teamweek_all.totalpoints14_old
		teamweek_all.league_medianhittingpoints = median_hittingpoints.median()
		teamweek_all.league_medianhittingpoints_old = median_hittingpoints.median()
		teamweek_all.league_medianhittingpoints14 = median_hittingpoints14.median()
		teamweek_all.league_medianhittingpoints14_old = median_hittingpoints14.median()
		teamweek_all.league_medianpitchingpoints = median_pitchingpoints.median()
		teamweek_all.league_medianpitchingpoints_old = median_pitchingpoints_old.median()
		teamweek_all.league_medianpitchingpoints14 = median_pitchingpoints14.median()
		teamweek_all.league_medianpitchingpoints14_old = median_pitchingpoints14_old.median()
		teamweek_all.league_medianstartingpitchingpoints = median_pitchingpoints_sp.median()
		teamweek_all.league_medianstartingpitchingpoints_old = median_pitchingpoints_old_sp.median()
		teamweek_all.league_medianstartingpitchingpointsperstart = median_pitchingpoints_per_start_sp.median()
		teamweek_all.league_medianstartingpitchingpointsperstart_old = median_pitchingpoints_per_start_old_sp.median()
		teamweek_all.league_mediantotalpoints = median_totalpoints.median()
		teamweek_all.league_mediantotalpoints_old = median_totalpoints_old.median()
		teamweek_all.league_mediantotalpoints14 = median_totalpoints14.median()
		teamweek_all.league_mediantotalpoints14_old = median_totalpoints14_old.median()
		teamweek_all.pitchingstarts = total_pitchingtotals_sp['GS']
		teamweek_all.set_calculated_fields()
		teamstats.append(teamweek_all)

		entitylist = []
		for i in range(0, len(teamstats)):
			if teamstats[i].grouping == 'ALL':
				teamstats[i].league_hittingpoints = total_hittingtotals['FPTS']
				teamstats[i].league_hittingpoints_old = total_hittingtotals['FPTS']
				teamstats[i].league_pitchingpoints = total_pitchingtotals['FPTS']
				teamstats[i].league_pitchingpoints_old = total_pitchingtotals['FPTS_OLD']
				teamstats[i].league_totalpoints = total_hittingtotals['FPTS'] + total_pitchingtotals['FPTS']
				teamstats[i].league_totalpoints_old = total_hittingtotals['FPTS'] + total_pitchingtotals['FPTS_OLD']
				teamstats[i].league_startingpitchingpoints = float(total_pitchingtotals_sp['FPTS'])
				teamstats[i].league_startingpitchingpoints_old = float(total_pitchingtotals_sp['FPTS_OLD'])
				teamstats[i].league_medianhittingpoints = median_hittingpoints.median()
				teamstats[i].league_medianhittingpoints_old = median_hittingpoints.median()
				teamstats[i].league_medianhittingpoints14 = median_hittingpoints14.median()
				teamstats[i].league_medianhittingpoints14_old = median_hittingpoints14.median()
				teamstats[i].league_medianpitchingpoints = median_pitchingpoints.median()
				teamstats[i].league_medianpitchingpoints_old = median_pitchingpoints_old.median()
				teamstats[i].league_medianpitchingpoints14 = median_pitchingpoints14.median()
				teamstats[i].league_medianpitchingpoints14_old = median_pitchingpoints14_old.median()
				teamstats[i].league_medianstartingpitchingpoints = median_pitchingpoints_sp.median()
				teamstats[i].league_medianstartingpitchingpoints_old = median_pitchingpoints_old_sp.median()
				teamstats[i].league_medianstartingpitchingpointsperstart = median_pitchingpoints_per_start_sp.median()
				teamstats[i].league_mediantotalpoints = median_totalpoints.median()
				teamstats[i].league_mediantotalpoints_old = median_totalpoints_old.median()
				teamstats[i].league_mediantotalpoints14 = median_totalpoints14.median()
				teamstats[i].league_mediantotalpoints14_old = median_totalpoints14_old.median()
			elif teamstats[i].grouping == 'C':
				teamstats[i].league_totalpoints = total_hittingtotals_c['FPTS']
				teamstats[i].league_totalpoints_old = total_hittingtotals_c['FPTS']
				teamstats[i].league_mediantotalpoints = median_hittingpoints_c.median()
				teamstats[i].league_mediantotalpoints_old = median_hittingpoints_c.median()
			elif teamstats[i].grouping == '1B':
				teamstats[i].league_totalpoints = total_hittingtotals_1b['FPTS']
				teamstats[i].league_totalpoints_old = total_hittingtotals_1b['FPTS']
				teamstats[i].league_mediantotalpoints = median_hittingpoints_1b.median()
				teamstats[i].league_mediantotalpoints_old = median_hittingpoints_1b.median()
			elif teamstats[i].grouping == '2B':
				teamstats[i].league_totalpoints = total_hittingtotals_2b['FPTS']
				teamstats[i].league_totalpoints_old = total_hittingtotals_2b['FPTS']
				teamstats[i].league_mediantotalpoints = median_hittingpoints_2b.median()
				teamstats[i].league_mediantotalpoints_old = median_hittingpoints_2b.median()
			elif teamstats[i].grouping == '3B':
				teamstats[i].league_totalpoints = total_hittingtotals_3b['FPTS']
				teamstats[i].league_totalpoints_old = total_hittingtotals_3b['FPTS']
				teamstats[i].league_mediantotalpoints = median_hittingpoints_3b.median()
				teamstats[i].league_mediantotalpoints_old = median_hittingpoints_3b.median()
			elif teamstats[i].grouping == 'SS':
				teamstats[i].league_totalpoints = total_hittingtotals_ss['FPTS']
				teamstats[i].league_totalpoints_old = total_hittingtotals_ss['FPTS']
				teamstats[i].league_mediantotalpoints = median_hittingpoints_ss.median()
				teamstats[i].league_mediantotalpoints_old = median_hittingpoints_ss.median()
			elif teamstats[i].grouping == 'OF':
				teamstats[i].league_totalpoints = total_hittingtotals_of['FPTS']
				teamstats[i].league_totalpoints_old = total_hittingtotals_of['FPTS']
				teamstats[i].league_mediantotalpoints = median_hittingpoints_of.median()
				teamstats[i].league_mediantotalpoints_old = median_hittingpoints_of.median()
			elif teamstats[i].grouping == 'DH':
				teamstats[i].league_totalpoints = total_hittingtotals_dh['FPTS']
				teamstats[i].league_totalpoints_old = total_hittingtotals_dh['FPTS']
				teamstats[i].league_mediantotalpoints = median_hittingpoints_dh.median()
				teamstats[i].league_mediantotalpoints_old = median_hittingpoints_dh.median()
			elif teamstats[i].grouping == 'RP':
				teamstats[i].league_totalpoints = total_pitchingtotals_rp['FPTS']
				teamstats[i].league_totalpoints_old = total_pitchingtotals_rp['FPTS_OLD']
				teamstats[i].league_mediantotalpoints = median_pitchingpoints_rp.median()
				teamstats[i].league_mediantotalpoints_old = median_pitchingpoints_old_rp.median()
			elif teamstats[i].grouping == 'SP':
				teamstats[i].league_totalpoints = total_pitchingtotals_sp['FPTS']
				teamstats[i].league_totalpoints_old = total_pitchingtotals_sp['FPTS_OLD']
				teamstats[i].league_mediantotalpoints = median_pitchingpoints_sp.median()
				teamstats[i].league_mediantotalpoints_old = median_pitchingpoints_old_sp.median()
			if datetime.date.today() > fantasyweek.enddate.date():
				teamstats[i].is_final = True
			teamstats[i].set_calculated_fields()
			entitylist.append(teamstats[i])
			if len(entitylist) >= 50:
				db.put(entitylist)
				entitylist = []
			#teamstats[i].put()

		db.put(entitylist)

		entitylist = []
		for i in range(0, len(fantasyplayerstats)):
			if fantasyplayerstats[i].lineupstatus <> "A": continue
			if fantasyplayerstats[i].positioncode == 'C':
				fantasyplayerstats[i].league_fantasypoints = total_hittingtotals_c['FPTS']
				fantasyplayerstats[i].league_fantasypoints_old = total_hittingtotals_c['FPTS']
				fantasyplayerstats[i].league_medianfantasypoints = median_hittingpoints_c.median()
				fantasyplayerstats[i].league_medianfantasypoints_old = median_hittingpoints_c.median()
			elif fantasyplayerstats[i].positioncode == '1B':
				fantasyplayerstats[i].league_fantasypoints = total_hittingtotals_1b['FPTS']
				fantasyplayerstats[i].league_fantasypoints_old = total_hittingtotals_1b['FPTS']
				fantasyplayerstats[i].league_medianfantasypoints = median_hittingpoints_1b.median()
				fantasyplayerstats[i].league_medianfantasypoints_old = median_hittingpoints_1b.median()
			elif fantasyplayerstats[i].positioncode == '2B':
				fantasyplayerstats[i].league_fantasypoints = total_hittingtotals_2b['FPTS']
				fantasyplayerstats[i].league_fantasypoints_old = total_hittingtotals_2b['FPTS']
				fantasyplayerstats[i].league_medianfantasypoints = median_hittingpoints_2b.median()
				fantasyplayerstats[i].league_medianfantasypoints_old = median_hittingpoints_2b.median()
			elif fantasyplayerstats[i].positioncode == '3B':
				fantasyplayerstats[i].league_fantasypoints = total_hittingtotals_3b['FPTS']
				fantasyplayerstats[i].league_fantasypoints_old = total_hittingtotals_3b['FPTS']
				fantasyplayerstats[i].league_medianfantasypoints = median_hittingpoints_3b.median()
				fantasyplayerstats[i].league_medianfantasypoints_old = median_hittingpoints_3b.median()
			elif fantasyplayerstats[i].positioncode == 'SS':
				fantasyplayerstats[i].league_fantasypoints = total_hittingtotals_ss['FPTS']
				fantasyplayerstats[i].league_fantasypoints_old = total_hittingtotals_ss['FPTS']
				fantasyplayerstats[i].league_medianfantasypoints = median_hittingpoints_ss.median()
				fantasyplayerstats[i].league_medianfantasypoints_old = median_hittingpoints_ss.median()
			elif fantasyplayerstats[i].positioncode == 'OF':
				fantasyplayerstats[i].league_fantasypoints = total_hittingtotals_of['FPTS']
				fantasyplayerstats[i].league_fantasypoints_old = total_hittingtotals_of['FPTS']
				fantasyplayerstats[i].league_medianfantasypoints = median_hittingpoints_of.median()
				fantasyplayerstats[i].league_medianfantasypoints_old = median_hittingpoints_of.median()
			elif fantasyplayerstats[i].positioncode == 'DH':
				fantasyplayerstats[i].league_fantasypoints = total_hittingtotals_dh['FPTS']
				fantasyplayerstats[i].league_fantasypoints_old = total_hittingtotals_dh['FPTS']
				fantasyplayerstats[i].league_medianfantasypoints = median_hittingpoints_dh.median()
				fantasyplayerstats[i].league_medianfantasypoints_old = median_hittingpoints_dh.median()
			elif fantasyplayerstats[i].positioncode == 'RP':
				fantasyplayerstats[i].league_fantasypoints = total_pitchingtotals_rp['FPTS']
				fantasyplayerstats[i].league_fantasypoints_old = total_pitchingtotals_rp['FPTS_OLD']
				fantasyplayerstats[i].league_medianfantasypoints = median_pitchingpoints_rp.median()
				fantasyplayerstats[i].league_medianfantasypoints_old = median_pitchingpoints_old_rp.median()
			elif fantasyplayerstats[i].positioncode == 'SP':
				fantasyplayerstats[i].league_fantasypoints = total_pitchingtotals_sp['FPTS']
				fantasyplayerstats[i].league_fantasypoints_old = total_pitchingtotals_sp['FPTS_OLD']
				fantasyplayerstats[i].league_medianfantasypoints = median_pitchingpoints_sp.median()
				fantasyplayerstats[i].league_medianfantasypoints_old = median_pitchingpoints_old_sp.median()
			if datetime.date.today() > fantasyweek.enddate.date():
				fantasyplayerstats[i].is_final = True
			fantasyplayerstats[i].set_calculated_fields()
			entitylist.append(fantasyplayerstats[i])
			if len(entitylist) >= 50:
				db.put(entitylist)
				entitylist = []
			#fantasyplayerstats[i].put()

		db.put(entitylist)
		#db.put(fantasyplayerstats)

		fantasyweek.hittingpoints = int(total_hittingtotals['FPTS'])
		fantasyweek.hittingpoints_old = int(total_hittingtotals['FPTS'])
		fantasyweek.hittingpoints14 = int(round(fantasyweek.hittingpoints * (float(len(fantasyteams)) / 14.0), 0))
		fantasyweek.hittingpoints14_old = int(round(fantasyweek.hittingpoints_old * (float(len(fantasyteams)) / 14.0), 0))
		fantasyweek.pitchingpoints = int(total_pitchingtotals['FPTS'])
		fantasyweek.pitchingpoints_old = int(total_pitchingtotals['FPTS_OLD'])
		fantasyweek.pitchingpoints14 = int(round(fantasyweek.pitchingpoints * (float(len(fantasyteams)) / 14.0), 0))
		fantasyweek.pitchingpoints14_old = int(round(fantasyweek.pitchingpoints_old * (float(len(fantasyteams)) / 14.0), 0))
		fantasyweek.totalpoints = int(total_hittingtotals['FPTS']) + int(total_pitchingtotals['FPTS'])
		fantasyweek.totalpoints_old = int(total_hittingtotals['FPTS']) + int(total_pitchingtotals['FPTS_OLD'])
		fantasyweek.totalpoints14 = int(round(fantasyweek.totalpoints * (float(len(fantasyteams)) / 14.0), 0))
		fantasyweek.totalpoints14_old = int(round(fantasyweek.totalpoints_old * (float(len(fantasyteams)) / 14.0), 0))
		fantasyweek.startingpitchingpoints = int(total_pitchingtotals_sp['FPTS'])
		fantasyweek.startingpitchingpoints_old = int(total_pitchingtotals_sp['FPTS_OLD'])
		fantasyweek.medianhittingpoints = median_hittingpoints.median()
		fantasyweek.medianhittingpoints_old = median_hittingpoints.median()
		fantasyweek.medianhittingpoints14 = median_hittingpoints14.median()
		fantasyweek.medianhittingpoints14_old = median_hittingpoints14.median()
		fantasyweek.medianpitchingpoints = median_pitchingpoints.median()
		fantasyweek.medianpitchingpoints_old = median_pitchingpoints_old.median()
		fantasyweek.medianpitchingpoints14 = median_pitchingpoints14.median()
		fantasyweek.medianpitchingpoints14_old = median_pitchingpoints14_old.median()
		fantasyweek.medianstartingpitchingpoints = median_pitchingpoints_sp.median()
		fantasyweek.medianstartingpitchingpoints_old = median_pitchingpoints_old_sp.median()
		fantasyweek.medianstartingpitchingpointsperstart = median_pitchingpoints_per_start_sp.median()
		fantasyweek.medianstartingpitchingpointsperstart_old = median_pitchingpoints_per_start_old_sp.median()
		fantasyweek.mediantotalpoints = median_totalpoints.median()
		fantasyweek.mediantotalpoints_old = median_totalpoints_old.median()
		fantasyweek.mediantotalpoints14 = median_totalpoints14.median()
		fantasyweek.mediantotalpoints14_old = median_totalpoints14_old.median()
		if datetime.date.today() > fantasyweek.enddate.date():
			fantasyweek.is_final = True
		fantasyweek.put()

	def handle_weeklyteamstats(self, week=1, teamnumber=1, totals=False):
		if week == 0: return

		year = self.get_current_year()
		cookie = get_cookie()

		season = dygfantasystatsmodel.FantasySeason.get_or_insert_by_values(year)
		fantasyweek = dygfantasystatsmodel.FantasyWeek.get_or_insert_by_values(season, week)
		fantasyteams = dygfantasystatsmodel.FantasyTeam.all().filter("year = ", year).fetch(1000)

		if totals:
			self.do_weeklyteamstats_leaguetotals(season, fantasyweek)
		else:
			teams = []
			t = self.getdbteam(teamnumber, year)
			if t == None: return
			if t.cbsteamid == 0: return

			teaminfo = {}

			teaminfo['dbteam'] = t
			teaminfo['cbsteamid'] = t.cbsteamid

			standardpage = dygutil.get_page(cookie, 'http://dyg.baseball.cbssports.com/stats/stats-main/team:' + str(t.cbsteamid) + '/period-' + str(week) + ':f/standard')
			scoringpage = dygutil.get_page(cookie, 'http://dyg.baseball.cbssports.com/stats/stats-main/team:' + str(t.cbsteamid) + '/period-' + str(week) + ':f/scoring')

			s = standardpage[standardpage.find(' value="/stats/stats-main/team:' + str(t.cbsteamid) + '/'):]
			s = s[s.find('>') + 1:]
			teamname = s[:s.find('<')]
			teaminfo['teamname'] = teamname

			headerstoken = ':sort_col=1">Player<'
			headersendtoken = '</tr>'
			playertoken = '><a class=\'playerLink\' href=\'/players/playerpage/'
			hittersendtoken = '>TOTALS<'
			pitchersendtoken = '>TOTALS<'

			ptr = standardpage.find(hittersendtoken) + len(hittersendtoken)
			pitchersblock = standardpage[ptr:]

			teaminfo['standard-pitchers'] = self.parse_player_stats(pitchersblock, headerstoken, headersendtoken, playertoken, pitchersendtoken)

			ptr = scoringpage.find(hittersendtoken) + len(hittersendtoken)
			hittersblock = scoringpage[:ptr]
			pitchersblock = scoringpage[ptr:]

			teaminfo['scoring-hitters'] = self.parse_player_stats(hittersblock, headerstoken, headersendtoken, playertoken, hittersendtoken)
			teaminfo['scoring-pitchers'] = self.parse_player_stats(pitchersblock, headerstoken, headersendtoken, playertoken, pitchersendtoken)

			teams.append(teaminfo)

			entitylist = []
			fantasyplayerstats = []
			for fantasyteam in teams:
				teamweek = dygfantasystatsmodel.FantasyTeamStats.all().filter("timespanvalue = ", dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN).filter("runningtotaltimespanvalue = ", dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN).filter("statstype = ", dygfantasystatsmodel.FantasyTeamStats.TOTALS).filter("fantasyteam = ", fantasyteam["dbteam"]).filter("year = ", year).filter("weeknumber = ", week).filter("grouping = ", 'ALL').fetch(1)[0]
				teamweek_c = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, 'C')
				teamweek_1b = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, '1B')
				teamweek_2b = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, '2B')
				teamweek_3b = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, '3B')
				teamweek_ss = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, 'SS')
				teamweek_of = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, 'OF')
				teamweek_dh = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, 'DH')
				teamweek_hitters = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, 'HITTERS')
				teamweek_rp = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, 'RP')
				teamweek_sp = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, 'SP')
				teamweek_pitchers = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS, teamweek.fantasyteam, teamweek.vsfantasyteam, season, fantasyweek, 'PITCHERS')

				fantasyplayerstats = dygfantasystatsmodel.FantasyPlayerStats.all().filter("timespanvalue = ", dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN).filter("runningtotaltimespanvalue = ", dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN).filter("statstype = ", dygfantasystatsmodel.FantasyTeamStats.TOTALS).filter("fantasyteam = ", fantasyteam["dbteam"]).filter("year = ", year).filter("weeknumber = ", week).fetch(1000)
				team_pitchingtotals = {}
				team_pitchingtotals_sp = {}
				team_pitchingtotals_rp = {}
				team_hittingtotals = {}
				team_hittingtotals_c = {}
				team_hittingtotals_1b = {}
				team_hittingtotals_2b = {}
				team_hittingtotals_3b = {}
				team_hittingtotals_ss = {}
				team_hittingtotals_of = {}
				team_hittingtotals_dh = {}
				team_pitchingtotals_sp['GS'] = 0.0
				for pitcher in fantasyteam['standard-pitchers']:
					for i in range(0, len(fantasyplayerstats)):
						if fantasyplayerstats[i].fantasyplayer == None: continue
						if fantasyplayerstats[i].lineupstatus <> "A": continue
						if fantasyplayerstats[i].cbsplayerid == pitcher['cbsplayerid']:
							fantasyplayerstats[i].pitchingstarts = float(pitcher['GS'])
							if fantasyplayerstats[i].positioncode == "SP":
								val = float(pitcher['GS'])
								team_pitchingtotals_sp['GS'] += val

				for pitcher in fantasyteam['scoring-pitchers']:
					pitcher['WEEKS'] = 1
					pitcher['FPTS_OLD'] = \
						pitcher['B'] * -1.0 + \
						pitcher['BB'] * -1.0 + \
						pitcher['BS'] * -5.0 + \
						pitcher['CG'] * 5.0 + \
						pitcher['ER'] * -1.0 + \
						pitcher['H'] * -1.0 + \
						pitcher['HB'] * -1.0 + \
						float(self.innings_to_outs(pitcher['INN'])) * 1.0 + \
						pitcher['K'] * 1.0 + \
						pitcher['L'] * -5.0 + \
						pitcher['NH'] * 20.0 + \
						pitcher['PG'] * 30.0 + \
						pitcher['PKO'] * 1.0 + \
						pitcher['QS'] * 0.0 + \
						pitcher['S'] * 10.0 + \
						pitcher['SO'] * 10.0 + \
						pitcher['W'] * 10.0 + \
						pitcher['WP'] * -1.0
					self.add_to_totals(pitcher, team_pitchingtotals)
					for i in range(0, len(fantasyplayerstats)):
						if fantasyplayerstats[i].fantasyplayer == None: continue
						if fantasyplayerstats[i].lineupstatus <> "A": continue
						if fantasyplayerstats[i].cbsplayerid == pitcher['cbsplayerid']:
							fantasyplayerstats[i] = self.set_pitcher_stats(fantasyplayerstats[i], pitcher)
							fantasyplayerstats[i].fantasypoints = fantasyplayerstats[i].stat_fpts
							fantasyplayerstats[i].fantasypoints_old = fantasyplayerstats[i].stat_fpts_old

							if fantasyplayerstats[i].positioncode == "SP":
								self.add_to_totals(pitcher, team_pitchingtotals_sp)
							else:
								self.add_to_totals(pitcher, team_pitchingtotals_rp)

				for hitter in fantasyteam['scoring-hitters']:
					hitter['WEEKS'] = 1
					self.add_to_totals(hitter, team_hittingtotals)
					for i in range(0, len(fantasyplayerstats)):
						if fantasyplayerstats[i].fantasyplayer == None: continue
						if fantasyplayerstats[i].lineupstatus <> "A": continue
						if fantasyplayerstats[i].cbsplayerid == hitter['cbsplayerid']:
							fantasyplayerstats[i] = self.set_hitter_stats(fantasyplayerstats[i], hitter)
							fantasyplayerstats[i].fantasypoints = fantasyplayerstats[i].stat_fpts
							if fantasyplayerstats[i].positioncode == "C":
								self.add_to_totals(hitter, team_hittingtotals_c)
							elif fantasyplayerstats[i].positioncode == "1B":
								self.add_to_totals(hitter, team_hittingtotals_1b)
							elif fantasyplayerstats[i].positioncode == "2B":
								self.add_to_totals(hitter, team_hittingtotals_2b)
							elif fantasyplayerstats[i].positioncode == "3B":
								self.add_to_totals(hitter, team_hittingtotals_3b)
							elif fantasyplayerstats[i].positioncode == "SS":
								self.add_to_totals(hitter, team_hittingtotals_ss)
							elif fantasyplayerstats[i].positioncode == "OF":
								self.add_to_totals(hitter, team_hittingtotals_of)
							elif fantasyplayerstats[i].positioncode == "DH":
								self.add_to_totals(hitter, team_hittingtotals_dh)

				self.set_hitter_stats(teamweek_c, team_hittingtotals_c)
				teamweek_c.totalpoints = teamweek_c.stat_fpts
				teamweek_c.totalpoints_old = teamweek_c.stat_fpts_old
				entitylist.append(teamweek_c)

				self.set_hitter_stats(teamweek_1b, team_hittingtotals_1b)
				teamweek_1b.totalpoints = teamweek_1b.stat_fpts
				teamweek_1b.totalpoints_old = teamweek_1b.stat_fpts_old
				entitylist.append(teamweek_1b)

				self.set_hitter_stats(teamweek_2b, team_hittingtotals_2b)
				teamweek_2b.totalpoints = teamweek_2b.stat_fpts
				teamweek_2b.totalpoints_old = teamweek_2b.stat_fpts_old
				entitylist.append(teamweek_2b)

				self.set_hitter_stats(teamweek_3b, team_hittingtotals_3b)
				teamweek_3b.totalpoints = teamweek_3b.stat_fpts
				teamweek_3b.totalpoints_old = teamweek_3b.stat_fpts_old
				entitylist.append(teamweek_3b)

				self.set_hitter_stats(teamweek_ss, team_hittingtotals_ss)
				teamweek_ss.totalpoints = teamweek_ss.stat_fpts
				teamweek_ss.totalpoints_old = teamweek_ss.stat_fpts_old
				entitylist.append(teamweek_ss)

				self.set_hitter_stats(teamweek_of, team_hittingtotals_of)
				teamweek_of.totalpoints = teamweek_of.stat_fpts
				teamweek_of.totalpoints_old = teamweek_of.stat_fpts_old
				entitylist.append(teamweek_of)

				self.set_hitter_stats(teamweek_dh, team_hittingtotals_dh)
				teamweek_dh.totalpoints = teamweek_dh.stat_fpts
				teamweek_dh.totalpoints_old = teamweek_dh.stat_fpts_old
				entitylist.append(teamweek_dh)

				self.set_hitter_stats(teamweek_hitters, team_hittingtotals)
				teamweek_hitters.totalpoints = teamweek_hitters.stat_fpts
				teamweek_hitters.totalpoints_old = teamweek_hitters.stat_fpts_old
				teamweek_hitters.hittingpoints = teamweek_hitters.totalpoints
				teamweek_hitters.hittingpoints_old = teamweek_hitters.totalpoints_old
				entitylist.append(teamweek_hitters)

				self.set_pitcher_stats(teamweek_rp, team_pitchingtotals_rp)
				teamweek_rp.totalpoints = teamweek_rp.stat_fpts
				teamweek_rp.totalpoints_old = teamweek_rp.stat_fpts_old
				entitylist.append(teamweek_rp)

				self.set_pitcher_stats(teamweek_sp, team_pitchingtotals_sp)
				teamweek_sp.totalpoints = teamweek_sp.stat_fpts
				teamweek_sp.totalpoints_old = teamweek_sp.stat_fpts_old
				if 'FPTS' in team_pitchingtotals_sp:
					teamweek_sp.startingpitchingpoints = team_pitchingtotals_sp['FPTS']
				if 'FPTS_OLD' in team_pitchingtotals_sp:
					teamweek_sp.startingpitchingpoints_old = team_pitchingtotals_sp['FPTS_OLD']
				if 'GS' in team_pitchingtotals_sp:
					teamweek_sp.pitchingstarts = team_pitchingtotals_sp['GS']
				entitylist.append(teamweek_sp)

				self.set_pitcher_stats(teamweek_pitchers, team_pitchingtotals)
				teamweek_pitchers.totalpoints = teamweek_pitchers.stat_fpts
				teamweek_pitchers.totalpoints_old = teamweek_pitchers.stat_fpts_old
				if 'FPTS' in team_pitchingtotals_sp:
					teamweek_pitchers.startingpitchingpoints = team_pitchingtotals['FPTS']
				if 'FPTS_OLD' in team_pitchingtotals_sp:
					teamweek_pitchers.startingpitchingpoints_old = team_pitchingtotals['FPTS_OLD']
				if 'GS' in team_pitchingtotals_sp:
					teamweek_pitchers.pitchingstarts = team_pitchingtotals_sp['GS']
				teamweek_pitchers.pitchingpoints = teamweek_pitchers.totalpoints
				teamweek_pitchers.pitchingpoints_old = teamweek_pitchers.totalpoints_old
				entitylist.append(teamweek_pitchers)

				self.set_hitter_stats(teamweek, team_hittingtotals)
				self.set_pitcher_stats(teamweek, team_pitchingtotals)
				teamweek.hittingpoints = team_hittingtotals['FPTS']
				teamweek.hittingpoints_old = team_hittingtotals['FPTS']
				teamweek.hittingpoints14 = teamweek.hittingpoints * (float(len(fantasyteams)) / 14.0)
				teamweek.hittingpoints14_old = teamweek.hittingpoints_old * (float(len(fantasyteams)) / 14.0)
				teamweek.pitchingpoints = team_pitchingtotals['FPTS']
				teamweek.pitchingpoints_old = team_pitchingtotals['FPTS_OLD']
				teamweek.pitchingpoints14 = teamweek.pitchingpoints * (float(len(fantasyteams)) / 14.0)
				teamweek.pitchingpoints14_old = teamweek.pitchingpoints_old * (float(len(fantasyteams)) / 14.0)
				teamweek.totalpoints = team_hittingtotals['FPTS'] + team_pitchingtotals['FPTS']
				teamweek.totalpoints_old = team_hittingtotals['FPTS'] + team_pitchingtotals['FPTS_OLD']
				teamweek.totalpoints14 = teamweek.totalpoints * (float(len(fantasyteams)) / 14.0)
				teamweek.totalpoints14_old = teamweek.totalpoints_old * (float(len(fantasyteams)) / 14.0)
				if 'FPTS' in team_pitchingtotals_sp:
					teamweek.startingpitchingpoints = team_pitchingtotals_sp['FPTS']
				if 'FPTS_OLD' in team_pitchingtotals_sp:
					teamweek.startingpitchingpoints_old = team_pitchingtotals_sp['FPTS_OLD']
				if 'GS' in team_pitchingtotals_sp:
					teamweek.pitchingstarts = team_pitchingtotals_sp['GS']
				teamweek.stat_fpts = teamweek.totalpoints
				teamweek.stat_fpts_old = teamweek.totalpoints_old
				entitylist.append(teamweek)

			for i in range(0, len(entitylist)):
				if datetime.date.today() > fantasyweek.enddate.date():
					entitylist[i].is_final = True
				entitylist[i].set_calculated_fields()
			db.put(entitylist)
			for i in range(0, len(fantasyplayerstats)):
				if datetime.date.today() > fantasyweek.enddate.date():
					fantasyplayerstats[i].is_final = True
				fantasyplayerstats[i].set_calculated_fields()
			db.put(fantasyplayerstats)

	def handle_teamtotals(self, teamnumber, year):
		team = self.getdbteam(teamnumber, year)
		if team == None: return

		#algorithm
		#1. recalculate career based on previous years
		#2. zero out current season
		#3. go through weeks in this year, adding to career and season
		#4. save to DB: career, current season, weeks not final
		#5. finalize weeks as appropriate

		#or
		#1. set career totals to values as of last finalized season
		#2. set current season totals to values as of last finalized week
		#3. get non-finalized weeks for current year, add them to season and career totals
		#4. update career totals as of current season
		#5. finalize weeks, seasons

		#store weeks:
		# for week/week/totals record, always 1
		# for week/season/totals record, always week #
		# for week/career/totals record, always sum of previous season week totals + week #
		# for season/season/totals record, number of weeks so far
		# for season/career/totals record, sum of previous season week totals plus number of weeks so far

		#for each finalized week/season/totals record, calculate average per week: totals divided by week number
		#for each finalized week/career/totals record, calculate average per week: totals divided by total number of weeks
		#for each finalized season/career/totals record, calculate average per season: totals divided by total number of seasons

		def stats_to_dict(stats=None, values_only=False, keys_only=False, values_class="SMALL"):
			d = {
				'key': str(stats.key()) if stats else None,
				'pitchingpoints14': stats.pitchingpoints14 if stats else None,
				'startingpitchingpoints': stats.startingpitchingpoints if stats else None,
				'startingpitchingpointsovermedian': stats.startingpitchingpointsovermedian if stats else None,
				'lowpointweeks': stats.lowpointweeks if stats else None,
				'weeks': stats.weeks if stats else None,
				'stat_fpts': stats.stat_fpts if stats else None,
				'cbsteamid': stats.cbsteamid if stats else None,
				'breakdownlosses': stats.breakdownlosses if stats else None,
				'totalpoints14': stats.totalpoints14 if stats else None,
				'vscbsteamid': stats.vscbsteamid if stats else None,
				'totalpoints': stats.totalpoints if stats else None,
				'weeknumber': stats.weeknumber if stats else None,
				'statstype': stats.statstype if stats else None,
				'startingpitchingpoints14': stats.startingpitchingpoints14 if stats else None,
				'breakdownties': stats.breakdownties if stats else None,
				'losses': stats.losses if stats else None,
				'games': stats.games if stats else None,
				'ties': stats.ties if stats else None,
				'hittingpoints': stats.hittingpoints if stats else None,
				'vsfranchiseteamid': stats.vsfranchiseteamid if stats else None,
				'pitchingpoints': stats.pitchingpoints if stats else None,
				'franchiseteamid': stats.franchiseteamid if stats else None,
				'hittingpoints14': stats.hittingpoints14 if stats else None,
				'highpointweeks': stats.highpointweeks if stats else None,
				'breakdowngames': stats.breakdowngames if stats else None,
				'breakdownwins': stats.breakdownwins if stats else None,
				'seasons': stats.seasons if stats else None,
				'wins': stats.wins if stats else None,
				'timespanvalue': stats.timespanvalue if stats else None,
				'runningtotaltimespanvalue': stats.runningtotaltimespanvalue if stats else None,
				'pitchingstarts': stats.pitchingstarts if stats else None,
				'is_final': stats.is_final if stats else None,
				'statstype': stats.statstype if stats else None,
				'grouping': stats.grouping if stats else None,
				'year': stats.year if stats else None,
				'weeknumber': stats.weeknumber if stats else None,
			}
			if values_class == "LARGE":
				d.update({
					'hittingpoints_old': stats.hittingpoints_old if stats else None,
					'pitchingpoints_old': stats.pitchingpoints_old if stats else None,
					'startingpitchingpoints_old': stats.startingpitchingpoints_old if stats else None,
					'totalpoints_old': stats.totalpoints_old if stats else None,
					'hittingpoints14_old': stats.hittingpoints14_old if stats else None,
					'pitchingpoints14_old': stats.pitchingpoints14_old if stats else None,
					'startingpitchingpoints14_old': stats.startingpitchingpoints14_old if stats else None,
					'totalpoints14_old': stats.totalpoints14_old if stats else None,
					'league_hittingpoints': stats.league_hittingpoints if stats else None,
					'league_pitchingpoints': stats.league_pitchingpoints if stats else None,
					'league_startingpitchingpoints': stats.league_startingpitchingpoints if stats else None,
					'league_totalpoints': stats.league_totalpoints if stats else None,
					'league_hittingpoints14': stats.league_hittingpoints14 if stats else None,
					'league_pitchingpoints14': stats.league_pitchingpoints14 if stats else None,
					'league_startingpitchingpoints14': stats.league_startingpitchingpoints14 if stats else None,
					'league_totalpoints14': stats.league_totalpoints14 if stats else None,
					'league_hittingpoints_old': stats.league_hittingpoints_old if stats else None,
					'league_pitchingpoints_old': stats.league_pitchingpoints_old if stats else None,
					'league_startingpitchingpoints_old': stats.league_startingpitchingpoints_old if stats else None,
					'league_totalpoints_old': stats.league_totalpoints_old if stats else None,
					'league_hittingpoints14_old': stats.league_hittingpoints14_old if stats else None,
					'league_pitchingpoints14_old': stats.league_pitchingpoints14_old if stats else None,
					'league_startingpitchingpoints14_old': stats.league_startingpitchingpoints14_old if stats else None,
					'league_totalpoints14_old': stats.league_totalpoints14_old if stats else None,
					'league_medianhittingpoints': stats.league_medianhittingpoints if stats else None,
					'league_medianpitchingpoints': stats.league_medianpitchingpoints if stats else None,
					'league_medianstartingpitchingpoints': stats.league_medianstartingpitchingpoints if stats else None,
					'league_mediantotalpoints': stats.league_mediantotalpoints if stats else None,
					'league_medianhittingpoints_old': stats.league_medianhittingpoints_old if stats else None,
					'league_medianpitchingpoints_old': stats.league_medianpitchingpoints_old if stats else None,
					'league_medianstartingpitchingpoints_old': stats.league_medianstartingpitchingpoints_old if stats else None,
					'league_mediantotalpoints_old': stats.league_mediantotalpoints_old if stats else None,
					'stat_b': stats.stat_b if stats else None,
					'stat_bbi': stats.stat_bbi if stats else None,
					'stat_bs': stats.stat_bs if stats else None,
					'stat_cg': stats.stat_cg if stats else None,
					'stat_er': stats.stat_er if stats else None,
					'stat_ha': stats.stat_ha if stats else None,
					'stat_hb': stats.stat_hb if stats else None,
					'stat_inn': stats.stat_inn if stats else None,
					'stat_k': stats.stat_k if stats else None,
					'stat_l': stats.stat_l if stats else None,
					'stat_nh': stats.stat_nh if stats else None,
					'stat_pg': stats.stat_pg if stats else None,
					'stat_pko': stats.stat_pko if stats else None,
					'stat_qs': stats.stat_qs if stats else None,
					'stat_s': stats.stat_s if stats else None,
					'stat_so': stats.stat_so if stats else None,
					'stat_w': stats.stat_w if stats else None,
					'stat_wp': stats.stat_wp if stats else None,
					'stat_1b': stats.stat_1b if stats else None,
					'stat_2b': stats.stat_2b if stats else None,
					'stat_3b': stats.stat_3b if stats else None,
					'stat_bb': stats.stat_bb if stats else None,
					'stat_cs': stats.stat_cs if stats else None,
					'stat_cyc': stats.stat_cyc if stats else None,
					'stat_e': stats.stat_e if stats else None,
					'stat_gdp': stats.stat_gdp if stats else None,
					'stat_hp': stats.stat_hp if stats else None,
					'stat_hr': stats.stat_hr if stats else None,
					'stat_ko': stats.stat_ko if stats else None,
					'stat_ofast': stats.stat_ofast if stats else None,
					'stat_pbc': stats.stat_pbc if stats else None,
					'stat_r': stats.stat_r if stats else None,
					'stat_rbi': stats.stat_rbi if stats else None,
					'stat_sb': stats.stat_sb if stats else None,
					'stat_sf': stats.stat_sf if stats else None,
				})
			if values_only:
				return stats_dict_to_values(d, values_class=values_class)
			elif keys_only:
				return d.keys()
			else:
				return d

		def stats_values_to_dict(val):
			values = val['values']
			return dict(zip(stats_to_dict(keys_only=True, values_class=val['values_class']), val['values']))

		def stats_dict_to_values(d, values_class="SMALL"):
			return {
				'values_class': values_class,
				'values': d.values(),
			}

		entitylist = []

		season = dygfantasystatsmodel.FantasySeason.get_or_insert_by_values(year)

		from google.appengine.api import logservice
		logservice.AUTOFLUSH_ENABLED = False
		#from asizeof import asizeof

		from google.appengine.api import runtime
		logging.info("pre FantasyTeamStats: RAM=%s" % (runtime.memory_usage().current()))
		logservice.flush()

		fantasyteamweeks_q = dygfantasystatsmodel.FantasyTeamStats.all().filter("fantasyteam = ", team).filter("year = ", year).order("weeknumber")

		cursor = None
		MAX = 50
		fantasyteamweeks = []
		week_numbers = []
		while True:
			if cursor: fantasyteamweeks_q.with_cursor(cursor)
			logging.info("loop 0: RAM=%s" % (runtime.memory_usage().current()))
			logservice.flush()
			db_fantasyteamweeks = fantasyteamweeks_q.fetch(MAX+1)
			logging.info("loop 1: RAM=%s" % (runtime.memory_usage().current()))
			logservice.flush()
			#fantasyteamweeks.extend([db.to_dict(fantasyteamweek) for fantasyteamweek in db_fantasyteamweeks])
			fantasyteamweeks.extend([stats_to_dict(fantasyteamweek, values_only=True) for fantasyteamweek in db_fantasyteamweeks])
			logging.info("loop 2: RAM=%s" % (runtime.memory_usage().current()))
			logservice.flush()
			week_numbers.extend([fantasyteamweek.weeknumber for fantasyteamweek in db_fantasyteamweeks])
			logging.info("loop 3: RAM=%s" % (runtime.memory_usage().current()))
			logservice.flush()
			week_numbers = list(set(week_numbers))
			weeks_count = len(db_fantasyteamweeks)
			del db_fantasyteamweeks
			db_fantasyteamweeks = None
			if weeks_count < MAX+1: break
			cursor = fantasyteamweeks_q.cursor()

			logging.info("%s fantasyteamweeks (%s), week_numbers=%s, RAM=%s" % (len(fantasyteamweeks), 0, week_numbers, runtime.memory_usage().current()))
			logservice.flush()

		logging.info("post FantasyTeamStats: RAM=%s" % (runtime.memory_usage().current()))
		logservice.flush()

		if year < 2009:
			poslist = ['ALL']
		else:
			poslist = ['ALL', 'C', '1B', '2B', '3B', 'SS', 'OF', 'DH', 'HITTERS', 'RP', 'SP', 'PITCHERS']

		# just make sure necessary Week records exist
		for pos in poslist:
			for rt in [dygfantasystatsmodel.FantasyTeamStats.SEASON_SPAN, dygfantasystatsmodel.FantasyTeamStats.CAREER_SPAN]:
				for st in [dygfantasystatsmodel.FantasyTeamStats.PER_SEASON_AVG, dygfantasystatsmodel.FantasyTeamStats.PER_WEEK_AVG, dygfantasystatsmodel.FantasyTeamStats.ROLLING_3_AVG]:
					fts = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, rt, st, team, None, season, None, pos)
					for t in dygfantasystatsmodel.FantasyTeam.all().filter("year = ", year).fetch(1000):
						if t.franchiseteamid <> team.franchiseteamid:
							fts = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, rt, st, team, t, season, None, pos)

		logging.info("1: RAM=%s" % (runtime.memory_usage().current()))
		logservice.flush()

		# just make sure necessary Season records exist
		for pos in poslist:
			for rt in [dygfantasystatsmodel.FantasyTeamStats.SEASON_SPAN, dygfantasystatsmodel.FantasyTeamStats.CAREER_SPAN]:
				for st in [dygfantasystatsmodel.FantasyTeamStats.TOTALS, dygfantasystatsmodel.FantasyTeamStats.PER_SEASON_AVG, dygfantasystatsmodel.FantasyTeamStats.PER_WEEK_AVG, dygfantasystatsmodel.FantasyTeamStats.ROLLING_3_AVG]:
					fts = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.SEASON_SPAN, rt, st, team, None, season, None, pos)
					for t in dygfantasystatsmodel.FantasyTeam.all().filter("year = ", year).fetch(1000):
						if t.franchiseteamid <> team.franchiseteamid:
							fts = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.SEASON_SPAN, rt, st, team, t, season, None, pos)

		logging.info("2: RAM=%s" % (runtime.memory_usage().current()))
		logservice.flush()

		# just make sure necessary Career records exist
		for pos in poslist:
			for st in [dygfantasystatsmodel.FantasyTeamStats.TOTALS, dygfantasystatsmodel.FantasyTeamStats.PER_SEASON_AVG, dygfantasystatsmodel.FantasyTeamStats.PER_WEEK_AVG, dygfantasystatsmodel.FantasyTeamStats.ROLLING_3_AVG]:
				ftc = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.CAREER_SPAN, dygfantasystatsmodel.FantasyTeamStats.CAREER_SPAN, st, team, None, season, None, pos)
				for t in dygfantasystatsmodel.FantasyTeam.all().filter("year = ", year).fetch(1000):
					if t.franchiseteamid <> team.franchiseteamid:
						ftc = dygfantasystatsmodel.FantasyTeamStats.get_or_insert_by_values(dygfantasystatsmodel.FantasyTeamStats.CAREER_SPAN, dygfantasystatsmodel.FantasyTeamStats.CAREER_SPAN, st, team, t, season, None, pos)

		logging.info("3: RAM=%s" % (runtime.memory_usage().current()))
		logservice.flush()

		fantasyteamseasons_q = dygfantasystatsmodel.FantasyTeamStats.all().filter("timespanvalue = ", dygfantasystatsmodel.FantasyTeamStats.SEASON_SPAN).filter("fantasyteam = ", team).order("year")
		fantasyteamseasons = []
		cursor = None
		MAX = 100
		while True:
			if cursor: fantasyteamseasons_q.with_cursor(cursor)
			db_fantasyteamseasons = fantasyteamseasons_q.fetch(MAX+1)
			#fantasyteamseasons.extend([db.to_dict(fantasyteamseason) for fantasyteamseason in db_fantasyteamseasons])
			fantasyteamseasons.extend([stats_to_dict(fantasyteamseason, values_only=True) for fantasyteamseason in db_fantasyteamseasons])
			seasons_count = len(db_fantasyteamseasons)
			del db_fantasyteamseasons
			if seasons_count < MAX+1: break
			cursor = fantasyteamseasons_q.cursor()

			logging.info("%s fantasyteamseasons (%s), RAM=%s" % (len(fantasyteamseasons), 0, runtime.memory_usage().current()))
			logservice.flush()

		logging.info("4: RAM=%s" % (runtime.memory_usage().current()))
		logservice.flush()

		fantasyteamcareer_q = dygfantasystatsmodel.FantasyTeamStats.all().filter("timespanvalue = ", dygfantasystatsmodel.FantasyTeamStats.CAREER_SPAN).filter("fantasyteam = ", team)
		fantasyteamcareer = []
		cursor = None
		MAX = 100
		while True:
			if cursor: fantasyteamcareer_q.with_cursor(cursor)
			db_fantasyteamcareer = fantasyteamcareer_q.fetch(MAX+1)
			#fantasyteamcareer.extend([db.to_dict(fantasyteamcareer_record) for fantasyteamcareer_record in db_fantasyteamcareer])
			fantasyteamcareer.extend([stats_to_dict(fantasyteamcareer_record, values_only=True) for fantasyteamcareer_record in db_fantasyteamcareer])
			career_count = len(db_fantasyteamcareer)
			del db_fantasyteamcareer
			if career_count < MAX+1: break
			cursor = fantasyteamcareer_q.cursor()

			logging.info("%s fantasyteamcareer (%s), RAM=%s" % (len(fantasyteamcareer), 0, runtime.memory_usage().current()))
			logservice.flush()

		logging.info("5: RAM=%s" % (runtime.memory_usage().current()))
		logservice.flush()

		def zerototals(val_list):
			entity = stats_values_to_dict(val_list)
			entity['weeks'] = 0
			entity['seasons'] = 0
			entity['wins'] = 0.0
			entity['losses'] = 0.0
			entity['ties'] = 0.0
			entity['hittingpoints'] = 0.0
			entity['pitchingpoints'] = 0.0
			entity['startingpitchingpoints'] = 0.0
			entity['totalpoints'] = 0.0
			entity['hittingpoints14'] = 0.0
			entity['pitchingpoints14'] = 0.0
			entity['startingpitchingpoints14'] = 0.0
			entity['totalpoints14'] = 0.0
			entity['hittingpoints_old'] = 0.0
			entity['pitchingpoints_old'] = 0.0
			entity['startingpitchingpoints_old'] = 0.0
			entity['totalpoints_old'] = 0.0
			entity['hittingpoints14_old'] = 0.0
			entity['pitchingpoints14_old'] = 0.0
			entity['startingpitchingpoints14_old'] = 0.0
			entity['totalpoints14_old'] = 0.0
			entity['league_hittingpoints'] = 0.0
			entity['league_pitchingpoints'] = 0.0
			entity['league_startingpitchingpoints'] = 0.0
			entity['league_totalpoints'] = 0.0
			entity['league_hittingpoints14'] = 0.0
			entity['league_pitchingpoints14'] = 0.0
			entity['league_startingpitchingpoints14'] = 0.0
			entity['league_totalpoints14'] = 0.0
			entity['league_hittingpoints_old'] = 0.0
			entity['league_pitchingpoints_old'] = 0.0
			entity['league_startingpitchingpoints_old'] = 0.0
			entity['league_totalpoints_old'] = 0.0
			entity['league_hittingpoints14_old'] = 0.0
			entity['league_pitchingpoints14_old'] = 0.0
			entity['league_startingpitchingpoints14_old'] = 0.0
			entity['league_totalpoints14_old'] = 0.0
			entity['league_medianhittingpoints'] = 0.0
			entity['league_medianpitchingpoints'] = 0.0
			entity['league_medianstartingpitchingpoints'] = 0.0
			entity['league_mediantotalpoints'] = 0.0
			entity['league_medianhittingpoints_old'] = 0.0
			entity['league_medianpitchingpoints_old'] = 0.0
			entity['league_medianstartingpitchingpoints_old'] = 0.0
			entity['league_mediantotalpoints_old'] = 0.0
			entity['pitchingstarts'] = 0.0
			entity['highpointweeks'] = 0.0
			entity['lowpointweeks'] = 0.0
			entity['breakdownwins'] = 0.0
			entity['breakdownlosses'] = 0.0
			entity['breakdownties'] = 0.0
			entity['stat_b'] = 0.0
			entity['stat_bbi'] = 0.0
			entity['stat_bs'] = 0.0
			entity['stat_cg'] = 0.0
			entity['stat_er'] = 0.0
			entity['stat_ha'] = 0.0
			entity['stat_hb'] = 0.0
			entity['stat_inn'] = 0.0
			entity['stat_k'] = 0.0
			entity['stat_l'] = 0.0
			entity['stat_nh'] = 0.0
			entity['stat_pg'] = 0.0
			entity['stat_pko'] = 0.0
			entity['stat_qs'] = 0.0
			entity['stat_s'] = 0.0
			entity['stat_so'] = 0.0
			entity['stat_w'] = 0.0
			entity['stat_wp'] = 0.0
			entity['stat_1b'] = 0.0
			entity['stat_2b'] = 0.0
			entity['stat_3b'] = 0.0
			entity['stat_bb'] = 0.0
			entity['stat_cs'] = 0.0
			entity['stat_cyc'] = 0.0
			entity['stat_e'] = 0.0
			entity['stat_gdp'] = 0.0
			entity['stat_hp'] = 0.0
			entity['stat_hr'] = 0.0
			entity['stat_ko'] = 0.0
			entity['stat_ofast'] = 0.0
			entity['stat_pbc'] = 0.0
			entity['stat_r'] = 0.0
			entity['stat_rbi'] = 0.0
			entity['stat_sb'] = 0.0
			entity['stat_sf'] = 0.0
			return stats_dict_to_values(entity, values_class="LARGE")

		def filter_list(list, runningtotaltimespanvalue=None, statstype=None, grouping=None, year=None, weeknumber=None, vsfantasyteam=None):
			new_list = []
			for l in list:
				d = stats_values_to_dict(l)
				if (d['runningtotaltimespanvalue'] == runningtotaltimespanvalue or runningtotaltimespanvalue == None) \
					and (d['statstype'] == statstype or statstype == None) \
					and (d['grouping'] == grouping or grouping == None) \
					and (d['year'] == year or year == 0) \
					and (d['weeknumber'] == weeknumber or weeknumber == 0) \
					and (d['vsfranchiseteamid'] == vsfantasyteam or vsfantasyteam == None):
					new_list.append(l)
			return new_list

		def filter_listindexes(list, runningtotaltimespanvalue=None, statstype=None, grouping=None, year=0, weeknumber=0, vsfranchiseteamid=0):
			indexes = []
			for i in range(0, len(list)):
				l = list[i]
				d = stats_values_to_dict(l)
				if (d['runningtotaltimespanvalue'] == runningtotaltimespanvalue or runningtotaltimespanvalue == None) \
					and (d['statstype'] == statstype or statstype == None) \
					and (d['grouping'] == grouping or grouping == None) \
					and (d['year'] == year or year == 0) \
					and (d['weeknumber'] == weeknumber or weeknumber == 0) \
					and (d['vsfranchiseteamid'] == vsfranchiseteamid or vsfranchiseteamid == 0):
					indexes.append(i)
			return indexes

		week_dirty_indexes = []
		season_dirty_indexes = []
		career_dirty_indexes = []

		logging.info("pre stats crunch: RAM=%s" % (runtime.memory_usage().current()))
		logservice.flush()

		# recalculate career totals based on previous final seasons
		for i in range(0, len(fantasyteamcareer)):
			fantasyteamcareer[i] = zerototals(fantasyteamcareer[i])
		fantasyteamseasons_seasontotals_indexes = \
			filter_listindexes(fantasyteamseasons, dygfantasystatsmodel.FantasyTeamStats.SEASON_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS)
		logging.info("fantasyteamseasons_seasontotals_indexes=%s" % fantasyteamseasons_seasontotals_indexes)
		for seasonindex in fantasyteamseasons_seasontotals_indexes:
			season_d = stats_values_to_dict(fantasyteamseasons[seasonindex])
			if (not season_d['is_final']) or \
				season_d['year'] >= year: continue
			fantasyteamcareer_matching_indexes = \
				filter_listindexes(fantasyteamcareer,
							dygfantasystatsmodel.FantasyTeamStats.CAREER_SPAN,
							dygfantasystatsmodel.FantasyTeamStats.TOTALS,
							season_d['grouping'],
							0,
							0,
							season_d['vsfranchiseteamid'])
			logging.info("fantasyteamcareer_matching_indexes=%s" % fantasyteamcareer_matching_indexes)
			for careerindex in fantasyteamcareer_matching_indexes:
				career_d = stats_values_to_dict(fantasyteamcareer[careerindex])
				career_d['wins'] += season_d['wins']
				career_d['losses'] += season_d['losses']
				career_d['ties'] += season_d['ties']
				career_d['totalpoints'] += season_d['totalpoints']
				career_d['totalpoints14'] += season_d['totalpoints14']
				career_d['league_totalpoints'] += season_d['league_totalpoints']
				career_d['league_totalpoints14'] += season_d['league_totalpoints14']
				career_d['breakdownwins'] += season_d['breakdownwins']
				career_d['breakdownlosses'] += season_d['breakdownlosses']
				career_d['breakdownties'] += season_d['breakdownties']
				career_d['highpointweeks'] += season_d['highpointweeks']
				career_d['lowpointweeks'] += season_d['lowpointweeks']
				career_d['weeks'] += season_d['weeks']
				career_d['seasons'] += 1
				if careerindex not in career_dirty_indexes:
					career_dirty_indexes.append(careerindex)

				fantasyteamcareer_perweekavg_indexes = \
					filter_listindexes(fantasyteamcareer,
								dygfantasystatsmodel.FantasyTeamStats.CAREER_SPAN,
								dygfantasystatsmodel.FantasyTeamStats.PER_WEEK_AVG,
								season_d['grouping'],
								0,
								0,
								season_d['vsfranchiseteamid'])
				logging.info("fantasyteamcareer_perweekavg_indexes=%s" % fantasyteamcareer_perweekavg_indexes)
				for careeringdex_avg in fantasyteamcareer_perweekavg_indexes:
					career_avg_d = stats_values_to_dict(fantasyteamcareer[careeringdex_avg])
					career_avg_d['wins'] = career_d['wins'] / career_d['weeks']
					career_avg_d['losses'] = career_d['losses'] / career_d['weeks']
					career_avg_d['ties'] = career_d['ties'] / career_d['weeks']
					career_avg_d['totalpoints'] = career_d['totalpoints'] / career_d['weeks']
					career_avg_d['totalpoints14'] = career_d['totalpoints14'] / career_d['weeks']
					career_avg_d['league_totalpoints'] = career_d['league_totalpoints'] / career_d['weeks']
					career_avg_d['league_totalpoints14'] = career_d['league_totalpoints14'] / career_d['weeks']
					career_avg_d['breakdownwins'] = career_d['breakdownwins'] / career_d['weeks']
					career_avg_d['breakdownlosses'] = career_d['breakdownlosses'] / career_d['weeks']
					career_avg_d['breakdownties'] = career_d['breakdownties'] / career_d['weeks']
					career_avg_d['highpointweeks'] = career_d['highpointweeks'] / career_d['weeks']
					career_avg_d['lowpointweeks'] = career_d['lowpointweeks'] / career_d['weeks']
					career_avg_d['weeks'] = career_d['weeks']
					career_avg_d['seasons'] = career_d['seasons']
					if careeringdex_avg not in career_dirty_indexes:
						career_dirty_indexes.append(careeringdex_avg)

				fantasyteamcareer_perseasonavg_indexes = \
					filter_listindexes(fantasyteamcareer,
								dygfantasystatsmodel.FantasyTeamStats.CAREER_SPAN,
								dygfantasystatsmodel.FantasyTeamStats.PER_SEASON_AVG,
								season_d['grouping'],
								0,
								0,
								season_d['vsfranchiseteamid'])
				logging.info("fantasyteamcareer_perseasonavg_indexes=%s" % fantasyteamcareer_perseasonavg_indexes)
				for careeringdex_avg in fantasyteamcareer_perseasonavg_indexes:
					career_avg_d = stats_values_to_dict(fantasyteamcareer[careeringdex_avg])
					career_avg_d['wins'] = career_d['wins'] / career_d['seasons']
					career_avg_d['losses'] = career_d['losses'] / career_d['seasons']
					career_avg_d['ties'] = career_d['ties'] / career_d['seasons']
					career_avg_d['totalpoints'] = career_d['totalpoints'] / career_d['seasons']
					career_avg_d['totalpoints14'] = career_d['totalpoints14'] / career_d['seasons']
					career_avg_d['league_totalpoints'] = career_d['league_totalpoints'] / career_d['seasons']
					career_avg_d['league_totalpoints14'] = career_d['league_totalpoints14'] / career_d['seasons']
					career_avg_d['breakdownwins'] = career_d['breakdownwins'] / career_d['seasons']
					career_avg_d['breakdownlosses'] = career_d['breakdownlosses'] / career_d['seasons']
					career_avg_d['breakdownties'] = career_d['breakdownties'] / career_d['seasons']
					career_avg_d['highpointweeks'] = career_d['highpointweeks'] / career_d['seasons']
					career_avg_d['lowpointweeks'] = career_d['lowpointweeks'] / career_d['seasons']
					career_avg_d['weeks'] = career_d['weeks']
					career_avg_d['seasons'] = career_d['seasons']
					if careeringdex_avg not in career_dirty_indexes:
						career_dirty_indexes.append(careeringdex_avg)

				fantasyteamcareer_rolling3avg_indexes = \
					filter_listindexes(fantasyteamcareer,
								dygfantasystatsmodel.FantasyTeamStats.CAREER_SPAN,
								dygfantasystatsmodel.FantasyTeamStats.ROLLING_3_AVG,
								season_d['grouping'],
								0,
								0,
								season_d['vsfranchiseteamid'])
				career_3week_totals = dygfantasystatsmodel.FantasyTeamStats()
				career_3week_seasons = 0
				for careeringdex_avg in fantasyteamcareer_rolling3avg_indexes:
					continue

				fantasyteamseasons_careertotals_indexes = \
					filter_listindexes(fantasyteamseasons,
								dygfantasystatsmodel.FantasyTeamStats.CAREER_SPAN,
								dygfantasystatsmodel.FantasyTeamStats.TOTALS,
								fantasyteamseasons[seasonindex]['grouping'],
								fantasyteamseasons[seasonindex]['year'],
								0,
								fantasyteamseasons[seasonindex]['vsfranchiseteamid'])
				logging.info("fantasyteamseasons_careertotals_indexes=%s" % fantasyteamseasons_careertotals_indexes)
				for seasonindex_career in fantasyteamseasons_careertotals_indexes:
					season_career_d = stats_values_to_dict(fantasyteamseasons[seasonindex_career])
					season_career_d['wins'] = career_d['wins']
					season_career_d['losses'] = career_d['losses']
					season_career_d['ties'] = career_d['ties']
					season_career_d['totalpoints'] = career_d['totalpoints']
					season_career_d['totalpoints14'] = career_d['totalpoints14']
					season_career_d['league_totalpoints'] = career_d['league_totalpoints']
					season_career_d['league_totalpoints14'] = career_d['league_totalpoints14']
					season_career_d['breakdownwins'] = career_d['breakdownwins']
					season_career_d['breakdownlosses'] = career_d['breakdownlosses']
					season_career_d['breakdownties'] = career_d['breakdownties']
					season_career_d['highpointweeks'] = career_d['highpointweeks']
					season_career_d['lowpointweeks'] = career_d['lowpointweeks']
					season_career_d['weeks'] = career_d['weeks']
					season_career_d['seasons'] = career_d['seasons']
					if seasonindex_career not in season_dirty_indexes:
						season_dirty_indexes.append(seasonindex_career)

				fantasyteamseasons_careeravg_indexes = \
					filter_listindexes(fantasyteamseasons,
								dygfantasystatsmodel.FantasyTeamStats.CAREER_SPAN,
								dygfantasystatsmodel.FantasyTeamStats.PER_WEEK_AVG,
								fantasyteamseasons[seasonindex]['grouping'],
								fantasyteamseasons[seasonindex]['year'],
								0,
								fantasyteamseasons[seasonindex]['vsfranchiseteamid'])
				logging.info("fantasyteamseasons_careeravg_indexes=%s" % fantasyteamseasons_careeravg_indexes)
				for seasonindex_career in fantasyteamseasons_careeravg_indexes:
					season_career_d = stats_values_to_dict(fantasyteamseasons[seasonindex_career])
					season_career_d['wins'] = career_d['wins'] / career_d['weeks']
					season_career_d['losses'] = career_d['losses'] / career_d['weeks']
					season_career_d['ties'] = career_d['ties'] / career_d['weeks']
					season_career_d['totalpoints'] = career_d['totalpoints'] / career_d['weeks']
					season_career_d['totalpoints14'] = career_d['totalpoints14'] / career_d['weeks']
					season_career_d['league_totalpoints'] = career_d['league_totalpoints'] / career_d['weeks']
					season_career_d['league_totalpoints14'] = career_d['league_totalpoints14'] / career_d['weeks']
					season_career_d['breakdownwins'] = career_d['breakdownwins'] / career_d['weeks']
					season_career_d['breakdownlosses'] = career_d['breakdownlosses'] / career_d['weeks']
					season_career_d['breakdownties'] = career_d['breakdownties'] / career_d['weeks']
					season_career_d['highpointweeks'] = career_d['highpointweeks'] / career_d['weeks']
					season_career_d['lowpointweeks'] = career_d['lowpointweeks'] / career_d['weeks']
					season_career_d['weeks'] = career_d['weeks']
					season_career_d['seasons'] = career_d['seasons']
					if seasonindex_career not in season_dirty_indexes:
						season_dirty_indexes.append(seasonindex_career)

				fantasyteamseasons_careeravg_indexes = \
					filter_listindexes(fantasyteamseasons,
								dygfantasystatsmodel.FantasyTeamStats.CAREER_SPAN,
								dygfantasystatsmodel.FantasyTeamStats.PER_SEASON_AVG,
								fantasyteamseasons[seasonindex]['grouping'],
								fantasyteamseasons[seasonindex]['year'],
								0,
								fantasyteamseasons[seasonindex]['vsfranchiseteamid'])
				logging.info("fantasyteamseasons_careeravg_indexes=%s" % fantasyteamseasons_careeravg_indexes)
				for seasonindex_career in fantasyteamseasons_careeravg_indexes:
					season_career_d = stats_values_to_dict(fantasyteamseasons[seasonindex_career])
					season_career_d['wins'] = career_d['wins'] / career_d['seasons']
					season_career_d['losses'] = career_d['losses'] / career_d['seasons']
					season_career_d['ties'] = career_d['ties'] / career_d['seasons']
					season_career_d['totalpoints'] = career_d['totalpoints'] / career_d['seasons']
					season_career_d['totalpoints14'] = career_d['totalpoints14'] / career_d['seasons']
					season_career_d['league_totalpoints'] = career_d['league_totalpoints'] / career_d['seasons']
					season_career_d['league_totalpoints14'] = career_d['league_totalpoints14'] / career_d['seasons']
					season_career_d['breakdownwins'] = career_d['breakdownwins'] / career_d['seasons']
					season_career_d['breakdownlosses'] = career_d['breakdownlosses'] / career_d['seasons']
					season_career_d['breakdownties'] = career_d['breakdownties'] / career_d['seasons']
					season_career_d['highpointweeks'] = career_d['highpointweeks'] / career_d['seasons']
					season_career_d['lowpointweeks'] = career_d['lowpointweeks'] / career_d['seasons']
					season_career_d['weeks'] = career_d['weeks']
					season_career_d['seasons'] = career_d['seasons']
					if seasonindex_career not in season_dirty_indexes:
						season_dirty_indexes.append(seasonindex_career)

		# recalculate this season's totals
		for i in range(0, len(fantasyteamseasons)):
			d = stats_values_to_dict(fantasyteamseasons[i])
			if d['year'] == year:
				fantasyteamseasons[i] = zerototals(fantasyteamseasons[i])
		fantasyteamweeks_weeklytotals_indexes = \
			filter_listindexes(fantasyteamweeks, dygfantasystatsmodel.FantasyTeamStats.WEEK_SPAN, dygfantasystatsmodel.FantasyTeamStats.TOTALS)

		logging.info("fantasyteamweeks_weeklytotals_indexes=%s" % fantasyteamweeks_weeklytotals_indexes)

		for weekindex in fantasyteamweeks_weeklytotals_indexes:
			week_d = stats_values_to_dict(fantasyteamweeks[weekindex])
			fantasyteamseasons_matching_indexes = \
				filter_listindexes(fantasyteamseasons,
							dygfantasystatsmodel.FantasyTeamStats.SEASON_SPAN,
							week_d['statstype'],
							week_d['grouping'],
							week_d['year'],
							0,
							week_d['vsfranchiseteamid'])
			logging.info("fantasyteamseasons_matching_indexes=%s" % fantasyteamseasons_matching_indexes)
			for seasonindex in fantasyteamseasons_matching_indexes:
				season_d = stats_values_to_dict(fantasyteamseasons[seasonindex])
				season_d['wins'] += week_d['wins']
				season_d['losses'] += week_d['losses']
				season_d['ties'] += week_d['ties']
				season_d['totalpoints'] += week_d['totalpoints']
				season_d['totalpoints14'] += week_d['totalpoints14']
				season_d['league_totalpoints'] += week_d['league_totalpoints']
				season_d['league_totalpoints14'] += week_d['league_totalpoints14']
				season_d['breakdownwins'] += week_d['breakdownwins']
				season_d['breakdownlosses'] += week_d['breakdownlosses']
				season_d['breakdownties'] += week_d['breakdownties']
				season_d['highpointweeks'] += week_d['highpointweeks']
				season_d['lowpointweeks'] += week_d['lowpointweeks']
				season_d['weeks'] += 1
				if week_d['is_final'] and season.enddate == week_d.week.enddate:
					season_d['is_final'] = True
				if seasonindex not in season_dirty_indexes:
					season_dirty_indexes.append(seasonindex)

				fantasyteamweeks_seasonavg_indexes = \
					filter_listindexes(fantasyteamweeks,
								dygfantasystatsmodel.FantasyTeamStats.SEASON_SPAN,
								dygfantasystatsmodel.FantasyTeamStats.PER_WEEK_AVG,
								week_d['grouping'],
								week_d['year'],
								week_d['weeknumber'],
								week_d['vsfranchiseteamid'])
				logging.info("fantasyteamweeks_seasonavg_indexes=%s" % fantasyteamweeks_seasonavg_indexes)
				for weekindex_season in fantasyteamweeks_seasonavg_indexes:
					week_season_d = stats_values_to_dict(fantasyteamweeks[weekindex_season])
					week_season_d['wins'] = season_d['wins'] / season_d['weeks']
					week_season_d['losses'] = season_d['losses'] / season_d['weeks']
					week_season_d['ties'] = season_d['ties'] / season_d['weeks']
					week_season_d['totalpoints'] = season_d['totalpoints'] / season_d['weeks']
					week_season_d['totalpoints14'] = season_d['totalpoints14'] / season_d['weeks']
					week_season_d['league_totalpoints'] = season_d['league_totalpoints'] / season_d['weeks']
					week_season_d['league_totalpoints14'] = season_d['league_totalpoints14'] / season_d['weeks']
					week_season_d['breakdownwins'] = season_d['breakdownwins'] / season_d['weeks']
					week_season_d['breakdownlosses'] = season_d['breakdownlosses'] / season_d['weeks']
					week_season_d['breakdownties'] = season_d['breakdownties'] / season_d['weeks']
					week_season_d['highpointweeks'] = season_d['highpointweeks'] / season_d['weeks']
					week_season_d['lowpointweeks'] = season_d['lowpointweeks'] / season_d['weeks']
					week_season_d['weeks'] = 1
					if weekindex_season not in week_dirty_indexes:
						week_dirty_indexes.append(weekindex_season)

			fantasyteamcareer_matching_indexes = \
				filter_listindexes(fantasyteamcareer,
							week_d['runningtotaltimespanvalue'],
							week_d['statstype'],
							week_d['grouping'],
							0,
							0,
							week_d['vsfranchiseteamid'])
			logging.info("fantasyteamcareer_matching_indexes=%s" % fantasyteamcareer_matching_indexes)
			for careerindex in fantasyteamcareer_matching_indexes:
				# if per-week average: only add if week is final.
				if career_d['statstype'] == dygfantasystatsmodel.FantasyTeamStats.PER_WEEK_AVG and \
					not week_d['is_final']:
					continue
				fantasyteamcareer[careerindex]['wins'] += week_d['wins']
				fantasyteamcareer[careerindex]['losses'] += week_d['losses']
				fantasyteamcareer[careerindex]['ties'] += week_d['ties']
				fantasyteamcareer[careerindex]['totalpoints'] += week_d['totalpoints']
				fantasyteamcareer[careerindex]['totalpoints14'] += week_d['totalpoints14']
				fantasyteamcareer[careerindex]['league_totalpoints'] += week_d['league_totalpoints']
				fantasyteamcareer[careerindex]['league_totalpoints14'] += week_d['league_totalpoints14']
				fantasyteamcareer[careerindex]['breakdownwins'] += week_d['breakdownwins']
				fantasyteamcareer[careerindex]['breakdownlosses'] += week_d['breakdownlosses']
				fantasyteamcareer[careerindex]['breakdownties'] += week_d['breakdownties']
				fantasyteamcareer[careerindex]['highpointweeks'] += week_d['highpointweeks']
				fantasyteamcareer[careerindex]['lowpointweeks'] += week_d['lowpointweeks']
				fantasyteamcareer[careerindex]['weeks'] += 1
				if careerindex not in career_dirty_indexes:
					career_dirty_indexes.append(careerindex)

				fantasyteamweeks_careeravg_indexes = \
					filter_listindexes(fantasyteamweeks,
								dygfantasystatsmodel.FantasyTeamStats.CAREER_SPAN,
								dygfantasystatsmodel.FantasyTeamStats.PER_WEEK_AVG,
								week_d['grouping'],
								week_d['year'],
								week_d['weeknumber'],
								week_d['vsfranchiseteamid'])
				logging.info("fantasyteamweeks_careeravg_indexes=%s" % fantasyteamweeks_careeravg_indexes)
				for weekindex_career in fantasyteamweeks_careeravg_indexes:
					week_career_d = stats_values_to_dict(fantasyteamweeks[weekindex_career])
					week_career_d['wins'] = fantasyteamcareer[careerindex]['wins'] / fantasyteamcareer[careerindex]['weeks']
					week_career_d['losses'] = fantasyteamcareer[careerindex]['losses'] / fantasyteamcareer[careerindex]['weeks']
					week_career_d['ties'] = fantasyteamcareer[careerindex]['ties'] / fantasyteamcareer[careerindex]['weeks']
					week_career_d['totalpoints'] = fantasyteamcareer[careerindex]['totalpoints'] / fantasyteamcareer[careerindex]['weeks']
					week_career_d['totalpoints14'] = fantasyteamcareer[careerindex]['totalpoints14'] / fantasyteamcareer[careerindex]['weeks']
					week_career_d['league_totalpoints'] = fantasyteamcareer[careerindex]['league_totalpoints'] / fantasyteamcareer[careerindex]['weeks']
					week_career_d['league_totalpoints14'] = fantasyteamcareer[careerindex]['league_totalpoints14'] / fantasyteamcareer[careerindex]['weeks']
					week_career_d['breakdownwins'] = fantasyteamcareer[careerindex]['breakdownwins'] / fantasyteamcareer[careerindex]['weeks']
					week_career_d['breakdownlosses'] = fantasyteamcareer[careerindex]['breakdownlosses'] / fantasyteamcareer[careerindex]['weeks']
					week_career_d['breakdownties'] = fantasyteamcareer[careerindex]['breakdownties'] / fantasyteamcareer[careerindex]['weeks']
					week_career_d['highpointweeks'] = fantasyteamcareer[careerindex]['highpointweeks'] / fantasyteamcareer[careerindex]['weeks']
					week_career_d['lowpointweeks'] = fantasyteamcareer[careerindex]['lowpointweeks'] / fantasyteamcareer[careerindex]['weeks']
					week_career_d['weeks'] = 1
					if weekindex_career not in week_dirty_indexes:
						week_dirty_indexes.append(weekindex_career)

		logging.info("week_dirty_indexes=%s" % week_dirty_indexes)
		logging.info("season_dirty_indexes=%s" % season_dirty_indexes)
		logging.info("career_dirty_indexes=%s" % career_dirty_indexes)

		entitylist = []
		for i in week_dirty_indexes:
			fantasyteamweeks[i].set_calculated_fields()
			entitylist.append(fantasyteamweeks[i])
		db.put(entitylist)

		entitylist = []
		for i in season_dirty_indexes:
			fantasyteamseasons[i].set_calculated_fields()
			entitylist.append(fantasyteamseasons[i])
		db.put(entitylist)

		entitylist = []
		for i in career_dirty_indexes:
			fantasyteamcareer[i].set_calculated_fields()
			entitylist.append(fantasyteamcareer[i])
		db.put(entitylist)


	def handle_setupfantasyteams(self, year):
		cookie = get_cookie()
		import json

		def is_json(myjson):
		    try:
		        json_object = json.loads(myjson)
		    except ValueError, e:
		        return False
		    return True

		teams_map = {}
		# page = dygutil.get_page(cookie, 'http://dyg.baseball.cbssports.com/setup/commish-tools/manage-teams-owners')
		page = dygutil.get_page(cookie, 'http://dyg.baseball.cbssports.com/api/users/owners-from-leagues/aggregated?version=3.0&league_id=dyg&SPORT=baseball&response_format=json&version=3.0&resultFormat=json&responseFormat=json')
		
		for owner in json.loads(page)['body']['by_league_owners']['dyg']['league_owners']:
			teams_map[owner['team']['id']] = owner['team']['long_abbr']

		logging.info("teams_map=%s" % teams_map)

		page = dygutil.get_page(cookie, 'http://dyg.baseball.cbssports.com/standings/' + str(year))

		headerstoken = '>Team<'
		headersendtoken = '</tr>'
		teamtoken = '<tr'
		teamsendtoken = '</table>'

		teams = []
		global_ptr = 0

		ptr = page.find(headerstoken)
		global_ptr += ptr
		s = page[ptr:]
		ptr = s.find(headersendtoken)
		headersblock = s[:ptr]

		ptr = s.find(teamtoken)
		global_ptr += ptr
		s = s[ptr:]
		ptr = s.find(teamsendtoken)
		teamssblock = s[:ptr]

		temp = page[global_ptr:]

		def getcols(headersblock):
			cols = headersblock.split('<td')
			cols = cols[1:]
			outputcols = cols[:len(cols)]
			for i in range(0, len(outputcols)):
				s = outputcols[i].strip()[1:]
				s = s[s.find('>') + 1:]
				s = s[:s.find('<')]

				outputcols[i] = s
			return outputcols

		cols = getcols(headersblock)

		htmlteams = teamssblock.split(teamtoken)
		def extractteaminfo(list, cols, htmlteams):
			for p in htmlteams:
				if p == '' or p.find('Standings Updated as of') > 0: continue

				teaminfo = {}

				#str:   height=17  class="bg2" align="right" valign="middle"><td  align=left><a href=/teams/page/6>DoggerLovesBacon</a></td><td >0</td><td >0</td><td >0</td><td >0.000</td><td >&nbsp;</td><td >-</td><td >0</td><td >0.0</td><td >0.0</td><td >0.0</td></tr>
				# ' class="row1"  align="right"><td  align="left">Vandelay Importers and Exporters</td><td >18</td><td >8</td><td >0</td><td >0.692</td><td >0</td><td >W6</td><td >5</td><td >7014.0</td><td >100.0</td><td >5967.0</td></tr>'
				s = p[:p.find("</tr>")]
				ptr = p.find("href='/teams/")
				if ptr > 0:
					s = s[ptr+13:]
					ptr = s.find("'>")
					teaminfo['cbsteamid'] = s[:ptr]
					ptr += 1
				else:
					teaminfo['cbsteamid'] = '0'
					ptr = s.find('>')
					s = s[ptr+1:]
					ptr = s.find('>')

				s = s[ptr + 1:]
				if s.find('<img') >= 0:
					ptr = s.find('>')
					s = s[ptr+1:]
				ptr = s.find('<')
				teaminfo['teamname'] = s[:ptr].strip()
				#if not teaminfo['teamname']: continue

				statcols = s[ptr:].split('<td')
				statcols = statcols[1:]
				teamcols = statcols[:len(cols)]

				for i in range(0, len(teamcols)):
					s = teamcols[i]
					s = s[s.find('>') + 1:]
					s = s[:s.find('<')]

					try:
						teaminfo[cols[i]] = float(s)
					except:
						teaminfo[cols[i]] = s

				list.append(teaminfo)

		extractteaminfo(teams, cols, htmlteams)

		for t in teams:
			franchiseteamid = 0
			dbteams = []
			cbsteamid = int(t["cbsteamid"])
			if cbsteamid > 0 and year == self.get_current_year():
				franchise = dygmodel.Team.all().filter("cbsteamid = ", cbsteamid).fetch(1)[0]
				franchiseteamid = franchise.teamid
			if franchiseteamid:
				dbteams = dygfantasystatsmodel.FantasyTeam.all().filter("year = ", year).filter("franchiseteamid = ", franchiseteamid).fetch(1)
			else:
				if cbsteamid > 0:
					dbteams = dygfantasystatsmodel.FantasyTeam.all().filter("year = ", year).filter("cbsteamid = ", cbsteamid).fetch(1)
					if len(dbteams) == 0:
						lastteams = dygfantasystatsmodel.FantasyTeam.all().filter("year = ", year-1).filter("cbsteamid = ", cbsteamid).fetch(1)
						if len(lastteams) > 0:
							franchiseteamid = lastteams[0].franchiseteamid
						else:
							lastteams = dygfantasystatsmodel.FantasyTeam.all().filter("year = ", year-1).filter("teamname = ", t["teamname"]).fetch(1)
							if len(lastteams) > 0:
								franchiseteamid = lastteams[0].franchiseteamid
				else:
					dbteams = dygfantasystatsmodel.FantasyTeam.all().filter("year = ", year).filter("teamname = ", t["teamname"]).fetch(1)
					if len(dbteams) == 0:
						lastteams = dygfantasystatsmodel.FantasyTeam.all().filter("year = ", year-1).filter("teamname = ", t["teamname"]).fetch(1)
						if len(lastteams) > 0:
							franchiseteamid = lastteams[0].franchiseteamid

			if len(dbteams) == 0:
				dbteam = dygfantasystatsmodel.FantasyTeam(year=year, teamname=t["teamname"], cbsteamid=cbsteamid)
				dbteam.franchiseteamid = franchiseteamid
			else:
				dbteam = dbteams[0]
				dbteam.teamname = t["teamname"]
				if t["cbsteamid"] in teams_map:
					dbteam.shortname = teams_map[t["cbsteamid"]]
				if cbsteamid: dbteam.cbsteamid = cbsteamid
				franchiseteamid = dbteam.franchiseteamid
			dbteam.put()
			if franchiseteamid > 0:
				franchise = dygmodel.Team.all().filter("teamid = ", dbteam.franchiseteamid).fetch(1)[0]
				franchise.teamname = t["teamname"]
				if t["cbsteamid"] in teams_map:
					franchise.shortname = teams_map[t["cbsteamid"]]
				franchise.put()

def get_pickem_week():
	now_central = datetime.datetime.now().replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)

	this_year = now_central.year
	seasons = dygfantasystatsmodel.FantasySeason.all().order("-enddate").fetch(2)
	for s in seasons:
		if datetime.datetime.now().date() > s.startdate.date() - datetime.timedelta(days=7):
			this_year = s.year
			break

	weeks = dygfantasystatsmodel.PickEmWeek.all().filter("year = ", this_year).fetch(100)
	weeks = sorted(weeks, key=lambda (w): w.start_date)

	current_week = weeks[0]
	for i in range(len(weeks)):
		if weeks[i].start_date.date() + datetime.timedelta(days=4) >= now_central.date():
			current_week = weeks[i]
			break

	return current_week

class EnqueuePickemBotTasksHandler(webapp.RequestHandler):
	def get(self):
		now_central = datetime.datetime.now().replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)
		current_week = get_pickem_week()

		if now_central.date() == current_week.first_game_datetime_central().date():
			seconds_til_start = (current_week.first_game_datetime - datetime.datetime.now()).seconds - 300
			t = taskqueue.Task(url='/pickembot/cbs', method='GET', countdown=seconds_til_start)
			t.add()

class CBSPickemPicksHandler(webapp.RequestHandler):
	def get(self):
		now_central = datetime.datetime.now().replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)
		this_year = now_central.year

		teamkeyname = "t_25"

		myteam = dygchatdata.fetch_team(teamkeyname)
		entrant = dygfantasystatsmodel.PickEmEntrant.get_or_insert_by_values(franchise=myteam, year=this_year)
		entrant.name = "CRACK STAFF's THE EDGE"
		entrant.put()

		current_week = get_pickem_week()
		week_number = current_week.weeknumber

		def get_class_lambda(tag_name, class_name):
			return "lambda tag: tag.name == '%s' and \"class\" in [key for (key, value) in tag.attrs] and \"%s\" in [value.split(" ") for (key, value) in tag.attrs if key==\"class\"][0]" % (tag_name, class_name)

		cookie = get_cookie()
		edge_matchups = []
		for matchup_number in range(1, 8):
			page = dygutil.get_page(cookie, 'http://dyg.baseball.cbssports.com/scoring/preview/%s/%s' % (week_number, matchup_number))
			soup = BeautifulSoup(page, convertEntities=BeautifulSoup.HTML_ENTITIES)
			table_data_div = soup.find("div", {'class': "tableData"})
			away_info_cell = table_data_div.find(eval(get_class_lambda("div", "awayTeamInfoCell")))
			home_info_cell = table_data_div.find(eval(get_class_lambda("div", "homeTeamInfoCell")))

			away_info_anchor = 	away_info_cell.find("a")
			visitor_cbs_team_id = int(away_info_anchor['href'].split('/')[-1])

			home_info_anchor = 	home_info_cell.find("a")
			home_cbs_team_id = int(home_info_anchor['href'].split('/')[-1])

			edge_content_row = table_data_div.find("table", {'class': "edgeCont"}).find("tr", {'class': "topEdgeCont"})
			edge_score_cells = edge_content_row.findAll("td", recursive=False)
			visitor_team_score = int(edge_score_cells[0].text)
			home_team_score = int(edge_score_cells[4].text)
			edge_matchups.append({
				'home_team': {
					'cbs_team_id': home_cbs_team_id,
					'projected_points': home_team_score,
				},
				'visitor_team': {
					'cbs_team_id': visitor_cbs_team_id,
					'projected_points': visitor_team_score,
				},
				'winner_differential': abs(visitor_team_score-home_team_score),
			})

		fantasyteams = dygfantasystatsmodel.FantasyTeam.all().filter("year = ", this_year).fetch(1000)

		def getfantasyteam(cbsteamid):
			fantasyteam = None
			for t in fantasyteams:
				if t.cbsteamid == cbsteamid:
					fantasyteam = t
			return fantasyteam

		entry = dygfantasystatsmodel.PickEmEntry.get_or_insert_by_values(entrant=entrant, week=current_week, entrant_name=entrant.name)
		entry.entrant_name = entrant.name
		selections = []
		has_changes = True

		edge_matchups = sorted(edge_matchups)
		edge_matchups = sorted(edge_matchups, key=lambda (m): m['winner_differential'])
		for i in range(len(edge_matchups)):
			edge_matchups[i]['selection_weight'] = i + 1

		for matchup in current_week.matchups:
			selection = dygfantasystatsmodel.PickEmEntrySelection.get_or_insert_by_values(entry=entry, matchup=db.Key.from_path("PickEmMatchup", matchup['key_name']))
			for edge_matchup in edge_matchups:
				if edge_matchup['home_team']['cbs_team_id'] == matchup['home_team']['cbs_team_id'] and edge_matchup['visitor_team']['cbs_team_id'] == matchup['visitor_team']['cbs_team_id']:
					if edge_matchup['visitor_team']['projected_points'] > edge_matchup['home_team']['projected_points']:
						selection.selected_team = getfantasyteam(matchup['visitor_team']['cbs_team_id'])
					else:
						selection.selected_team = getfantasyteam(matchup['home_team']['cbs_team_id'])
					selection.selection_weight = edge_matchup['selection_weight']
					break
			selection.put()
			selections.append(selection.to_dict())
		entry.selections = selections
		entry.source_data = edge_matchups
		if (has_changes or not entry.submitted_datetime): # and not admin:
			entry.submitted_datetime = datetime.datetime.now()
		entry.put()

		found = False
		for i in range(len(current_week.entries)):
			if current_week.entries[i]['entrant_team']['team_id'] == entrant.franchise.teamid:
				current_week.entries[i] = entry.to_dict()
				found = True
				break
		if not found:
			current_week.entries.append(entry.to_dict())
		current_week.put()

		#t = taskqueue.Task(url='/pickembot/sal', method='GET')
		#t.add()

class SalBotPickemPicksHandler(webapp.RequestHandler):
	def get(self):
		now_central = datetime.datetime.now().replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)
		this_year = now_central.year

		teamkeyname = "t_26"
		the_edge_teamkeyname = "t_25"

		myteam = dygchatdata.fetch_team(teamkeyname)
		the_edge_team = dygchatdata.fetch_team(the_edge_teamkeyname)

		entrant = dygfantasystatsmodel.PickEmEntrant.get_or_insert_by_values(franchise=myteam, year=this_year)
		entrant.name = "SalBot"
		entrant.put()

		the_edge_entrant = dygfantasystatsmodel.PickEmEntrant.get_or_insert_by_values(franchise=the_edge_team, year=this_year)

		current_week = get_pickem_week()
		week_number = current_week.weeknumber

		fantasyteams = dygfantasystatsmodel.FantasyTeam.all().filter("year = ", this_year).fetch(1000)

		def getfantasyteam(cbsteamid):
			fantasyteam = None
			for t in fantasyteams:
				if t.cbsteamid == cbsteamid:
					fantasyteam = t
			return fantasyteam

		entry = dygfantasystatsmodel.PickEmEntry.get_or_insert_by_values(entrant=entrant, week=current_week, entrant_name=entrant.name)
		entry.entrant_name = entrant.name
		selections = []
		has_changes = True

		kn = dygfantasystatsmodel.PickEmEntry.generate_key_name(entrant=the_edge_entrant, week=current_week)
		the_edge_entry = dygfantasystatsmodel.PickEmEntry.get_by_key_name(kn)

		available_weights = [1, 2, 3, 4, 5, 6, 7]
		import random
		random.seed()
		for run_through in ["sal", "others"]:
			for matchup in current_week.matchups:
				is_sal = matchup['home_team']['cbs_team_id'] == 17 or matchup['visitor_team']['cbs_team_id'] == 17
				if run_through == "sal" and is_sal or run_through == "others" and not is_sal:
					selection = dygfantasystatsmodel.PickEmEntrySelection.get_or_insert_by_values(entry=entry, matchup=db.Key.from_path("PickEmMatchup", matchup['key_name']))
					if is_sal:
						if matchup['home_team']['cbs_team_id'] == 17:
							selection.selected_team = getfantasyteam(matchup['visitor_team']['cbs_team_id'])
						elif matchup['visitor_team']['cbs_team_id'] == 17:
							selection.selected_team = getfantasyteam(matchup['home_team']['cbs_team_id'])
						kn = dygfantasystatsmodel.PickEmEntrySelection.generate_key_name(entry=the_edge_entry, matchup=db.Key.from_path("PickEmMatchup", matchup['key_name']))
						the_edge_selection = dygfantasystatsmodel.PickEmEntrySelection.get_by_key_name(kn)
						if the_edge_selection.selected_team.cbsteamid == 17:
							opponent_favored = 1 - the_edge_selection.selection_weight
						else:
							opponent_favored = the_edge_selection.selection_weight
						selection.selection_weight = int(round((float(opponent_favored + 7)) / 2.0))
					else:
						selection.selection_weight = available_weights[random.randrange(len(available_weights))]
						if random.randrange(2) == 0:
							selection.selected_team = getfantasyteam(matchup['visitor_team']['cbs_team_id'])
						else:
							selection.selected_team = getfantasyteam(matchup['home_team']['cbs_team_id'])
					available_weights = [w for w in available_weights if w != selection.selection_weight]
					selection.put()
					selections.append(selection.to_dict())
		entry.selections = selections
		if (has_changes or not entry.submitted_datetime): # and not admin:
			entry.submitted_datetime = datetime.datetime.now()
		entry.put()

		found = False
		for i in range(len(current_week.entries)):
			if current_week.entries[i]['entrant_team']['team_id'] == entrant.franchise.teamid:
				current_week.entries[i] = entry.to_dict()
				found = True
				break
		if not found:
			current_week.entries.append(entry.to_dict())
		current_week.put()

def load_mrsports(pos):
	from google.appengine.api import urlfetch
	import dygfantasystatsmodel

	url = "http://baseball.mrsports.com/natl/gamesplayed.cfm"
	payload = "sel_pos=%s&year=2010&type=A" % pos
	response = urlfetch.fetch(url, payload, urlfetch.POST, deadline=10)

	content = response.content
	content = content[content.find("<Table CELLPADDING=3 CELLSPACING=1 BORDER=1>"):]
	content = content[:content.find("</tABLE>")]
	soup = BeautifulStoneSoup(content, convertEntities=BeautifulSoup.HTML_ENTITIES)

	for tr in soup.findAll("tr"):
		if tr.find("a"):
			tds = tr.findAll("td")
			a = tds[0].find("a")
			player_id = int(a['href'].split("=")[-1])
			full_name = a.find("b").text
			games_c = 0
			games_1b = 0
			games_2b = 0
			games_ss = 0
			games_3b = 0
			games_of = 0
			games_dh = 0
			games_rp = 0
			games_sp = 0
			if pos in ["RP", "SP"]:
				games_sp = int(tds[6].text)
				games_rp = int(tds[7].text)
			else:
				games_c = int(tds[6].text)
				games_1b = int(tds[7].text)
				games_2b = int(tds[8].text)
				games_ss = int(tds[9].text)
				games_3b = int(tds[10].text)
				games_of = int(tds[11].text)
				games_dh = int(tds[12].text)

			player_season = dygfantasystatsmodel.MrSportsPlayerSeason.all().filter("player_id = ", player_id).get()
			if not player_season:
				player_season = dygfantasystatsmodel.MrSportsPlayerSeason(
					player_id=player_id,
					year=2010,
					full_name=full_name,
					games_c=games_c,
					games_1b=games_1b,
					games_2b=games_2b,
					games_ss=games_ss,
					games_3b=games_3b,
					games_of=games_of,
					games_dh=games_dh,
					games_sp=games_sp,
					games_rp=games_rp
				)
				player_season.put()

class MrSportsHandler(webapp.RequestHandler):
	def get(self, section="mlbteams"):
		pos = self.request.get("pos")
		load_mrsports(pos)

class MrSportsHandler2(webapp.RequestHandler):
	def get(self, section="mlbteams"):
		cursor = self.request.get("cursor", default_value="")

		LIMIT = 50
		players_q = dygfantasystatsmodel.FantasyPlayerSeason.all().filter("year = ", 2010)
		if cursor: players_q.with_cursor(cursor)
		players = players_q.fetch(LIMIT)
		for player in players:
			db_player = player.player
			full_name = db_player.firstname + " " + db_player.lastname
			mrsports_players = dygfantasystatsmodel.MrSportsPlayerSeason.all().filter("full_name = ", full_name).fetch(2)
			if len(mrsports_players) == 1:
				mrsports_player = mrsports_players[0]
				mrsports_player.cbsplayerid = db_player.cbsplayerid
				mrsports_player.put()

		if len(players) == LIMIT:
			t = taskqueue.Task(url='/mrsports2', params={'cursor': players_q.cursor()},
							method='GET')
			t.add()

class MrSportsHandler3(webapp.RequestHandler):
	def get(self, section="mlbteams"):
		cursor = self.request.get("cursor", default_value="")

		LIMIT = 50
		players_q = dygfantasystatsmodel.FantasyPlayerSeason.all().filter("year = ", 2010)
		if cursor: players_q.with_cursor(cursor)
		players = players_q.fetch(LIMIT)
		for player in players:
			mrsports_players = dygfantasystatsmodel.MrSportsPlayerSeason.all().filter("cbsplayerid = ", player.cbsplayerid).fetch(2)
			if len(mrsports_players) == 1:
				mrsports_player = mrsports_players[0]
				player.games_sp = mrsports_player.games_sp
				player.games_rp = mrsports_player.games_rp
				player.games_c = mrsports_player.games_c
				player.games_1b = mrsports_player.games_1b
				player.games_2b = mrsports_player.games_2b
				player.games_3b = mrsports_player.games_3b
				player.games_ss = mrsports_player.games_ss
				player.games_of = mrsports_player.games_of
				player.games_dh = mrsports_player.games_dh
				player.put()

		if len(players) == LIMIT:
			t = taskqueue.Task(url='/mrsports3', params={'cursor': players_q.cursor()},
							method='GET')
			t.add()

class MrSportsHandler4(webapp.RequestHandler):
	def get(self, section="mlbteams"):

		if not backends.get_backend():
			t = taskqueue.Task(url='/mrsports4', target="batch", method='GET')
			t.add()
			return

		season = dygfantasystatsmodel.FantasySeason.get_or_insert_by_values(2010)

		for i in range(0, 8):
			if i == 0:
				el = "eligible_rp"
				n1 = 25
				n2 = 30
			elif i == 1:
				el = "eligible_sp"
				n1 = 125
				n2 = 150
			elif i == 2:
				el = "eligible_c"
				n1 = 25
				n2 = 30
			elif i == 3:
				el = "eligible_1b"
				n1 = 25
				n2 = 30
			elif i == 4:
				el = "eligible_2b"
				n1 = 25
				n2 = 30
			elif i == 5:
				el = "eligible_3b"
				n1 = 25
				n2 = 30
			elif i == 6:
				el = "eligible_ss"
				n1 = 25
				n2 = 30
			elif i == 7:
				el = "eligible_of"
				n1 = 75
				n2 = 90
			top = dygfantasystatsmodel.FantasyPlayer.all().filter(el + " = ", True).order("-fpts_year0_used").fetch(n2+30)
			r = 0
			for p in top:
				r += 1
				mrsports_players = dygfantasystatsmodel.MrSportsPlayerSeason.all().filter("cbsplayerid = ", p.cbsplayerid).fetch(2)
				if len(mrsports_players) <> 1:
					dbplayerseason = dygfantasystatsmodel.FantasyPlayerSeason.get_by_key_name('ps_' + p.key().name() + "_" + season.key().name())
					if not dbplayerseason or dbplayerseason.stat_fpts < 100:
						logging.info("%s %s (#%s for %s)" % (p.firstname, p.lastname, r, el))


def log_player_team_change(player, batch_cycle_id, prev_fantasyteam):
	log_item = dygfantasystatsmodel.FantasyPlayerTeamChangeLog.get_or_insert_by_values(player=player, batch_cycle_id=batch_cycle_id)
	if not log_item.prev_fantasyteam:
		log_item.prev_fantasyteam = prev_fantasyteam
	log_item.new_fantasyteam = player.fantasyteam
	log_item.put()

def http_login(url, payload):
	import urllib, urllib2

	opener = urllib2.build_opener(urllib2.HTTPErrorProcessor)
	urllib2.install_opener(opener)

	req = urllib2.Request(url, urllib.urlencode(payload))
	req.http_method = "POST"

	fc = dygutil.FixedCookie()
	try:
		response = urllib2.urlopen(req)
		fc.load(response.headers['set-cookie'])
	except urllib2.HTTPError, e:
		fc.load(e.headers['set-cookie'])

	cookie = ""
	for a, b in fc.items():
		cookie += b.key + "=" + b.value + ";"

	logging.info("cookie=" + cookie)
	return cookie

def get_page(cookie, url):
	import urllib, urllib2

	opener = urllib2.build_opener(urllib2.HTTPErrorProcessor)
	urllib2.install_opener(opener)

	req = urllib2.Request(url)
	req.add_header("cookie", cookie)
	try:
		response = urllib2.urlopen(req)
		return response.read()
	except urllib2.HTTPError, e:
		return e.fp.read()

class TestHandler(webapp.RequestHandler):
	def get(self, section="mlbteams"):
		user = 'myuser'
		password = 'mypassword'
		url = 'http://dyg.baseball.cbssports.com/standings/2012'
		cookie = dygutil.http_login('http://www.cbssports.com/login', 'xurl=http://www.cbssports.com/fantasy&master_product=150&id=' + user + '&password=' + password)
		self.response.out.write(dygutil.get_page(cookie, url))

app = webapp2.WSGIApplication([
	(r'/fantasystatsload/(.*)', StatsHandler), \
	('/fantasystatsload', StatsHandler), \
	('/pickembot/start', EnqueuePickemBotTasksHandler), \
	('/pickembot/cbs', CBSPickemPicksHandler), \
	('/pickembot/sal', SalBotPickemPicksHandler), \
	('/testload', TestHandler), \
	('/mrsports', MrSportsHandler), \
	('/mrsports2', MrSportsHandler2), \
	('/mrsports3', MrSportsHandler3), \
	('/mrsports4', MrSportsHandler4), \
	], \
								   debug=False)
