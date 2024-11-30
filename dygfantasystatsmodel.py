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

import datetime

from google.appengine.ext import db,search
from google.appengine.api import datastore_types

import dygutil
import dygchatdata
import logging
import dygmodel
import string

logdebug = True

class MLBTeam(db.Model):
	teamcode = db.StringProperty(required=True)
	teamname = db.StringProperty()
	wins = db.IntegerProperty(required=True,default=0)
	losses = db.IntegerProperty(required=True,default=0)
	games = db.IntegerProperty(required=True,default=0)
	endseasongames = db.IntegerProperty(required=True,default=162)

	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		self.games = self.wins + self.losses
		if self.endseasongames < self.games:
			self.endseasongames = self.games

class SalaryCapSettings(db.Model):
	current_year = db.IntegerProperty(required=True, default=datetime.datetime.now().year)
	capvalue_rp_25 = db.FloatProperty(default=0.0)
	capvalue_rp_30 = db.FloatProperty(default=0.0)
	capvalue_rp = db.FloatProperty()
	capvalue_sp_125 = db.FloatProperty(default=0.0)
	capvalue_sp_150 = db.FloatProperty(default=0.0)
	capvalue_sp = db.FloatProperty()
	capvalue_c_25 = db.FloatProperty(default=0.0)
	capvalue_c_30 = db.FloatProperty(default=0.0)
	capvalue_c = db.FloatProperty()
	capvalue_1b_25 = db.FloatProperty(default=0.0)
	capvalue_1b_30 = db.FloatProperty(default=0.0)
	capvalue_1b = db.FloatProperty()
	capvalue_2b_25 = db.FloatProperty(default=0.0)
	capvalue_2b_30 = db.FloatProperty(default=0.0)
	capvalue_2b = db.FloatProperty()
	capvalue_3b_25 = db.FloatProperty(default=0.0)
	capvalue_3b_30 = db.FloatProperty(default=0.0)
	capvalue_3b = db.FloatProperty()
	capvalue_ss_25 = db.FloatProperty(default=0.0)
	capvalue_ss_30 = db.FloatProperty(default=0.0)
	capvalue_ss = db.FloatProperty()
	capvalue_of_75 = db.FloatProperty(default=0.0)
	capvalue_of_90 = db.FloatProperty(default=0.0)
	capvalue_of = db.FloatProperty()
	capvalue_dh_25 = db.FloatProperty(default=0.0)
	capvalue_dh_30 = db.FloatProperty(default=0.0)
	capvalue_dh = db.FloatProperty()
	capvalue_other = db.FloatProperty(default=0.0)
	capvalue_total = db.FloatProperty()
	updatedate = db.DateTimeProperty()

	def current_year_minus_1(self):
		return self.current_year - 1

	def current_year_minus_2(self):
		return self.current_year - 2

	def next_year(self):
		return self.current_year + 1

	def displayupdatedate(self):
		return self.updatedate.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).strftime('%A %m/%d/%Y %I:%M:%S %p')

	def put(self):
		self.set_calculated_fields()
		self.updatedate = datetime.datetime.now()
		return db.Model.put(self)
	def set_calculated_fields(self):
		self.capvalue_rp = (self.capvalue_rp_25 + self.capvalue_rp_30) / 2.0
		self.capvalue_sp = (self.capvalue_sp_125 + self.capvalue_sp_150) / 2.0
		self.capvalue_c = (self.capvalue_c_25 + self.capvalue_c_30) / 2.0
		self.capvalue_1b = (self.capvalue_1b_25 + self.capvalue_1b_30) / 2.0
		self.capvalue_2b = (self.capvalue_2b_25 + self.capvalue_2b_30) / 2.0
		self.capvalue_3b = (self.capvalue_3b_25 + self.capvalue_3b_30) / 2.0
		self.capvalue_ss = (self.capvalue_ss_25 + self.capvalue_ss_30) / 2.0
		self.capvalue_of = (self.capvalue_of_75 + self.capvalue_of_90) / 2.0
		self.capvalue_dh = (self.capvalue_c + self.capvalue_1b + self.capvalue_2b + self.capvalue_3b + self.capvalue_ss + 3.0 * self.capvalue_of) / 8.0
		self.capvalue_total = self.capvalue_rp + self.capvalue_sp * 5.0 + self.capvalue_c + self.capvalue_1b + self.capvalue_2b + self.capvalue_3b + self.capvalue_ss + self.capvalue_of * 3.0 + self.capvalue_dh + self.capvalue_other


class FantasySeason(db.Model):
	year = db.IntegerProperty(required=True)
	startdate = db.DateTimeProperty()
	enddate = db.DateTimeProperty()
	is_final = db.BooleanProperty(required=True,default=False)
	p_captotal = db.IntegerProperty()
	c_captotal = db.IntegerProperty()
	b_1b_captotal = db.IntegerProperty()
	b_2b_captotal = db.IntegerProperty()
	b_3b_captotal = db.IntegerProperty()
	ss_captotal = db.IntegerProperty()
	of_captotal = db.IntegerProperty()
	dh_captotal = db.IntegerProperty()
	all_captotal = db.IntegerProperty()
	games = db.IntegerProperty()
	totalweeks = db.IntegerProperty()
	hittingpoints = db.IntegerProperty(default=0)
	pitchingpoints = db.IntegerProperty(default=0)
	startingpitchingpoints = db.IntegerProperty(default=0)
	totalpoints = db.IntegerProperty(default=0)
	hittingpoints14 = db.IntegerProperty(default=0)
	pitchingpoints14 = db.IntegerProperty(default=0)
	startingpitchingpoints14 = db.IntegerProperty(default=0)
	totalpoints14 = db.IntegerProperty(default=0)
	medianhittingpoints = db.FloatProperty(default=0.0)
	medianhittingpoints14 = db.FloatProperty(default=0.0)
	medianpitchingpoints = db.FloatProperty(default=0.0)
	medianpitchingpoints14 = db.FloatProperty(default=0.0)
	medianstartingpitchingpoints = db.FloatProperty(default=0.0)
	medianstartingpitchingpointsperstart = db.FloatProperty(default=0.0)
	medianstartingpitchingpoints14 = db.FloatProperty(default=0.0)
	medianstartingpitchingpointsperstart14 = db.FloatProperty(default=0.0)
	mediantotalpoints = db.FloatProperty(default=0.0)
	mediantotalpoints_old = db.FloatProperty(default=0.0)
	mediantotalpoints14_old = db.FloatProperty(default=0.0)
	medianhittingpoints_old = db.FloatProperty(default=0.0)
	medianhittingpoints14_old = db.FloatProperty(default=0.0)
	medianpitchingpoints_old = db.FloatProperty(default=0.0)
	medianpitchingpoints14_old = db.FloatProperty(default=0.0)
	medianstartingpitchingpoints_old = db.FloatProperty(default=0.0)
	medianstartingpitchingpointsperstart_old = db.FloatProperty(default=0.0)
	medianstartingpitchingpoints14_old = db.FloatProperty(default=0.0)
	medianstartingpitchingpointsperstart14_old = db.FloatProperty(default=0.0)
	mediantotalpoints_old = db.FloatProperty(default=0.0)
	mediantotalpoints14_old = db.FloatProperty(default=0.0)
	leadergamesabove500 = db.IntegerProperty(default=0)

	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		pass

	@staticmethod
	def get_or_insert_by_values(year):
		count = 0
		while True:
			try:
				return FantasySeason.get_or_insert("y_" + str(year),
					year=year)
			except db.Timeout:
				count += 1
				if count == 3:
					raise

