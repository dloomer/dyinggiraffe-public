#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#	  http://www.apache.org/licenses/LICENSE-2.0
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
import dygfantasystatsmodel
import dygsettingsdata
import dygchatdata

from google.appengine.ext.webapp import template
from google.appengine.ext import webapp
from google.appengine.ext import db,search
from google.appengine.api import memcache

from google.appengine.api.labs import taskqueue
#from google.appengine.api import taskqueue

def format_datetime(value, format_str):
	#import re
	#re.sub('([aAbBcdfHIjmMpSUwWxXyYzZ%])', '%\\1', format_str)
	return value.strftime(format_str).replace(' 0', ' ') if value else ""

import jinja2
jinja_environment = jinja2.Environment(
		loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))
jinja_environment.filters['datetime'] = format_datetime

logdebug = True

class SalaryHandler(webapp.RequestHandler):
	def get(self):
		firefox_win, ie_win, team_owner_name, settingsdict = get_initial_values(self)

		capsettings = dygfantasystatsmodel.SalaryCapSettings.get_by_key_name('MASTER')

		teamid = int(self.request.get("team",default_value="0"))
		teamkeyname = dygutil.getteamid(self,enforce=True)
		myteam = dygchatdata.fetch_team(teamkeyname)
		if teamid > 0:
			fantasyteam = dygfantasystatsmodel.FantasyTeam.all().filter("year = ", capsettings.current_year).filter("franchiseteamid = ", teamid).get()
		else:
			fantasyteam = dygfantasystatsmodel.FantasyTeam.all().filter("year = ", capsettings.current_year).filter("franchiseteamid = ", myteam.teamid).get()
			if not fantasyteam:
				fantasyteam = dygfantasystatsmodel.FantasyTeam.all().filter("year = ", capsettings.current_year).get()
			teamid = fantasyteam.franchiseteamid

		players = dygfantasystatsmodel.FantasyPlayer.all().filter("fantasyteam = ", fantasyteam).order("-salarycapvalue").fetch(100)
		dbteams = db.GqlQuery("SELECT * FROM FantasyTeam WHERE year=" + str(capsettings.current_year) +
							"ORDER BY teamname")
		teams = []
		for t in dbteams:
			if t.cbsteamid != None and t.cbsteamid > 0:
				teams.append(t)

		cap_points_trades = dygmodel.CapPointsTrade.all().filter("offseason_year = ", capsettings.next_year()).fetch(100)
		cap_points_trades = [trade for trade in cap_points_trades if teamid in trade.team_ids]

		cap_adjustment = 0.0
		for trade in cap_points_trades:
			from_team_id = int(dygmodel.CapPointsTrade.from_team.get_value_for_datastore(trade).name()[2:])
			to_team_id = int(dygmodel.CapPointsTrade.to_team.get_value_for_datastore(trade).name()[2:])

			if from_team_id == teamid:
				cap_adjustment -= trade.points_traded
			else:
				cap_adjustment += trade.points_traded

		keepers = dygutil.getkeeperids(self)

		total_salary = 0.0
		count_c = 0
		count_1b = 0
		count_2b = 0
		count_3b = 0
		count_ss = 0
		count_of = 0
		count_rp = 0
		count_sp = 0
		count_tot = 0
		all_players_tot = 0
		for player in players:
			# if player.weighted_fpts_2020 == None:
			# 	player.weighted_fpts_2020 = player.fpts_yearminus2 * (162.0 / 60.0)
			# 	player.fpts_3yravg = (player.fpts_year0_used + player.weighted_fpts_2020 + player.fpts_yearminus1) / 3.0
			# 	player.salarycapvalue = player.fpts_3yravg / 10.0
			if player.cbsplayerid in keepers:
				player._keeper = True
				total_salary += player.salarycapvalue
				if player.nextyr_eligible_c: count_c += 1
				if player.nextyr_eligible_1b: count_1b += 1
				if player.nextyr_eligible_2b: count_2b += 1
				if player.nextyr_eligible_3b: count_3b += 1
				if player.nextyr_eligible_ss: count_ss += 1
				if player.nextyr_eligible_of: count_of += 1
				if player.nextyr_eligible_rp: count_rp += 1
				if player.nextyr_eligible_sp: count_sp += 1
				count_tot += 1
			else:
				player._keeper = False
			all_players_tot += 1

		ismyteam = (fantasyteam.franchiseteamid == myteam.teamid)
		capvalue_total = 500.0
		template_values = {
			'team_owner_name': team_owner_name,
			'theme': settingsdict["theme"],
			'firefox_win': firefox_win,
			'team': fantasyteam,
			'teams': teams,
			'ismyteam': ismyteam,
			'players': players,
			'capsettings': capsettings,
			'total_salary': total_salary,
			'cap_adjustment': cap_adjustment,
			'capvalue_total': capvalue_total,
			'adjusted_capvalue_total': capvalue_total+cap_adjustment,
			'count_c': count_c,
			'count_1b': count_1b,
			'count_2b': count_2b,
			'count_3b': count_3b,
			'count_ss': count_ss,
			'count_of': count_of,
			'count_rp': count_rp,
			'count_sp': count_sp,
			'count_tot': count_tot,
			'ie_win': ie_win,
			'all_players_tot': all_players_tot,
		}
		template = jinja_environment.get_template('templates/salary.html')
		self.response.out.write(template.render(template_values))

'''
To change an entry:
import dygfantasystatsmodel, dygutil, dygchatdata
import datetime

now_central = datetime.datetime.now().replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)

this_year = 2014
teamkeyname = "t_7"
week_number = 16

myteam = dygchatdata.fetch_team(teamkeyname)
entrant = dygfantasystatsmodel.PickEmEntrant.get_or_insert_by_values(franchise=myteam, year=this_year)

current_week = dygfantasystatsmodel.PickEmWeek.all().filter("year = ", this_year).filter("weeknumber = ", week_number).get()
fantasyteams = dygfantasystatsmodel.FantasyTeam.all().filter("year = ", this_year).fetch(1000)

def getfantasyteam(cbsteamid):
	fantasyteam = None
	for t in fantasyteams:
		if t.cbsteamid == cbsteamid:
			fantasyteam = t
	return fantasyteam

entry = dygfantasystatsmodel.PickEmEntry.get_or_insert_by_values(entrant=entrant, week=current_week)
selections = []
has_changes = False
for matchup in current_week.matchups:
	selection = dygfantasystatsmodel.PickEmEntrySelection.get_or_insert_by_values(entry=entry, matchup=db.Key.from_path("PickEmMatchup", matchup['key_name']))
	if matchup['key_name'] == "y_2014_w_16_v_8_h_14":
		selected_cbs_team_id = 17
		selected_weight = 7
		if selected_cbs_team_id > 0 and selected_weight > 0:
			if selected_cbs_team_id != selection.selected_cbs_team_id:
				selection.selected_team = getfantasyteam(selected_cbs_team_id)
				has_changes = True
			if selected_weight != selection.selection_weight:
				selection.selection_weight = selected_weight
				has_changes = True
			selection.put()
	selections.append(selection.to_dict())
entry.selections = selections
#if (has_changes or not entry.submitted_datetime):
#	entry.submitted_datetime = datetime.datetime.now()
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

'''
class PickemHandler(webapp.RequestHandler):
	def post(self):
		now_central = datetime.datetime.now().replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)
		this_year = now_central.year

		teamkeyname = dygutil.getteamid(self,enforce=True)
		if teamkeyname is None or teamkeyname == "": return

		admin = teamkeyname == "t_1"
		if admin:
			teamid = int(self.request.get("team",default_value="0"))
			if teamid: teamkeyname = "t_%s" % teamid

		myteam = dygchatdata.fetch_team(teamkeyname)
		entrant = dygfantasystatsmodel.PickEmEntrant.get_or_insert_by_values(franchise=myteam, year=this_year)
		entrant.name = self.request.get('entrant_name')
		entrant.put()

		week_number = int(self.request.get("_week"))
		current_week = dygfantasystatsmodel.PickEmWeek.all().filter("year = ", this_year).filter("weeknumber = ", week_number).get()
		if now_central > current_week.entry_deadline_datetime_central() and not admin:
			self.get()
			return

		fantasyteams = dygfantasystatsmodel.FantasyTeam.all().filter("year = ", this_year).fetch(1000)

		def getfantasyteam(cbsteamid):
			fantasyteam = None
			for t in fantasyteams:
				if t.cbsteamid == cbsteamid:
					fantasyteam = t
			return fantasyteam

		entry = dygfantasystatsmodel.PickEmEntry.get_or_insert_by_values(entrant=entrant, week=current_week, entrant_name=self.request.get('entrant_name'))
		entry.entrant_name = self.request.get('entrant_name')
		selections = []
		has_changes = False
		for matchup in current_week.matchups:
			selected_cbs_team_id = int(self.request.get("selection_" + matchup['key_name'], default_value="0"))
			selected_weight = int(self.request.get("weight_" + matchup['key_name'], default_value="0"))
			if selected_cbs_team_id > 0 and selected_weight > 0:
				selection = dygfantasystatsmodel.PickEmEntrySelection.get_or_insert_by_values(entry=entry, matchup=db.Key.from_path("PickEmMatchup", matchup['key_name']))
				if selected_cbs_team_id != selection.selected_cbs_team_id:
					selection.selected_team = getfantasyteam(selected_cbs_team_id)
					has_changes = True
				if selected_weight != selection.selection_weight:
					selection.selection_weight = selected_weight
					has_changes = True
				selection.put()
				selections.append(selection.to_dict())
		entry.selections = selections
		if (has_changes or not entry.submitted_datetime): # and week_number != 3:
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

		self.get()

	def get(self):
		import copy
		firefox_win, ie_win, team_owner_name, settingsdict = get_initial_values(self)
		week_number = int(self.request.get("week",default_value="0"))
		reveal = self.request.get("reveal", default_value="false").lower() == "true"

		now_central = datetime.datetime.now().replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)

		this_year = now_central.year
		seasons = dygfantasystatsmodel.FantasySeason.all().order("-enddate").fetch(2)
		for s in seasons:
			if datetime.datetime.now().date() > s.startdate.date() - datetime.timedelta(days=7):
				this_year = s.year
				break

		weeks = dygfantasystatsmodel.PickEmWeek.all().filter("year = ", this_year).fetch(100)
		weeks = sorted(weeks, key=lambda (w): w.start_date)

		teamkeyname = dygutil.getteamid(self,enforce=True)
		if teamkeyname is None or teamkeyname == "": return

		admin = teamkeyname == "t_1"
		if admin:
			teamid = int(self.request.get("team",default_value="0"))
			if teamid: teamkeyname = "t_%s" % teamid
		myteam = dygchatdata.fetch_team(teamkeyname)

		entrant = dygfantasystatsmodel.PickEmEntrant.get_or_insert_by_values(franchise=myteam, year=this_year)

		if week_number == 0:
			current_week = weeks[0]
			for i in range(len(weeks)-1, -1, -1):
				if weeks[i].start_date.date() - datetime.timedelta(days=2) <= now_central.date():
					current_week = weeks[i]
					break
		else:
			current_week = weeks[week_number-1]

		current_week_matchups = sorted(current_week.matchups, key=lambda (m): m['home_team']['cbs_team_id'])
		my_matchups = copy.deepcopy(current_week_matchups)

		entry = dygfantasystatsmodel.PickEmEntry.get_by_key_name(dygfantasystatsmodel.PickEmEntry.generate_key_name(entrant=entrant, week=current_week))
		if entry:
			entrant_name = entry.entrant_name

			for selection in entry.selections:
				for matchup in my_matchups:
					if matchup['key_name'] == selection['matchup']['key_name']:
						matchup['selection'] = selection
		else:
			entrant_name = entrant.name

		entry_deadline_datetime_central = current_week.entry_deadline_datetime_central()
		import logging
		logging.info("entry_deadline_datetime_central=%s" % entry_deadline_datetime_central)
		if entry_deadline_datetime_central:
			is_editable = now_central < entry_deadline_datetime_central
		else:
			is_editable = now_central < current_week.start_date
		if reveal and admin: is_editable = False
		#if admin:
		#	is_editable = True
		first_game_datetime_central = current_week.first_game_datetime_central()
		if first_game_datetime_central:
			now_is_late = now_central >= first_game_datetime_central
		else:
			now_is_late = now_central >= current_week.start_date
		entry_is_late = entry.submitted_datetime > current_week.first_game_datetime if entry and entry.submitted_datetime else False
		submitted_datetime_central = entry.submitted_datetime.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()) if entry and entry.submitted_datetime else None

		week_has_final_scores = False

		if is_editable:
			picks_grid = []
		else:
			picks_grid = {'matchups': current_week_matchups, 'entries': []}
			for entry in current_week.entries:
				entry_row = {'team': entry['entrant_team'], 'selections': [matchup.copy() for matchup in current_week_matchups], 'total_score': 0, 'is_late': entry['is_late']}
				if entry['is_late']:
					entry_row['late_duration_str'] = entry['late_duration_str']
				for matchup in entry_row['selections']:
					#if matchup.get('selection') is None:
					#	matchup['selection'] = {'selected_team': {'team_abbrev': ""}}
					for entry_selection in entry['selections']:
						if entry_selection['matchup']['key_name'] == matchup['key_name']:
							if matchup['home_team']['final_points'] > matchup['visitor_team']['final_points']:
								winner_cbs_team_id = matchup['home_team']['cbs_team_id']
							elif matchup['visitor_team']['final_points'] > matchup['home_team']['final_points']:
								winner_cbs_team_id = matchup['visitor_team']['cbs_team_id']
							else:
								winner_cbs_team_id = 0
							if winner_cbs_team_id: week_has_final_scores = True
							if entry_selection['selected_team']['cbs_team_id'] == matchup['home_team']['cbs_team_id']:
								entry_selection['selected_team']['team_name'] = matchup['home_team']['team_name']
								entry_selection['selected_team']['team_abbrev'] = matchup['home_team']['team_abbrev']
							else:
								entry_selection['selected_team']['team_name'] = matchup['visitor_team']['team_name']
								entry_selection['selected_team']['team_abbrev'] = matchup['visitor_team']['team_abbrev']
							entry_selection['is_correct'] = entry_selection['selected_team']['cbs_team_id'] == winner_cbs_team_id
							if entry_selection['is_correct']:
								entry_row['total_score'] += entry_selection['selection_weight']
							matchup['selection'] = entry_selection
							break
				picks_grid['entries'].append(entry_row)

		week_numbers = [week.weeknumber for week in weeks]
		template_values = {
			'team_owner_name': team_owner_name,
			'theme': settingsdict["theme"],
			'firefox_win': firefox_win,
			'week_numbers': week_numbers,
			'current_week': current_week,
			'my_matchups': my_matchups,
			'entrant': entrant,
			'entrant_name': entrant_name,
			'is_editable': is_editable,
			'now_is_late': now_is_late,
			'submitted_datetime_central': submitted_datetime_central,
			'entry_is_late': entry_is_late,
			'picks_grid': picks_grid,
			'week_has_final_scores': week_has_final_scores,
		}
		logging.info("picks_grid=%s" % picks_grid)
		template = jinja_environment.get_template('templates/pickem.html')
		self.response.out.write(template.render(template_values))