class FantasyWeek(db.Model):
	season = db.ReferenceProperty(FantasySeason, required=True)
	year = db.IntegerProperty(required=True)
	weeknumber = db.IntegerProperty(required=True)
	games = db.IntegerProperty(default=0)
	totalweeks = db.IntegerProperty(default=0)
	hittingpoints = db.IntegerProperty(default=0)
	pitchingpoints = db.IntegerProperty(default=0)
	startingpitchingpoints = db.IntegerProperty(default=0)
	totalpoints = db.IntegerProperty(default=0)
	hittingpoints14 = db.IntegerProperty(default=0)
	pitchingpoints14 = db.IntegerProperty(default=0)
	startingpitchingpoints14 = db.IntegerProperty(default=0)
	totalpoints14 = db.IntegerProperty(default=0)
	medianhittingpoints = db.FloatProperty(default=0.0)
	medianhittingpoints14 = db.FloatProperty(default=0.0)
	medianpitchingpoints = db.FloatProperty(default=0.0)
	medianpitchingpoints14 = db.FloatProperty(default=0.0)
	medianstartingpitchingpoints = db.FloatProperty(default=0.0)
	medianstartingpitchingpointsperstart = db.FloatProperty(default=0.0)
	medianstartingpitchingpoints14 = db.FloatProperty(default=0.0)
	medianstartingpitchingpointsperstart14 = db.FloatProperty(default=0.0)
	mediantotalpoints = db.FloatProperty(default=0.0)
	mediantotalpoints_old = db.FloatProperty(default=0.0)
	mediantotalpoints14_old = db.FloatProperty(default=0.0)
	medianhittingpoints_old = db.FloatProperty(default=0.0)
	medianhittingpoints14_old = db.FloatProperty(default=0.0)
	medianpitchingpoints_old = db.FloatProperty(default=0.0)
	medianpitchingpoints14_old = db.FloatProperty(default=0.0)
	medianstartingpitchingpoints_old = db.FloatProperty(default=0.0)
	medianstartingpitchingpointsperstart_old = db.FloatProperty(default=0.0)
	medianstartingpitchingpoints14_old = db.FloatProperty(default=0.0)
	medianstartingpitchingpointsperstart14_old = db.FloatProperty(default=0.0)
	mediantotalpoints_old = db.FloatProperty(default=0.0)
	mediantotalpoints14_old = db.FloatProperty(default=0.0)
	leadergamesabove500 = db.IntegerProperty(default=0)
	startdate = db.DateTimeProperty()
	enddate = db.DateTimeProperty()
	is_final = db.BooleanProperty(required=True,default=False)

	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		pass

	@staticmethod
	def get_or_insert_by_values(season, weeknumber):
		count = 0
		while True:
			try:
				return FantasyWeek.get_or_insert(season.key().name() + "_w_" + str(weeknumber),
					season=season, year=season.year, weeknumber=weeknumber)
			except db.Timeout:
				count += 1
				if count == 3:
					raise


class FantasyAllTime(db.Model):
	startdate = db.DateTimeProperty()
	enddate = db.DateTimeProperty()
	games = db.IntegerProperty()
	totalweeks = db.IntegerProperty(default=0)
	totalseasons = db.IntegerProperty(default=0)
	hittingpoints = db.IntegerProperty(default=0)
	pitchingpoints = db.IntegerProperty(default=0)
	startingpitchingpoints = db.IntegerProperty(default=0)
	totalpoints = db.IntegerProperty(default=0)
	hittingpoints14 = db.IntegerProperty(default=0)
	pitchingpoints14 = db.IntegerProperty(default=0)
	startingpitchingpoints14 = db.IntegerProperty(default=0)
	totalpoints14 = db.IntegerProperty(default=0)
	medianhittingpoints = db.FloatProperty(default=0.0)
	medianhittingpoints14 = db.FloatProperty(default=0.0)
	medianpitchingpoints = db.FloatProperty(default=0.0)
	medianpitchingpoints14 = db.FloatProperty(default=0.0)
	medianstartingpitchingpoints = db.FloatProperty(default=0.0)
	medianstartingpitchingpointsperstart = db.FloatProperty(default=0.0)
	medianstartingpitchingpoints14 = db.FloatProperty(default=0.0)
	medianstartingpitchingpointsperstart14 = db.FloatProperty(default=0.0)
	mediantotalpoints = db.FloatProperty(default=0.0)
	mediantotalpoints_old = db.FloatProperty(default=0.0)
	mediantotalpoints14_old = db.FloatProperty(default=0.0)
	medianhittingpoints_old = db.FloatProperty(default=0.0)
	medianhittingpoints14_old = db.FloatProperty(default=0.0)
	medianpitchingpoints_old = db.FloatProperty(default=0.0)
	medianpitchingpoints14_old = db.FloatProperty(default=0.0)
	medianstartingpitchingpoints_old = db.FloatProperty(default=0.0)
	medianstartingpitchingpointsperstart_old = db.FloatProperty(default=0.0)
	medianstartingpitchingpoints14_old = db.FloatProperty(default=0.0)
	medianstartingpitchingpointsperstart14_old = db.FloatProperty(default=0.0)
	mediantotalpoints_old = db.FloatProperty(default=0.0)
	mediantotalpoints14_old = db.FloatProperty(default=0.0)
	leadergamesabove500 = db.IntegerProperty(default=0)

	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		pass

class FantasyTeam(db.Model):
	franchiseteamid = db.IntegerProperty(required=True,default=0)
	year = db.IntegerProperty(required=True)
	teamname = db.StringProperty(required=True)
	shortname = db.StringProperty()
	cbsteamid = db.IntegerProperty(required=True,default=0)
	franchise = db.ReferenceProperty(dygmodel.Team)
	season = db.ReferenceProperty(FantasySeason)
	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		if self.franchiseteamid > 0:
			self.franchise = dygmodel.Team.all().filter("teamid = ", self.franchiseteamid).fetch(1)[0]
		else:
			self.franchise = None
		self.season = FantasySeason.get_or_insert_by_values(self.year)

class FantasyPlayer(db.Model):
	cbsplayerid = db.IntegerProperty(required=True)
	firstname = db.StringProperty(indexed=False)
	lastname = db.StringProperty(indexed=False)
	primaryposition = db.StringProperty()
	mlbteamcode = db.StringProperty(indexed=False)
	birthdate = db.DateTimeProperty(indexed=False)
	age = db.IntegerProperty(indexed=False)
	fantasyteam = db.ReferenceProperty(FantasyTeam)
	eligible_rp = db.BooleanProperty(required=True,default=False)
	eligible_sp = db.BooleanProperty(required=True,default=False)
	eligible_p = db.BooleanProperty(required=True,default=False)
	eligible_c = db.BooleanProperty(required=True,default=False)
	eligible_1b = db.BooleanProperty(required=True,default=False)
	eligible_2b = db.BooleanProperty(required=True,default=False)
	eligible_3b = db.BooleanProperty(required=True,default=False)
	eligible_ss = db.BooleanProperty(required=True,default=False)
	eligible_of = db.BooleanProperty(required=True,default=False)
	eligible_dh = db.BooleanProperty(required=True,default=False)
	nextyr_eligible_rp = db.BooleanProperty(required=True,default=False)
	nextyr_eligible_sp = db.BooleanProperty(required=True,default=False)
	nextyr_eligible_p = db.BooleanProperty(required=True,default=False)
	nextyr_eligible_c = db.BooleanProperty(required=True,default=False)
	nextyr_eligible_1b = db.BooleanProperty(required=True,default=False)
	nextyr_eligible_2b = db.BooleanProperty(required=True,default=False)
	nextyr_eligible_3b = db.BooleanProperty(required=True,default=False)
	nextyr_eligible_ss = db.BooleanProperty(required=True,default=False)
	nextyr_eligible_of = db.BooleanProperty(required=True,default=False)
	nextyr_eligible_dh = db.BooleanProperty(required=True,default=False)
	status = db.StringProperty(required=True,default='A')
	is_disabled = db.BooleanProperty(required=True,default=False,indexed=False)
	dl_15 = db.BooleanProperty(required=True,default=False,indexed=False)
	dl_60 = db.BooleanProperty(required=True,default=False,indexed=False)
	dl_season = db.BooleanProperty(required=True,default=False,indexed=False)
	fpts_year0_actual = db.FloatProperty(default=0.0)
	fpts_year0_projected = db.FloatProperty(default=0.0)
	fpts_year0_projected_override = db.FloatProperty()
	fpts_year0_used = db.FloatProperty(default=0.0)
	fpts_yearminus1 = db.FloatProperty(default=0.0)
	fpts_yearminus2 = db.FloatProperty(default=0.0)
	weighted_fpts_2020 = db.FloatProperty(default=0.0)
	fpts_3yravg = db.FloatProperty(default=0.0)
	salarycapvalue = db.FloatProperty(default=0.0)
	most_recent_season = db.ReferenceProperty(FantasySeason)
	most_recent_season_year = db.IntegerProperty()

	_keeper = db.BooleanProperty()

	def selected_keeper(self):
		return self._keeper

	''''
	def age(self):
		if self.birthdate <> None:
			return dygutil.calculate_age(self.birthdate)
		else:
			return 99
	'''
	def eligibility_str(self):
		l = []
		if self.eligible_sp: l.append('SP')
		if self.eligible_rp: l.append('RP')
		if self.eligible_c: l.append('C')
		if self.eligible_1b: l.append('1B')
		if self.eligible_2b: l.append('2B')
		if self.eligible_3b: l.append('3B')
		if self.eligible_ss: l.append('SS')
		if self.eligible_of: l.append('OF')
		if len(l) == 0: l.append(self.primaryposition)
		return string.join(l, ',')

	def nextyr_eligibility_str(self):
		l = []
		if self.nextyr_eligible_sp: l.append('SP')
		if self.nextyr_eligible_rp: l.append('RP')
		if self.nextyr_eligible_c: l.append('C')
		if self.nextyr_eligible_1b: l.append('1B')
		if self.nextyr_eligible_2b: l.append('2B')
		if self.nextyr_eligible_3b: l.append('3B')
		if self.nextyr_eligible_ss: l.append('SS')
		if self.nextyr_eligible_of: l.append('OF')
		if len(l) == 0: l.append(self.primaryposition)
		return string.join(l, ',')

	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		self.is_disabled = (self.dl_15 or self.dl_60)

		if self.fpts_year0_projected_override <> None:
			self.fpts_year0_used = self.fpts_year0_projected_override
		else:
			self.fpts_year0_used = round(self.fpts_year0_projected, 0)
		# self.weighted_fpts_2020 = self.fpts_yearminus2 * (162.0 / 60.0)

		fpts_year0_used = 0.0
		fpts_yearminus1 = 0.0
		fpts_yearminus2 = 0.0
		# weighted_fpts_2020 = 0.0
		if self.fpts_year0_used <> None: fpts_year0_used = self.fpts_year0_used
		if self.fpts_yearminus1 <> None: fpts_yearminus1 = self.fpts_yearminus1
		if self.fpts_yearminus2 <> None: fpts_yearminus2 = self.fpts_yearminus2
		# if self.weighted_fpts_2020 <> None: weighted_fpts_2020 = self.weighted_fpts_2020
		self.fpts_3yravg = (fpts_year0_used + fpts_yearminus1 + fpts_yearminus2) / 3.0
		self.salarycapvalue = self.fpts_3yravg / 10.0
		if self.salarycapvalue < 0.0: self.salarycapvalue = 0.0
		if self.most_recent_season:
			self.most_recent_season_year = self.most_recent_season.year

	@staticmethod
	def get_or_insert_by_values(cbsplayerid):
		count = 0
		while True:
			try:
				return FantasyPlayer.get_or_insert("p_" + str(cbsplayerid),
					cbsplayerid=cbsplayerid)
			except db.Timeout:
				count += 1
				if count == 3:
					raise