class PickemStandingsHandler(webapp.RequestHandler):
	def get(self):
		firefox_win, ie_win, team_owner_name, settingsdict = get_initial_values(self)

		now_central = datetime.datetime.now().replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)

		this_year = now_central.year
		seasons = dygfantasystatsmodel.FantasySeason.all().order("-enddate").fetch(2)
		for s in seasons:
			if datetime.datetime.now().date() > s.startdate.date() - datetime.timedelta(days=7):
				this_year = s.year
				break

		weeks = dygfantasystatsmodel.PickEmWeek.all().filter("year = ", this_year).fetch(100)
		# scores should be finalized around 7am.
		weeks = [week for week in weeks if week.end_date.date() < (now_central - datetime.timedelta(hours=7)).date()]
		weeks = sorted(weeks, key=lambda (w): w.start_date)

		teamkeyname = dygutil.getteamid(self,enforce=True)
		if teamkeyname is None or teamkeyname == "": return

		myteam = dygchatdata.fetch_team(teamkeyname)

		entrant = dygfantasystatsmodel.PickEmEntrant.get_or_insert_by_values(franchise=myteam, year=this_year)

		standings_grid = {'weeks': weeks, 'entrants': []}
		for week_index in range(len(weeks)):
			week = weeks[week_index]
			matchups_dict = {}
			for matchup in week.matchups:
				if matchup['home_team']['final_points'] > matchup['visitor_team']['final_points']:
					winner_cbs_team_id = matchup['home_team']['cbs_team_id']
				elif matchup['visitor_team']['final_points'] > matchup['home_team']['final_points']:
					winner_cbs_team_id = matchup['visitor_team']['cbs_team_id']
				else:
					winner_cbs_team_id = 0
				matchups_dict[matchup['key_name']] = {'winner_cbs_team_id': winner_cbs_team_id}
			import logging
			logging.debug("matchups_dict=%s" % matchups_dict)
			for week_entry in week.entries:
				standings_entrant = None
				for _standings_entrant in standings_grid['entrants']:
					if _standings_entrant['team_id'] == week_entry['entrant_team']['team_id']:
						standings_entrant = _standings_entrant
						break
				if not standings_entrant:
					standings_entrant = {'team_id': week_entry['entrant_team']['team_id'], 'week_scores': [], 'total_score': 0}
					for i in range(len(weeks)):
						standings_entrant['week_scores'].append({'score': -1, 'is_late': False})
					standings_grid['entrants'].append(standings_entrant)
				standings_entrant['name'] = week_entry['entrant_team']['name']
				week_score = 0
				for selection in week_entry['selections']:
					winner_cbs_team_id = matchups_dict[selection['matchup']['key_name']]['winner_cbs_team_id']
					if selection['selected_team']['cbs_team_id'] == winner_cbs_team_id:
						week_score += selection['selection_weight']
				standings_entrant['week_scores'][week_index] = {'score': week_score, 'is_late': week_entry['is_late']}
				if week_entry['is_late']:
					standings_entrant['week_scores'][week_index]['late_duration_str'] = week_entry['late_duration_str']
				standings_entrant['total_score'] += week_score

		standings_grid['entrants'] = sorted(standings_grid['entrants'], key=lambda (e): e['total_score'], reverse=True)

		template_values = {
			'team_owner_name': team_owner_name,
			'theme': settingsdict["theme"],
			'firefox_win': firefox_win,
			'entrant': entrant,
			'standings_grid': standings_grid,
		}
		template = jinja_environment.get_template('templates/pickem_standings.html')
		self.response.out.write(template.render(template_values))