class FantasyPlayerTeamChangeLog(db.Model):
	player = db.ReferenceProperty(FantasyPlayer, required=True)
	batch_cycle_id = db.StringProperty(required=True)
	new_fantasyteam = db.ReferenceProperty(FantasyTeam, collection_name='fantasyplayerteamchangelog_new_team_set')
	prev_fantasyteam = db.ReferenceProperty(FantasyTeam, collection_name='fantasyplayerteamchangelog_prev_team_set')
	transaction_type = db.StringProperty()
	team_ids = db.ListProperty(int)
	datetime = db.DateTimeProperty(auto_now_add=True)
	date = db.DateProperty()

	@classmethod
	def generate_key_name(cls, **kwargs):
		return kwargs['player'].key().name() + '_' + kwargs['batch_cycle_id']

	@classmethod
	def get_or_insert_by_values(cls, **kwargs):
		return cls.get_or_insert(cls.generate_key_name(**kwargs), **kwargs)

	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		self.team_ids = []
		if self.prev_fantasyteam:
			self.team_ids.append(self.prev_fantasyteam.key().id())
		if self.new_fantasyteam:
			self.team_ids.append(self.new_fantasyteam.key().id())
		self.date = self.datetime.date()
		if self.new_fantasyteam != self.prev_fantasyteam:
			if self.new_fantasyteam is None:
				self.transaction_type = "DROP"
			elif self.prev_fantasyteam is None:
				self.transaction_type = "ADD"
			else:
				self.transaction_type = "TRADE"

class FantasyPlayerSeason(db.Model):
	player = db.ReferenceProperty(FantasyPlayer, required=True)
	season = db.ReferenceProperty(FantasySeason, required=True)
	cbsplayerid = db.IntegerProperty(required=True)
	year = db.IntegerProperty(required=True)
	games_sp = db.IntegerProperty(indexed=False)
	games_rp = db.IntegerProperty(indexed=False)
	games_c = db.IntegerProperty(indexed=False)
	games_1b = db.IntegerProperty(indexed=False)
	games_2b = db.IntegerProperty(indexed=False)
	games_3b = db.IntegerProperty(indexed=False)
	games_ss = db.IntegerProperty(indexed=False)
	games_of = db.IntegerProperty(indexed=False)
	games_dh = db.IntegerProperty(indexed=False)
	is_final = db.BooleanProperty(required=True,default=False)
	stat_b = db.FloatProperty(indexed=False)
	stat_bbi = db.FloatProperty(indexed=False)
	stat_bs = db.FloatProperty(indexed=False)
	stat_cg = db.FloatProperty(indexed=False)
	stat_er = db.FloatProperty(indexed=False)
	stat_ha = db.FloatProperty(indexed=False)
	stat_hb = db.FloatProperty(indexed=False)
	stat_inn = db.FloatProperty(indexed=False)
	stat_k = db.FloatProperty(indexed=False)
	stat_l = db.FloatProperty(indexed=False)
	stat_nh = db.FloatProperty(indexed=False)
	stat_pg = db.FloatProperty(indexed=False)
	stat_pko = db.FloatProperty(indexed=False)
	stat_qs = db.FloatProperty(indexed=False)
	stat_s = db.FloatProperty(indexed=False)
	stat_so = db.FloatProperty(indexed=False)
	stat_w = db.FloatProperty(indexed=False)
	stat_wp = db.FloatProperty(indexed=False)
	stat_1b = db.FloatProperty(indexed=False)
	stat_2b = db.FloatProperty(indexed=False)
	stat_3b = db.FloatProperty(indexed=False)
	stat_bb = db.FloatProperty(indexed=False)
	stat_cs = db.FloatProperty(indexed=False)
	stat_cyc = db.FloatProperty(indexed=False)
	stat_e = db.FloatProperty(indexed=False)
	stat_gdp = db.FloatProperty(indexed=False)
	stat_hp = db.FloatProperty(indexed=False)
	stat_hr = db.FloatProperty(indexed=False)
	stat_ko = db.FloatProperty(indexed=False)
	stat_ofast = db.FloatProperty(indexed=False)
	stat_pbc = db.FloatProperty(indexed=False)
	stat_r = db.FloatProperty(indexed=False)
	stat_rbi = db.FloatProperty(indexed=False)
	stat_sb = db.FloatProperty(indexed=False)
	stat_sf = db.FloatProperty(indexed=False)
	stat_fpts = db.FloatProperty()

	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		if self.stat_fpts == None: self.stat_fpts = 0.0
		if self.stat_fpts == 0.0: self.is_final = False

	@staticmethod
	def get_or_insert_by_values(player, season):
		count = 0
		while True:
			try:
				return FantasyPlayerSeason.get_or_insert('ps_' + player.key().name() + "_" + season.key().name(),
					player=player, season=season, year=season.year, cbsplayerid=player.cbsplayerid)
			except db.Timeout:
				count += 1
				if count == 3:
					raise

class FantasyPlayerStats(db.Model):
	WEEK_SPAN = 1
	SEASON_SPAN = 2
	CAREER_SPAN = 3
	TOTALS = 1
	PER_WEEK_AVG = 2
	ROLLING_3_AVG = 3
	PER_SEASON_AVG = 4
	timespanvalue = db.IntegerProperty(choices = [WEEK_SPAN, SEASON_SPAN, CAREER_SPAN], required=True)
	runningtotaltimespanvalue = db.IntegerProperty(choices = [WEEK_SPAN, SEASON_SPAN, CAREER_SPAN], required=True)
	statstype = db.IntegerProperty(choices = [TOTALS, PER_WEEK_AVG, ROLLING_3_AVG, PER_SEASON_AVG], required=True)
	fantasyplayer = db.ReferenceProperty(FantasyPlayer, required=True)
	fantasyteam = db.ReferenceProperty(FantasyTeam, collection_name='fantasyplayerstats_set')
	vsfantasyteam = db.ReferenceProperty(FantasyTeam, collection_name='fantasyplayerstats_vs_set')
	year = db.IntegerProperty(required=True)
	week = db.ReferenceProperty(FantasyWeek)
	weeknumber = db.IntegerProperty(required=True)
	weeks = db.IntegerProperty(required=True,default=1)
	seasons = db.IntegerProperty(required=True,default=0)
	franchiseteamid = db.IntegerProperty(required=True, default=0)
	vsfranchiseteamid = db.IntegerProperty(required=True, default=0)
	cbsteamid = db.IntegerProperty(required=True, default=0)
	vscbsteamid = db.IntegerProperty(required=True, default=0)
	cbsplayerid = db.IntegerProperty(required=True)
	positioncode = db.StringProperty()
	lineupstatus = db.StringProperty(indexed=False)
	fantasypoints = db.FloatProperty(default=0.0,indexed=False)
	fantasypoints_old = db.FloatProperty(default=0.0,indexed=False)
	league_fantasypoints = db.FloatProperty(default=0.0,indexed=False)
	league_fantasypoints_old = db.FloatProperty(default=0.0,indexed=False)
	league_medianfantasypoints = db.FloatProperty(default=0.0,indexed=False)
	league_medianfantasypoints_old = db.FloatProperty(default=0.0,indexed=False)
	league_medianstartingpitchingpointsperstart = db.FloatProperty(default=0.0,indexed=False)
	league_medianstartingpitchingpointsperstart_old = db.FloatProperty(default=0.0,indexed=False)
	pitchingstarts = db.FloatProperty(default=0.0,indexed=False)
	pointsperpitchingstart = db.FloatProperty(default=0.0,indexed=False)
	pointsperpitchingstart_old = db.FloatProperty(default=0.0,indexed=False)
	highpointweeks = db.FloatProperty(default=0.0,indexed=False)
	lowpointweeks = db.FloatProperty(default=0.0,indexed=False)
	leaguefantasypointspct = db.FloatProperty(default=0.0,indexed=False)
	leaguefantasypointspct_old = db.FloatProperty(default=0.0,indexed=False)
	fantasypointsovermedian = db.FloatProperty(default=0.0,indexed=False)
	fantasypointsovermedian_old = db.FloatProperty(default=0.0,indexed=False)
	fantasypointsovermedianratio = db.FloatProperty(default=0.0,indexed=False)
	fantasypointsovermedianratio_old = db.FloatProperty(default=0.0,indexed=False)
	startingpitchingpointsperstartovermedian = db.FloatProperty(default=0.0,indexed=False)
	startingpitchingpointsperstartovermedianratio = db.FloatProperty(default=0.0,indexed=False)
	startingpitchingpointsperstartovermedian_old = db.FloatProperty(default=0.0,indexed=False)
	startingpitchingpointsperstartovermedianratio_old = db.FloatProperty(default=0.0,indexed=False)
	is_final = db.BooleanProperty(required=True,default=False,indexed=False)
	stat_b = db.FloatProperty(default=0.0,indexed=False)
	stat_bbi = db.FloatProperty(default=0.0,indexed=False)
	stat_bs = db.FloatProperty(default=0.0,indexed=False)
	stat_cg = db.FloatProperty(default=0.0,indexed=False)
	stat_er = db.FloatProperty(default=0.0,indexed=False)
	stat_ha = db.FloatProperty(default=0.0,indexed=False)
	stat_hb = db.FloatProperty(default=0.0,indexed=False)
	stat_inn = db.FloatProperty(default=0.0,indexed=False)
	stat_k = db.FloatProperty(default=0.0,indexed=False)
	stat_l = db.FloatProperty(default=0.0,indexed=False)
	stat_nh = db.FloatProperty(default=0.0,indexed=False)
	stat_pg = db.FloatProperty(default=0.0,indexed=False)
	stat_pko = db.FloatProperty(default=0.0,indexed=False)
	stat_qs = db.FloatProperty(default=0.0,indexed=False)
	stat_s = db.FloatProperty(default=0.0,indexed=False)
	stat_so = db.FloatProperty(default=0.0,indexed=False)
	stat_w = db.FloatProperty(default=0.0,indexed=False)
	stat_wp = db.FloatProperty(default=0.0,indexed=False)
	stat_1b = db.FloatProperty(default=0.0,indexed=False)
	stat_2b = db.FloatProperty(default=0.0,indexed=False)
	stat_3b = db.FloatProperty(default=0.0,indexed=False)
	stat_bb = db.FloatProperty(default=0.0,indexed=False)
	stat_cs = db.FloatProperty(default=0.0,indexed=False)
	stat_cyc = db.FloatProperty(default=0.0,indexed=False)
	stat_e = db.FloatProperty(default=0.0,indexed=False)
	stat_gdp = db.FloatProperty(default=0.0,indexed=False)
	stat_hp = db.FloatProperty(default=0.0,indexed=False)
	stat_hr = db.FloatProperty(default=0.0,indexed=False)
	stat_ko = db.FloatProperty(default=0.0,indexed=False)
	stat_ofast = db.FloatProperty(default=0.0,indexed=False)
	stat_pbc = db.FloatProperty(default=0.0,indexed=False)
	stat_r = db.FloatProperty(default=0.0,indexed=False)
	stat_rbi = db.FloatProperty(default=0.0,indexed=False)
	stat_sb = db.FloatProperty(default=0.0,indexed=False)
	stat_sf = db.FloatProperty(default=0.0,indexed=False)
	stat_fpts = db.FloatProperty(default=0.0)
	stat_fpts_old = db.FloatProperty(default=0.0)

	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		if self.pitchingstarts > 0:
			self.pointsperpitchingstart = self.fantasypoints / self.pitchingstarts
			self.pointsperpitchingstart_old = self.fantasypoints_old / self.pitchingstarts
		if self.league_fantasypoints > 0:
			self.leaguefantasypointspct = self.fantasypoints / self.league_fantasypoints
		if self.league_fantasypoints_old > 0:
			self.leaguefantasypointspct_old = self.fantasypoints_old / self.league_fantasypoints_old
		if self.league_medianfantasypoints > 0:
			self.fantasypointsovermedian = self.fantasypoints - self.league_medianfantasypoints
			self.fantasypointsovermedianratio = self.fantasypointsovermedian / self.league_medianfantasypoints
		if self.league_medianfantasypoints_old > 0:
			self.fantasypointsovermedian_old = self.fantasypoints_old - self.league_medianfantasypoints_old
			self.fantasypointsovermedianratio_old = self.fantasypointsovermedian_old / self.league_medianfantasypoints_old
		if self.league_medianstartingpitchingpointsperstart > 0:
			self.startingpitchingpointsperstartovermedian = self.pointsperpitchingstart - self.league_medianstartingpitchingpointsperstart
			self.startingpitchingpointsperstartovermedianratio = self.startingpitchingpointsperstartovermedian / self.league_medianstartingpitchingpointsperstart
		if self.league_medianstartingpitchingpointsperstart_old > 0:
			self.startingpitchingpointsperstartovermedian_old = self.pointsperpitchingstart_old - self.league_medianstartingpitchingpointsperstart_old
			self.startingpitchingpointsperstartovermedianratio_old = self.startingpitchingpointsperstartovermedian_old / self.league_medianstartingpitchingpointsperstart_old
		if self.fantasyteam <> None:
			self.franchiseteamid = self.fantasyteam.franchiseteamid
			self.cbsteamid = self.fantasyteam.cbsteamid
		if self.vsfantasyteam <> None:
			self.vsfranchiseteamid = self.vsfantasyteam.franchiseteamid
			self.vscbsteamid = self.vsfantasyteam.cbsteamid

	@staticmethod
	def get_or_insert_by_values(timespanvalue, runningtotaltimespanvalue, statstype, fantasyplayer, season, week):
		count = 0
		while True:
			try:
				playerkeyname = "p_" + str(fantasyplayer.cbsplayerid)
				cbsplayerid = fantasyplayer.cbsplayerid
				weekkeyname = 'None'
				weeknumber = 0
				year = 0
				if week <> None:
					weekkeyname = week.key().name()
					weeknumber = week.weeknumber
					year = week.year
				elif season <> None:
					year = season.year
					weekkeyname = season.key().name() + "_None"
				return FantasyPlayerStats.get_or_insert("ts_" + str(timespanvalue) + "_rtts_" + str(runningtotaltimespanvalue) + "_st_" + str(statstype) + "_" + playerkeyname + "_y_" + str(year) +  "_" + weekkeyname,
					timespanvalue=timespanvalue, runningtotaltimespanvalue=runningtotaltimespanvalue, statstype=statstype, fantasyplayer=fantasyplayer, week=week, year=year, weeknumber=weeknumber,
					cbsplayerid=cbsplayerid)
			except db.Timeout:
				count += 1
				if count == 3:
					raise