'''
t_1 Staines
t_2 Trent
t_5 Chone
t_6 Cyrus
t_7 Nuke
t_8 Ben
t_9 PJ
t_10 Vandelay
t_12 Dogger
t_13 KEITH
t_21 Joe
t_22 Tabler / TJ
t_24 Shellers
t_27 Jimmy
t_28 Hrabosky
t_29 Canseco
offseason_year = next season

import dygmodel

# 2019
# 7 cap points from TJ to 1984 (Peralta)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_22'),
	to_team=dygmodel.Team.get_by_key_name('t_13'),
	points_traded=7.0,
	trade_date=datetime.date(2019, 2, 9),
	offseason_year=2019,
)
trade.put()

# 15 cap points from Al to Canseco (Cain)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_28'),
	to_team=dygmodel.Team.get_by_key_name('t_29'),
	points_traded=15.0,
	trade_date=datetime.date(2019, 2, 12),
	offseason_year=2019,
)
trade.put()

# 25 cap points from TJ to Shellers (Mazara)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_22'),
	to_team=dygmodel.Team.get_by_key_name('t_24'),
	points_traded=25.0,
	trade_date=datetime.date(2019, 2, 13),
	offseason_year=2019,
)
trade.put()

# 2018
# 15 points from Hrabosky to Trent (Wentz)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_28'),
	to_team=dygmodel.Team.get_by_key_name('t_2'),
	points_traded=15.0,
	trade_date=datetime.date(2018, 3, 17),
	offseason_year=2018,
)
trade.put()

# 2 points from Hrabosky to Vandelay (4th round pick)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_28'),
	to_team=dygmodel.Team.get_by_key_name('t_10'),
	points_traded=2.0,
	trade_date=datetime.date(2018, 3, 17),
	offseason_year=2018,
)
trade.put()

# 12 points from Hrabosky to Chone (picks)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_28'),
	to_team=dygmodel.Team.get_by_key_name('t_5'),
	points_traded=12.0,
	trade_date=datetime.date(2018, 3, 17),
	offseason_year=2018,
)
trade.put()

# 10 points from Tabler to Vandelay (Sano/Brantley)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_22'),
	to_team=dygmodel.Team.get_by_key_name('t_10'),
	points_traded=10.0,
	trade_date=datetime.date(2018, 3, 17),
	offseason_year=2018,
)
trade.put()

# 6 points from Hrabosky to 1984 (Gyorko)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_28'),
	to_team=dygmodel.Team.get_by_key_name('t_13'),
	points_traded=6.0,
	trade_date=datetime.date(2018, 3, 15),
	offseason_year=2018,
)
trade.put()

# 15 points from Hrabosky to PJ (4th round pick)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_28'),
	to_team=dygmodel.Team.get_by_key_name('t_9'),
	points_traded=15.0,
	trade_date=datetime.date(2018, 3, 16),
	offseason_year=2018,
)
trade.put()

# 16 points from Tabler to Shellers (Realmuto)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_22'),
	to_team=dygmodel.Team.get_by_key_name('t_24'),
	points_traded=16.0,
	trade_date=datetime.date(2018, 3, 12),
	offseason_year=2018,
)
trade.put()

# 5.2 points from Nuke to Canseco (Scherzer / Robles / Tucker / etc)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_7'),
	to_team=dygmodel.Team.get_by_key_name('t_29'),
	points_traded=5.2,
	trade_date=datetime.date(2018, 3, 9),
	offseason_year=2018,
)
trade.put()

# 8.37 points from Ben to Shellers (5th round pick)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_8'),
	to_team=dygmodel.Team.get_by_key_name('t_24'),
	points_traded=8.37,
	trade_date=datetime.date(2018, 3, 6),
	offseason_year=2018,
)
trade.put()

# 2017
# 3.5 cap points to Nate from Chone (draft pick swap)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_5'),
	to_team=dygmodel.Team.get_by_key_name('t_10'),
	points_traded=3.5,
	trade_date=datetime.date(2017, 3, 13),
	offseason_year=2017,
)
trade.put()

# 22 cap points to Tabler from Jimmy (Molina)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_27'),
	to_team=dygmodel.Team.get_by_key_name('t_15'),
	points_traded=22.0,
	trade_date=datetime.date(2017, 3, 13),
	offseason_year=2017,
)
trade.put()

# 4.9 cap points to Cyrus from Ben (round 4 pick)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_8'),
	to_team=dygmodel.Team.get_by_key_name('t_6'),
	points_traded=4.9,
	trade_date=datetime.date(2017, 3, 13),
	offseason_year=2017,
)
trade.put()

# 5 cap points to Trent from Moneyballers (Honeywell)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_27'),
	to_team=dygmodel.Team.get_by_key_name('t_2'),
	points_traded=5.0,
	trade_date=datetime.date(2017, 3, 12),
	offseason_year=2017,
)
trade.put()

# 25 cap points to Stains from Moneyballers (Reyes)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_27'),
	to_team=dygmodel.Team.get_by_key_name('t_1'),
	points_traded=25.0,
	trade_date=datetime.date(2016, 12, 19),
	offseason_year=2017,
)
trade.put()

# 15 Cap Point to Shellers from Tabler (Brantley)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_22'),
	to_team=dygmodel.Team.get_by_key_name('t_24'),
	points_traded=15.0,
	trade_date=datetime.date(2016, 12, 19),
	offseason_year=2017,
)
trade.put()

# 22 Cap Points to KEITH from Tabler (Kennedy)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_22'),
	to_team=dygmodel.Team.get_by_key_name('t_13'),
	points_traded=22.0,
	trade_date=datetime.date(2016, 12, 20),
	offseason_year=2017,
)
trade.put()

# 23 Cap Points to Nuke from Tabler (Bauer)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_22'),
	to_team=dygmodel.Team.get_by_key_name('t_7'),
	points_traded=23.0,
	trade_date=datetime.date(2016, 12, 27),
	offseason_year=2017,
)
trade.put()

# 4 Cap points to Shellers from Expos (Springer)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_6'),
	to_team=dygmodel.Team.get_by_key_name('t_24'),
	points_traded=4.0,
	trade_date=datetime.date(2016, 12, 27),
	offseason_year=2017,
)
trade.put()

# 2 Cap points to Nuke from Moneyballers (Melky)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_27'),
	to_team=dygmodel.Team.get_by_key_name('t_7'),
	points_traded=2.0,
	trade_date=datetime.date(2016, 12, 30),
	offseason_year=2017,
)
trade.put()

# 6 Cap points to Sheller from Moneyballers (Rosario)
trade = dygmodel.CapPointsTrade(
	from_team=dygmodel.Team.get_by_key_name('t_27'),
	to_team=dygmodel.Team.get_by_key_name('t_24'),
	points_traded=6.0,
	trade_date=datetime.date(2017, 1, 5),
	offseason_year=2017,
)
trade.put()
'''
class CapTradesHandler(webapp.RequestHandler):
	def get(self):
		trade = dygmodel.CapPointsTrade(
			from_team=dygmodel.Team.get_by_key_name('t_24'),
			to_team=dygmodel.Team.get_by_key_name('t_6'),
			points_traded=25.0,
			trade_date=datetime.date(2016, 12, 20),
			offseason_year=2016,
		)
		trade.put()

		trade = dygmodel.CapPointsTrade(
			from_team=dygmodel.Team.get_by_key_name('t_27'),
			to_team=dygmodel.Team.get_by_key_name('t_7'),
			points_traded=25.0,
			trade_date=datetime.date(2015, 11, 17),
			offseason_year=2016,
		)
		trade.put()

def get_initial_values(handler):
	browserinfo = dygutil.get_browser_info(handler.request)
	firefox_win = (browserinfo['browser'] == "firefox" and browserinfo["os"] == "windows")
	ie_win = (browserinfo['browser'] == "ie" and browserinfo["os"] == "windows")

	team_owner_name = dygchatdata.fetch_team_ownername(dygutil.getteamid(handler,enforce=True))

	latestsettings = dygsettingsdata.get_latest_settings()
	settingsdict = latestsettings.to_dict()

	return firefox_win, ie_win, team_owner_name, settingsdict

app = webapp2.WSGIApplication([
		('/fantasy/salary', SalaryHandler), \
		('/fantasy/pickem', PickemHandler), \
		('/fantasy/pickem/standings', PickemStandingsHandler), \
		('/fantasy', SalaryHandler), \
		('/cap_trades', CapTradesHandler), \
		], \
									   debug=False)