class FantasyGame(db.Model):
	week = db.ReferenceProperty(FantasyWeek, required=True)
	year = db.IntegerProperty(required=True)
	weeknumber = db.IntegerProperty(required=True)
	visitor = db.ReferenceProperty(FantasyTeam, required=True, collection_name='fantasygame_visitor_set')
	visitorfranchiseteamid = db.IntegerProperty(required=True)
	visitorcbsteamid = db.IntegerProperty(required=True)
	visitorpoints = db.IntegerProperty()
	home = db.ReferenceProperty(FantasyTeam, required=True, collection_name='fantasygame_home_set')
	homefranchiseteamid = db.IntegerProperty(required=True)
	homecbsteamid = db.IntegerProperty(required=True)
	homepoints = db.IntegerProperty()

	@staticmethod
	def get_or_insert_by_values(week, visitor, home):
		count = 0
		while True:
			try:
				return FantasyGame.get_or_insert(week.key().name() + '_v_' + str(visitor.franchiseteamid) + '_h_' + str(home.franchiseteamid),
					year=week.year, week=week, weeknumber=week.weeknumber,
					visitor=visitor, visitorfranchiseteamid=visitor.franchiseteamid, visitorcbsteamid=visitor.cbsteamid, home=home, homefranchiseteamid=home.franchiseteamid, homecbsteamid=home.cbsteamid)
			except db.Timeout:
				count += 1
				if count == 3:
					raise

class FantasyTeamStats(db.Model):
	WEEK_SPAN = 1
	SEASON_SPAN = 2
	CAREER_SPAN = 3
	TOTALS = 1
	PER_WEEK_AVG = 2
	ROLLING_3_AVG = 3
	PER_SEASON_AVG = 4
	timespanvalue = db.IntegerProperty(choices = [WEEK_SPAN, SEASON_SPAN, CAREER_SPAN], required=True)
	runningtotaltimespanvalue = db.IntegerProperty(choices = [WEEK_SPAN, SEASON_SPAN, CAREER_SPAN], required=True)
	statstype = db.IntegerProperty(choices = [TOTALS, PER_WEEK_AVG, ROLLING_3_AVG, PER_SEASON_AVG], required=True)
	fantasyteam = db.ReferenceProperty(FantasyTeam, collection_name='fantasyteamstats_set')
	vsfantasyteam = db.ReferenceProperty(FantasyTeam, collection_name='fantasyteamstats_vs_set')
	grouping = db.StringProperty(required=True,default='ALL')
	year = db.IntegerProperty(required=True)
	week = db.ReferenceProperty(FantasyWeek)
	weeknumber = db.IntegerProperty(required=True)
	weeks = db.IntegerProperty(required=True,default=1)
	seasons = db.IntegerProperty(required=True,default=0)
	franchiseteamid = db.IntegerProperty(required=True)
	vsfranchiseteamid = db.IntegerProperty(required=True)
	cbsteamid = db.IntegerProperty(required=True)
	vscbsteamid = db.IntegerProperty(required=True)
	wins = db.FloatProperty(default=0.0)
	losses = db.FloatProperty(default=0.0)
	ties = db.FloatProperty(default=0.0)
	games = db.FloatProperty(default=0.0)
	gamesabove500 = db.FloatProperty(default=0.0)
	leadergamesabove500 = db.FloatProperty(default=0.0)
	gamesbehind = db.FloatProperty(default=0.0)
	winningpct = db.FloatProperty(default=0.0)
	hittingpoints = db.FloatProperty(default=0.0)
	pitchingpoints = db.FloatProperty(default=0.0)
	startingpitchingpoints = db.FloatProperty(default=0.0)
	totalpoints = db.FloatProperty(default=0.0)
	hittingpoints14 = db.FloatProperty(default=0.0)
	pitchingpoints14 = db.FloatProperty(default=0.0)
	startingpitchingpoints14 = db.FloatProperty(default=0.0)
	totalpoints14 = db.FloatProperty(default=0.0)
	hittingpoints_old = db.FloatProperty(default=0.0)
	pitchingpoints_old = db.FloatProperty(default=0.0)
	startingpitchingpoints_old = db.FloatProperty(default=0.0)
	totalpoints_old = db.FloatProperty(default=0.0)
	hittingpoints14_old = db.FloatProperty(default=0.0)
	pitchingpoints14_old = db.FloatProperty(default=0.0)
	startingpitchingpoints14_old = db.FloatProperty(default=0.0)
	totalpoints14_old = db.FloatProperty(default=0.0)
	league_hittingpoints = db.FloatProperty(default=0.0)
	league_pitchingpoints = db.FloatProperty(default=0.0)
	league_startingpitchingpoints = db.FloatProperty(default=0.0)
	league_totalpoints = db.FloatProperty(default=0.0)
	league_hittingpoints14 = db.FloatProperty(default=0.0)
	league_pitchingpoints14 = db.FloatProperty(default=0.0)
	league_startingpitchingpoints14 = db.FloatProperty(default=0.0)
	league_totalpoints14 = db.FloatProperty(default=0.0)
	league_hittingpoints_old = db.FloatProperty(default=0.0)
	league_pitchingpoints_old = db.FloatProperty(default=0.0)
	league_startingpitchingpoints_old = db.FloatProperty(default=0.0)
	league_totalpoints_old = db.FloatProperty(default=0.0)
	league_hittingpoints14_old = db.FloatProperty(default=0.0)
	league_pitchingpoints14_old = db.FloatProperty(default=0.0)
	league_startingpitchingpoints14_old = db.FloatProperty(default=0.0)
	league_totalpoints14_old = db.FloatProperty(default=0.0)
	league_medianhittingpoints = db.FloatProperty(default=0.0)
	league_medianpitchingpoints = db.FloatProperty(default=0.0)
	league_medianstartingpitchingpoints = db.FloatProperty(default=0.0)
	league_medianstartingpitchingpointsperstart = db.FloatProperty(default=0.0)
	league_mediantotalpoints = db.FloatProperty(default=0.0)
	league_medianhittingpoints_old = db.FloatProperty(default=0.0)
	league_medianpitchingpoints_old = db.FloatProperty(default=0.0)
	league_medianstartingpitchingpoints_old = db.FloatProperty(default=0.0)
	league_medianstartingpitchingpointsperstart_old = db.FloatProperty(default=0.0)
	league_mediantotalpoints_old = db.FloatProperty(default=0.0)
	pitchingstarts = db.FloatProperty(default=0.0)
	pointsperpitchingstart = db.FloatProperty(default=0.0)
	pointsperpitchingstart_old = db.FloatProperty(default=0.0)
	highpointweeks = db.FloatProperty(default=0.0)
	lowpointweeks = db.FloatProperty(default=0.0)
	breakdownwins = db.FloatProperty(default=0.0)
	breakdownlosses = db.FloatProperty(default=0.0)
	breakdownties = db.FloatProperty(default=0.0)
	breakdowngames = db.FloatProperty(default=0.0)
	breakdowngamesabove500 = db.FloatProperty(default=0.0)
	breakdownpct = db.FloatProperty(default=0.0)
	expectedwins = db.FloatProperty(default=0.0)
	expectedlosses = db.FloatProperty(default=0.0)
	leaguehittingpointspct = db.FloatProperty(default=0.0)
	leaguepitchingpointspct = db.FloatProperty(default=0.0)
	leaguestartingpitchingpointspct = db.FloatProperty(default=0.0)
	leaguetotalpointspct = db.FloatProperty(default=0.0)
	leaguepitchingpointspct_old = db.FloatProperty(default=0.0)
	leaguestartingpitchingpointspct_old = db.FloatProperty(default=0.0)
	leaguetotalpointspct_old = db.FloatProperty(default=0.0)
	hittingpointsovermedian = db.FloatProperty(default=0.0)
	pitchingpointsovermedian = db.FloatProperty(default=0.0)
	startingpitchingpointsovermedian = db.FloatProperty(default=0.0)
	startingpitchingpointsperstartovermedian = db.FloatProperty(default=0.0)
	totalpointsovermedian = db.FloatProperty(default=0.0)
	hittingpointsovermedian14 = db.FloatProperty(default=0.0)
	pitchingpointsovermedian14 = db.FloatProperty(default=0.0)
	startingpitchingpointsovermedian14 = db.FloatProperty(default=0.0)
	totalpointsovermedian14 = db.FloatProperty(default=0.0)
	hittingpointsovermedian_old = db.FloatProperty(default=0.0)
	pitchingpointsovermedian_old = db.FloatProperty(default=0.0)
	startingpitchingpointsovermedian_old = db.FloatProperty(default=0.0)
	totalpointsovermedian_old = db.FloatProperty(default=0.0)
	hittingpointsovermedian14_old = db.FloatProperty(default=0.0)
	pitchingpointsovermedian14_old = db.FloatProperty(default=0.0)
	startingpitchingpointsovermedian14_old = db.FloatProperty(default=0.0)
	totalpointsovermedian14_old = db.FloatProperty(default=0.0)
	hittingpointsovermedianratio = db.FloatProperty(default=0.0)
	pitchingpointsovermedianratio = db.FloatProperty(default=0.0)
	startingpitchingpointsovermedianratio = db.FloatProperty(default=0.0)
	startingpitchingpointsperstartovermedianratio = db.FloatProperty(default=0.0)
	totalpointsovermedianratio = db.FloatProperty(default=0.0)
	hittingpointsovermedianratio_old = db.FloatProperty(default=0.0)
	pitchingpointsovermedianratio_old = db.FloatProperty(default=0.0)
	startingpitchingpointsovermedianratio_old = db.FloatProperty(default=0.0)
	totalpointsovermedianratio_old = db.FloatProperty(default=0.0)
	startingpitchingpointsperstartovermedian_old = db.FloatProperty(default=0.0)
	is_final = db.BooleanProperty(required=True,default=False)
	stat_b = db.FloatProperty(default=0.0)
	stat_bbi = db.FloatProperty(default=0.0)
	stat_bs = db.FloatProperty(default=0.0)
	stat_cg = db.FloatProperty(default=0.0)
	stat_er = db.FloatProperty(default=0.0)
	stat_ha = db.FloatProperty(default=0.0)
	stat_hb = db.FloatProperty(default=0.0)
	stat_inn = db.FloatProperty(default=0.0)
	stat_k = db.FloatProperty(default=0.0)
	stat_l = db.FloatProperty(default=0.0)
	stat_nh = db.FloatProperty(default=0.0)
	stat_pg = db.FloatProperty(default=0.0)
	stat_pko = db.FloatProperty(default=0.0)
	stat_qs = db.FloatProperty(default=0.0)
	stat_s = db.FloatProperty(default=0.0)
	stat_so = db.FloatProperty(default=0.0)
	stat_w = db.FloatProperty(default=0.0)
	stat_wp = db.FloatProperty(default=0.0)
	stat_1b = db.FloatProperty(default=0.0)
	stat_2b = db.FloatProperty(default=0.0)
	stat_3b = db.FloatProperty(default=0.0)
	stat_bb = db.FloatProperty(default=0.0)
	stat_cs = db.FloatProperty(default=0.0)
	stat_cyc = db.FloatProperty(default=0.0)
	stat_e = db.FloatProperty(default=0.0)
	stat_gdp = db.FloatProperty(default=0.0)
	stat_hp = db.FloatProperty(default=0.0)
	stat_hr = db.FloatProperty(default=0.0)
	stat_ko = db.FloatProperty(default=0.0)
	stat_ofast = db.FloatProperty(default=0.0)
	stat_pbc = db.FloatProperty(default=0.0)
	stat_r = db.FloatProperty(default=0.0)
	stat_rbi = db.FloatProperty(default=0.0)
	stat_sb = db.FloatProperty(default=0.0)
	stat_sf = db.FloatProperty(default=0.0)
	stat_fpts = db.FloatProperty(default=0.0)
	stat_fpts_old = db.FloatProperty(default=0.0)

	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		self.games = self.wins + self.losses + self.ties
		if self.games > 0: self.winningpct = (self.wins + self.ties * .5) / self.games
		self.gamesabove500 = self.wins - self.losses
		self.gamesbehind = (self.leadergamesabove500 - self.gamesabove500) / 2.0
		if self.pitchingstarts > 0:
			self.pointsperpitchingstart = self.startingpitchingpoints / self.pitchingstarts
			self.pointsperpitchingstart_old = self.startingpitchingpoints_old / self.pitchingstarts
		self.breakdowngames = self.breakdownwins + self.breakdownlosses + self.breakdownties
		if self.breakdowngames > 0: self.breakdownpct = (self.breakdownwins + self.breakdownties * .5) / self.breakdowngames
		self.breakdowngamesabove500 = self.breakdownwins - self.breakdownlosses
		self.expectedwins = self.breakdownpct * self.games
		self.expectedlosses = (1.0 - self.breakdownpct) * self.games
		if self.league_hittingpoints > 0:
			self.leaguehittingpointspct = self.hittingpoints / self.league_hittingpoints
		if self.league_pitchingpoints > 0:
			self.leaguepitchingpointspct = self.pitchingpoints / self.league_pitchingpoints
		if self.league_startingpitchingpoints > 0:
			self.leaguestartingpitchingpointspct = self.startingpitchingpoints / self.league_startingpitchingpoints
		if self.league_totalpoints > 0:
			self.leaguetotalpointspct = self.totalpoints / self.league_totalpoints
		if self.league_pitchingpoints_old > 0:
			self.leaguepitchingpointspct_old = self.pitchingpoints_old / self.league_pitchingpoints_old
		if self.league_startingpitchingpoints_old > 0:
			self.leaguestartingpitchingpointspct_old = self.startingpitchingpoints_old / self.league_startingpitchingpoints_old
		if self.league_totalpoints_old > 0:
			self.leaguetotalpointspct_old = self.totalpoints_old / self.league_totalpoints_old
		if self.league_medianhittingpoints > 0:
			self.hittingpointsovermedian = self.hittingpoints - self.league_medianhittingpoints
			self.hittingpointsovermedianratio = self.hittingpointsovermedian / self.league_medianhittingpoints
		if self.league_medianpitchingpoints > 0:
			self.pitchingpointsovermedian = self.pitchingpoints - self.league_medianpitchingpoints
			self.pitchingpointsovermedianratio = self.pitchingpointsovermedian / self.league_medianpitchingpoints
		if self.league_medianstartingpitchingpoints > 0:
			self.startingpitchingpointsovermedian = self.startingpitchingpoints - self.league_medianstartingpitchingpoints
			self.startingpitchingpointsovermedianratio = self.startingpitchingpointsovermedian / self.league_medianstartingpitchingpoints
		if self.league_medianstartingpitchingpointsperstart > 0:
			self.startingpitchingpointsperstartovermedian = self.pointsperpitchingstart - self.league_medianstartingpitchingpointsperstart
			self.startingpitchingpointsperstartovermedianratio = self.startingpitchingpointsperstartovermedian / self.league_medianstartingpitchingpointsperstart
		if self.league_mediantotalpoints > 0:
			self.totalpointsovermedian = self.totalpoints - self.league_mediantotalpoints
			self.totalpointsovermedianratio = self.totalpointsovermedian / self.league_mediantotalpoints
		if self.league_medianhittingpoints_old > 0:
			self.hittingpointsovermedian_old = self.hittingpoints_old - self.league_medianhittingpoints_old
			self.hittingpointsovermedianratio_old = self.hittingpointsovermedian_old / self.league_medianhittingpoints_old
		if self.league_medianpitchingpoints_old > 0:
			self.pitchingpointsovermedian_old = self.pitchingpoints_old - self.league_medianpitchingpoints_old
			self.pitchingpointsovermedianratio_old = self.pitchingpointsovermedian_old / self.league_medianpitchingpoints_old
		if self.league_medianstartingpitchingpoints_old > 0:
			self.startingpitchingpointsovermedian_old = self.startingpitchingpoints_old - self.league_medianstartingpitchingpoints_old
			self.startingpitchingpointsovermedianratio_old = self.startingpitchingpointsovermedian_old / self.league_medianstartingpitchingpoints_old
		if self.league_medianstartingpitchingpointsperstart_old > 0:
			self.startingpitchingpointsperstartovermedian_old = self.pointsperpitchingstart_old - self.league_medianstartingpitchingpointsperstart_old
			self.startingpitchingpointsperstartovermedianratio_old = self.startingpitchingpointsperstartovermedian_old / self.league_medianstartingpitchingpointsperstart_old
		if self.league_mediantotalpoints_old > 0:
			self.totalpointsovermedian_old = self.totalpoints_old - self.league_mediantotalpoints_old
			self.totalpointsovermedianratio_old = self.totalpointsovermedian_old / self.league_mediantotalpoints_old

	@staticmethod
	def get_or_insert_by_values(timespanvalue, runningtotaltimespanvalue, statstype, fantasyteam, vsfantasyteam, season, week, grouping='ALL'):
		count = 0
		while True:
			try:
				teamkeyname = 'ALL'
				franchiseteamid = 0
				cbsteamid = 0
				if fantasyteam <> None:
					teamkeyname = "t_" + str(fantasyteam.franchiseteamid) + "_y_" + str(fantasyteam.year)
					franchiseteamid = fantasyteam.franchiseteamid
					cbsteamid = fantasyteam.cbsteamid
				vsteamkeyname = 'ALL'
				vsfranchiseteamid = 0
				vscbsteamid = 0
				if vsfantasyteam <> None:
					vsteamkeyname = "t_" + str(vsfantasyteam.franchiseteamid) + "_y_" + str(vsfantasyteam.year)
					vsfranchiseteamid = vsfantasyteam.franchiseteamid
					vscbsteamid = vsfantasyteam.cbsteamid
				weekkeyname = 'ALL'
				weeknumber = 0
				year = 0
				if week <> None:
					weekkeyname = week.key().name()
					weeknumber = week.weeknumber
					year = week.year
				elif season <> None:
					year = season.year
					weekkeyname = season.key().name() + "_ALL"
				return FantasyTeamStats.get_or_insert("ts_" + str(timespanvalue) + "_rtts_" + str(runningtotaltimespanvalue) + "_st_" + str(statstype) + "_" + teamkeyname + "_vs_" + vsteamkeyname + "_grp_" + grouping + "_y_" + str(year) +	"_" + weekkeyname,
					timespanvalue=timespanvalue, runningtotaltimespanvalue=runningtotaltimespanvalue, statstype=statstype, fantasyteam=fantasyteam, vsfantasyteam=vsfantasyteam, week=week, year=year, weeknumber=weeknumber,
					franchiseteamid=franchiseteamid, vsfranchiseteamid=vsfranchiseteamid, cbsteamid=cbsteamid, vscbsteamid=vscbsteamid, grouping=grouping)
			except db.Timeout:
				count += 1
				if count == 3:
					raise

class BreakdownStats(db.Model):
	WEEK_SPAN = 1
	SEASON_SPAN = 2
	CAREER_SPAN = 3
	timespanvalue = db.IntegerProperty(choices = [WEEK_SPAN, SEASON_SPAN, CAREER_SPAN], required=True)
	runningtotaltimespanvalue = db.IntegerProperty(choices = [WEEK_SPAN, SEASON_SPAN, CAREER_SPAN], required=True)
	fantasyteam = db.ReferenceProperty(FantasyTeam, collection_name='breakownstats_set')
	vsfantasyteam = db.ReferenceProperty(FantasyTeam, collection_name='breakownstats_vs_set')
	grouping = db.StringProperty(required=True,default='ALL')
	year = db.IntegerProperty(required=True)
	week = db.ReferenceProperty(FantasyWeek)
	weeknumber = db.IntegerProperty(required=True)
	franchiseteamid = db.IntegerProperty(required=True)
	vsfranchiseteamid = db.IntegerProperty(required=True)
	cbsteamid = db.IntegerProperty(required=True)
	vscbsteamid = db.IntegerProperty(required=True)
	wins = db.FloatProperty(default=0.0)
	losses = db.FloatProperty(default=0.0)
	ties = db.FloatProperty(default=0.0)
	games = db.FloatProperty(default=0.0)
	gamesabove500 = db.FloatProperty(default=0.0)
	weeklystats = db.ReferenceProperty(FantasyTeamStats, collection_name='breakownstats_set')
	vsweeklystats = db.ReferenceProperty(FantasyTeamStats, collection_name='breakownstats_vs_set')
	breakdownwins = db.FloatProperty(default=0.0)
	breakdownlosses = db.FloatProperty(default=0.0)
	breakdownties = db.FloatProperty(default=0.0)
	breakdowngames = db.FloatProperty(default=0.0)
	breakdowngamesabove500 = db.FloatProperty(default=0.0)
	breakdownpct = db.FloatProperty(default=0.0)
	expectedwins = db.FloatProperty(default=0.0)
	expectedlosses = db.FloatProperty(default=0.0)
	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		self.games = self.wins + self.losses + self.ties
		if self.games > 0: self.winningpct = (self.wins + self.ties * .5) / self.games
		self.gamesabove500 = self.wins - self.losses
		self.breakdowngames = self.breakdownwins + self.breakdownlosses + self.breakdownties
		if self.breakdowngames > 0: self.breakdownpct = (self.breakdownwins + self.breakdownties * .5) / self.breakdowngames
		self.breakdowngamesabove500 = self.breakdownwins - self.breakdownlosses
		self.expectedwins = self.breakdownpct * self.games
		self.expectedlosses = (1.0 - self.breakdownpct) * self.games

	@staticmethod
	def get_or_insert_by_values(timespanvalue, runningtotaltimespanvalue, fantasyteam, vsfantasyteam, season, week, grouping='ALL'):
		count = 0
		while True:
			try:
				teamkeyname = 'ALL'
				franchiseteamid = 0
				cbsteamid = 0
				if fantasyteam <> None:
					teamkeyname = "t_" + str(fantasyteam.franchiseteamid) + "_y_" + str(fantasyteam.year)
					franchiseteamid = fantasyteam.franchiseteamid
					cbsteamid = fantasyteam.cbsteamid
				vsteamkeyname = 'ALL'
				vsfranchiseteamid = 0
				vscbsteamid = 0
				if vsfantasyteam <> None:
					vsteamkeyname = "t_" + str(vsfantasyteam.franchiseteamid) + "_y_" + str(vsfantasyteam.year)
					vsfranchiseteamid = vsfantasyteam.franchiseteamid
					vscbsteamid = vsfantasyteam.cbsteamid
				weekkeyname = 'ALL'
				weeknumber = 0
				year = 0
				if week <> None:
					weekkeyname = week.key().name()
					weeknumber = week.weeknumber
					year = week.year
				elif season <> None:
					year = season.year
					weekkeyname = season.key().name() + "_ALL"
				return BreakdownStats.get_or_insert("ts_" + str(timespanvalue) + "_rtts_" + str(runningtotaltimespanvalue) + "_" + teamkeyname + "_vs_" + vsteamkeyname + "_grp_" + grouping + "_y_" + str(year) +	"_" + weekkeyname,
					timespanvalue=timespanvalue, runningtotaltimespanvalue=runningtotaltimespanvalue, fantasyteam=fantasyteam, vsfantasyteam=vsfantasyteam, week=week, year=year, weeknumber=weeknumber,
					franchiseteamid=franchiseteamid, vsfranchiseteamid=vsfranchiseteamid, cbsteamid=cbsteamid, vscbsteamid=vscbsteamid, grouping=grouping)
			except db.Timeout:
				count += 1
				if count == 3:
					raise

class SalaryCapChangeLog(db.Model):
	changerteam = db.ReferenceProperty(dygmodel.Team, required=True)
	changedplayer = db.ReferenceProperty(FantasyPlayer, required=True)
	changedyear = db.IntegerProperty(required=True)
	ipaddress = db.StringProperty(required=True)
	changedetails = db.StringProperty(required=True)
	date = db.DateTimeProperty(auto_now_add=True)
	changerownername = db.StringProperty()
	changedplayername = db.StringProperty()
	changedteamname = db.StringProperty()
	originalrecord_pickled = db.TextProperty()
	newrecord_pickled = db.TextProperty()
	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		self.changerownername = self.changerteam.ownername
		self.changedplayername = self.changedplayer.firstname + ' ' + self.changedplayer.lastname
		self.changedteamname = self.changedplayer.fantasyteam.teamname

class PickEmWeek(db.Model):
	week = db.ReferenceProperty(FantasyWeek, required=True)
	weeknumber = db.IntegerProperty()
	season = db.ReferenceProperty(FantasySeason)
	year = db.IntegerProperty()
	first_game_datetime = db.DateTimeProperty()
	start_date = db.DateTimeProperty()
	end_date = db.DateTimeProperty()
	matchups = dygmodel.DictListProperty()
	entries = dygmodel.DictListProperty()
	dateadded = db.DateTimeProperty(auto_now_add=True)

	def first_game_datetime_central(self):
		if self.first_game_datetime:
			return self.first_game_datetime.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)

	def entry_deadline_datetime_central(self):
		first_game_datetime_central = self.first_game_datetime_central()
		if not first_game_datetime_central:
			return
		if self.year == 2018 and self.weeknumber == 1:
			deadline_central = first_game_datetime_central.replace(hour=22, minute=0)
			if first_game_datetime_central > deadline_central:
				deadline_central = first_game_datetime_central
			return deadline_central
		else:
			deadline_central = first_game_datetime_central
			return deadline_central

	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		self.weeknumber = self.week.weeknumber
		self.season = self.week.season
		self.year = self.season.year
		self.start_date = self.week.startdate
		self.end_date = self.week.enddate

	@classmethod
	def generate_key_name(cls, **kwargs):
		return kwargs['week'].key().name()

	@classmethod
	def get_or_insert_by_values(cls, **kwargs):
		return cls.get_or_insert(cls.generate_key_name(**kwargs), **kwargs)

class PickEmMatchup(db.Model):
	game = db.ReferenceProperty(FantasyGame, required=True)
	week = db.ReferenceProperty(PickEmWeek)
	home_final_points = db.IntegerProperty(default=0)
	visitor_final_points = db.IntegerProperty(default=0)
	dateadded = db.DateTimeProperty(auto_now_add=True)

	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		now_central = datetime.datetime.now().replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)
		if now_central.date() > self.week.end_date.date():
			self.home_final_points = self.game.homepoints
			self.visitor_final_points = self.game.visitorpoints

	def to_dict(self):
		return {
			'key_name': self.key().name(),
			'home_team': {
				'cbs_team_id': self.game.home.cbsteamid,
				'team_name': self.game.home.teamname,
				'team_abbrev': self.game.home.shortname,
				'final_points': self.home_final_points,
			},
			'visitor_team': {
				'cbs_team_id': self.game.visitor.cbsteamid,
				'team_name': self.game.visitor.teamname,
				'team_abbrev': self.game.visitor.shortname,
				'final_points': self.visitor_final_points,
			},
		}
	@classmethod
	def generate_key_name(cls, **kwargs):
		return kwargs['game'].key().name()

	@classmethod
	def get_or_insert_by_values(cls, **kwargs):
		return cls.get_or_insert(cls.generate_key_name(**kwargs), **kwargs)

class PickEmEntrant(db.Model):
	franchise = db.ReferenceProperty(dygmodel.Team)
	year = db.IntegerProperty(required=True)
	name = db.StringProperty(required=True)
	dateadded = db.DateTimeProperty(auto_now_add=True)

	@classmethod
	def generate_key_name(cls, **kwargs):
		return 'pme_' + str(kwargs['franchise'].teamid) + '_' + str(kwargs['year'])

	@classmethod
	def get_or_insert_by_values(cls, **kwargs):
		if not kwargs.get('name'):
			kwargs['name'] = kwargs['franchise'].ownername
		return cls.get_or_insert(cls.generate_key_name(**kwargs), **kwargs)

class PickEmEntry(db.Model):
	week = db.ReferenceProperty(PickEmWeek, required=True)
	entrant = db.ReferenceProperty(PickEmEntrant, required=True)
	entrant_name = db.StringProperty(required=True)
	dateadded = db.DateTimeProperty(auto_now_add=True)
	submitted_datetime = db.DateTimeProperty()
	selections = dygmodel.DictListProperty()
	source_data = dygmodel.DictListProperty()

	def to_dict(self):
		if self.submitted_datetime:
			submitted_datetime_central = self.submitted_datetime.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)
		return {
			'entrant_team': {
				'team_id': self.entrant.franchise.teamid,
				'cbs_team_id': self.entrant.franchise.cbsteamid,
				'name': self.entrant_name,
			},
			'submitted_datetime_central': submitted_datetime_central.strftime('%m/%d/%Y %I:%M:%S %p'),
			'selections': self.selections,
			'is_late': self.is_late(),
			'late_duration_str': self.late_duration_str(),
		}

	def is_late(self):
		return self.submitted_datetime > self.week.first_game_datetime

	def late_duration_str(self):
		if self.is_late():
			late_duration_days = (self.submitted_datetime - self.week.first_game_datetime).days
			late_duration_seconds = (self.submitted_datetime - self.week.first_game_datetime).seconds
			late_duration_hours = int((late_duration_seconds + 900) / 3600)
			late_duration_minutes = int(late_duration_seconds / 60)
			if late_duration_days:
				return "%s day%s" % (late_duration_days, "" if late_duration_days == 1 else "s")
			elif late_duration_hours > 0 and late_duration_minutes >= 60:
				return "%s hour%s" % (late_duration_hours, "" if late_duration_hours == 1 else "s")
			elif late_duration_minutes:
				return "%s minute%s" % (late_duration_minutes, "" if late_duration_minutes == 1 else "s")
			else:
				return "%s late_duration_seconds%s" % (late_duration_seconds, "" if late_duration_seconds == 1 else "s")

	@classmethod
	def generate_key_name(cls, **kwargs):
		return 'pme_' + kwargs['entrant'].key().name() + '_' + str(kwargs['week'].weeknumber)

	@classmethod
	def get_or_insert_by_values(cls, **kwargs):
		return cls.get_or_insert(cls.generate_key_name(**kwargs), **kwargs)

class PickEmEntrySelection(db.Model):
	entry = db.ReferenceProperty(PickEmEntry)
	matchup = db.ReferenceProperty(PickEmMatchup, required=True)
	selected_team = db.ReferenceProperty(FantasyTeam)
	selected_cbs_team_id = db.IntegerProperty()
	selection_weight = db.IntegerProperty()
	dateadded = db.DateTimeProperty(auto_now_add=True)

	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		self.selected_cbs_team_id = self.selected_team.cbsteamid if self.selected_team else None

	def to_dict(self):
		return {
			'matchup': {
				'key_name': self.matchup.key().name(),
			},
			'selected_team': {
				'cbs_team_id': self.selected_team.cbsteamid,
			},
			'selection_weight': self.selection_weight,
		}

	@classmethod
	def generate_key_name(cls, **kwargs):
		if isinstance(kwargs['entry'], db.Key):
			entry_key_name = kwargs['entry'].name()
		elif isinstance(kwargs['entry'], db.Model):
			entry_key_name = kwargs['entry'].key().name()
		if isinstance(kwargs['matchup'], db.Key):
			matchup_key_name = kwargs['matchup'].name()
		elif isinstance(kwargs['matchup'], db.Model):
			matchup_key_name = kwargs['matchup'].key().name()
		return 'pmes_' + entry_key_name + '_' + matchup_key_name

	@classmethod
	def get_or_insert_by_values(cls, **kwargs):
		return cls.get_or_insert(cls.generate_key_name(**kwargs), **kwargs)

class MrSportsPlayerSeason(db.Model):
	player_id = db.IntegerProperty(required=True)
	cbsplayerid = db.IntegerProperty()
	year = db.IntegerProperty(required=True)
	full_name = db.StringProperty(required=True)
	games_sp = db.IntegerProperty()
	games_rp = db.IntegerProperty()
	games_c = db.IntegerProperty()
	games_1b = db.IntegerProperty()
	games_2b = db.IntegerProperty()
	games_3b = db.IntegerProperty()
	games_ss = db.IntegerProperty()
	games_of = db.IntegerProperty()
	games_dh = db.IntegerProperty()
