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

import datetime

from google.appengine.ext import db,search
from google.appengine.api import datastore_types

import dygutil
import dygchatdata
import logging

logdebug = True

import pickle
class SerializedDataProperty(db.Property):
	def get_value_for_datastore(self, model_instance):
		value = super(SerializedDataProperty, self).get_value_for_datastore(model_instance)
		return db.Blob(pickle.dumps(value))

	def make_value_from_datastore(self, value):
		if value is None:
			return None
		return pickle.loads(value)

	def default_value(self):
		if self.default is None:
			return None
		else:
			return super(SerializedDataProperty, self).default_value().copy()

	def empty(self, value):
		return value is None

class DictProperty(SerializedDataProperty):
	data_type = dict

	def make_value_from_datastore(self, value):
		if value is None:
			return dict()
		return super(DictProperty, self).make_value_from_datastore(value)

	def default_value(self):
		if self.default is None:
			return dict()
		else:
			return super(DictProperty, self).default_value().copy()

	def validate(self, value):
		if not isinstance(value, dict):
			raise db.BadValueError('Property %s needs to be convertible '
												 'to a dict instance (%s) of class dict' % (self.name, value))
		return super(DictProperty, self).validate(value)

class DictListProperty(SerializedDataProperty):
	data_type = list

	def make_value_from_datastore(self, value):
		if value is None:
			return []
		return super(DictListProperty, self).make_value_from_datastore(value)

	def default_value(self):
		if self.default is None:
			return []
		else:
			return super(DictListProperty, self).default_value().copy()

	def validate(self, value):
		if not isinstance(value, list):
			raise db.BadValueError('Property %s needs to be convertible '
												 'to a list instance (%s) of class list' % (self.name, value))
		for item in value:
			if not isinstance(item, dict):
				raise db.BadValueError('Items in List Property %s need to be convertible '
													 'to a dict instance (%s) of class dict' % (self.name, item))
		return super(DictListProperty, self).validate(value)

class Team(db.Model):
	teamname = db.StringProperty(required=True)
	ownername = db.StringProperty(required=True)
	shortname = db.StringProperty()
	email = db.EmailProperty()
	postindex = db.IntegerProperty(required=True, default=0)
	user_google_login = db.BooleanProperty(default=False)
	google_id = db.EmailProperty()
	cbsteamid = db.IntegerProperty(default=0)
	teamid = db.IntegerProperty()
	is_interactive = db.BooleanProperty(required=True, default=True)

class ChatMessage(search.SearchableModel):
	team = db.ReferenceProperty(Team,required=True)
	team_key_name = db.StringProperty(indexed=False)
	local_id = db.StringProperty()
	text = db.TextProperty(required=True)
	htmltext = db.TextProperty()
	media = DictListProperty()
	date = db.DateTimeProperty(auto_now_add=True)
	sortindex = db.StringProperty()
	displaydate = db.StringProperty(indexed=False)
	ipaddress = db.StringProperty(required=True)
	logicaldelete = db.BooleanProperty(required=True,default=False,indexed=False)
	statscomplete = db.BooleanProperty(required=True,default=False,indexed=False)
	mancow = db.BooleanProperty(default=False,indexed=False)
	from_slack = db.BooleanProperty(default=False,indexed=False)
	_pteamownername = db.StringProperty()
	def teamownername(self):
		if not self._pteamownername:
			if logdebug: logging.debug("ChatMessage.teamownername(): invoking dygchatdata.fetch_team_ownername()")
			self._pteamownername = dygchatdata.fetch_team_ownername(self.team.key().name())
			#db.Model.put(self)
		return self._pteamownername
	def to_dict(self):
		if not self.htmltext:
			self.set_calculated_fields()
		#'team_owner_name': "Cyrus Khazai" if self.mancow else self.teamownername(),
		return {
			'id': self.key().id(),
			'local_id': self.local_id,
			'team_key_name': self.team_key_name,
			'team_owner_name': self.teamownername(),
			'text': self.htmltext,
			'date': self.date.replace(tzinfo=dygutil.UTC_tzinfo()).strftime("%a %b %d %H:%M:%S UTC %Y"),
			'sortindex': self.sortindex,
			'mancow': self.mancow,
			'media': self.media,
			'from_slack': self.from_slack
		}
	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		html, media = dygutil.urlify(self.text, suppress_images=self.htmltext != None)
		self.htmltext = html
		self.media = media
		self.displaydate = self.date.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).strftime('%m/%d/%Y %I:%M:%S %p')
		self.team_key_name = self.team.key().name()

class ChatWord(db.Model):
	word = db.StringProperty()
	hidden = db.BooleanProperty(required=True,default=False)
	date = db.DateTimeProperty(auto_now_add=True)

class ChatMessageChatWord(db.Model):
	chatmessage = db.ReferenceProperty(ChatMessage)
	chatword = db.ReferenceProperty(ChatWord)
	statscomplete = db.BooleanProperty(required=True,default=False,indexed=False)
	messagedate = db.DateTimeProperty()
	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		self.messagedate = self.chatmessage.date

class StatsTimeSpan(db.Model):
	ALL_TIME_SPAN = 1
	YEAR_SPAN = 2
	MONTH_SPAN = 3
	DAY_SPAN = 4
	HOUR_SPAN = 5
	timespanvalue = db.IntegerProperty(choices = [HOUR_SPAN, DAY_SPAN, MONTH_SPAN, YEAR_SPAN, ALL_TIME_SPAN])
	year_central = db.IntegerProperty()
	month_central = db.IntegerProperty()
	day_central = db.IntegerProperty()
	hour_central = db.IntegerProperty(indexed=False)
	postcount = db.IntegerProperty(required=True,default=0)
	uniqueteamspostings = db.ListProperty(str)
	uniqueteamspostingcount = db.IntegerProperty(required=True,default=0)
	totalduration = db.FloatProperty(required=True,default=float(0))
	date = db.DateTimeProperty(auto_now_add=True)
	statsdate_central = db.DateTimeProperty()
	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		if not self.is_saved():
			if self.timespanvalue == StatsTimeSpan.ALL_TIME_SPAN:
				self.statsdate_central = datetime.datetime.now()
			elif self.timespanvalue == StatsTimeSpan.YEAR_SPAN:
				self.statsdate_central = datetime.datetime(year=self.year_central,month=1,day=1)
			elif self.timespanvalue == StatsTimeSpan.MONTH_SPAN:
				self.statsdate_central = datetime.datetime(year=self.year_central,month=self.month_central,day=1)
			elif self.timespanvalue == StatsTimeSpan.DAY_SPAN:
				self.statsdate_central = datetime.datetime(year=self.year_central,month=self.month_central,day=self.day_central)
			elif self.timespanvalue == StatsTimeSpan.HOUR_SPAN:
				self.statsdate_central = datetime.datetime(year=self.year_central,month=self.month_central,day=self.day_central,hour=self.hour_central,minute=0,second=0)
	def uniqueteamspostingperhour(self):
		if self.totalduration > 0:
			return float(self.uniqueteamspostingcount) / self.totalduration
		else:
			return 0.0
	def postpercentage(self):
		return 0.0
	def usagecount(self):
		return 0
	def usagepercentage(self):
		return 0.0
	def displaypostcount(self):
		return dygutil.format_number(self.postcount)
	def monthname(self):
		return dygutil.get_month_name(self.month_central)
	def displayhour(self):
		if self.hour_central == 0:
			return "12am"
		elif self.hour_central < 12:
			return str(self.hour_central) + "am"
		elif self.hour_central == 12:
			return str(self.hour_central) + "pm"
		else:
			return str(self.hour_central-12) + "pm"

	@staticmethod
	def get_or_insert_by_values(timespanvalue, year_central, month_central, day_central, hour_central):
		count = 0
		while True:
			try:
				return StatsTimeSpan.get_or_insert("ts_" + str(timespanvalue) + "_" + str(year_central) + "_" + str(month_central) + "_" + str(day_central) + "_" + str(hour_central),
					timespanvalue=timespanvalue,year_central=year_central,month_central=month_central,day_central=day_central,hour_central=hour_central)
			except db.Timeout:
				count += 1
				if count == 3:
					raise

class ChatWordStats(db.Model):
	chatword = db.ReferenceProperty(ChatWord)
	word = db.StringProperty()
	hiddenword = db.BooleanProperty()
	worddate = db.DateTimeProperty()
	worddate_central = db.DateTimeProperty()
	timespan = db.ReferenceProperty(StatsTimeSpan)
	timespanvalue = db.IntegerProperty()
	year_central = db.IntegerProperty()
	month_central = db.IntegerProperty()
	day_central = db.IntegerProperty()
	hour_central = db.IntegerProperty(indexed=False)
	usagecount = db.IntegerProperty(required=True,default=0)
	uniqueteamsusing = db.ListProperty(str, indexed=False)
	uniqueteamsusagecount = db.IntegerProperty(required=True,default=0, indexed=False)
	date = db.DateTimeProperty(auto_now_add=True)
	statsdate_central = db.DateTimeProperty()
	date_central = db.DateTimeProperty()

	def usagepercentage(self):
		all_words = ChatWordStats.get_by_key_name("cws_" + self.timespan.key().name() + "_" + "cw__all_")
		if all_words and all_words.usagecount > 0:
			return (float(self.usagecount) / float(all_words.usagecount)) * 100.0
		else:
			return 0.0

	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)

	def set_calculated_fields(self):
		if not self.is_saved():
			self.date_central = self.date.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)
			self.timespanvalue = self.timespan.timespanvalue
			self.year_central = self.timespan.year_central
			self.month_central = self.timespan.month_central
			self.day_central = self.timespan.day_central
			self.hour_central = self.timespan.hour_central
			self.statsdate_central = ChatWordStats.get_statsdate_central(self.timespanvalue, self.year_central, self.month_central, self.day_central, self.hour_central)
			self.word = self.chatword.word
			self.worddate = self.chatword.date
			self.worddate_central = self.chatword.date.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)
			self.hiddenword = self.chatword.hidden

	@staticmethod
	def get_statsdate_central(timespanvalue, year_central, month_central, day_central, hour_central):
		if timespanvalue == StatsTimeSpan.ALL_TIME_SPAN:
			return datetime.datetime.now()
		elif timespanvalue == StatsTimeSpan.YEAR_SPAN:
			return datetime.datetime(year=year_central,month=1,day=1)
		elif timespanvalue == StatsTimeSpan.MONTH_SPAN:
			return datetime.datetime(year=year_central,month=month_central,day=1)
		elif timespanvalue == StatsTimeSpan.DAY_SPAN:
			return datetime.datetime(year=year_central,month=month_central,day=day_central)
		elif timespanvalue == StatsTimeSpan.HOUR_SPAN:
			return datetime.datetime(year=year_central,month=month_central,day=day_central,hour=hour_central,minute=0,second=0)

	@staticmethod
	def get_or_insert_by_values(timespan, chatword):
		count = 0
		while True:
			try:
				return ChatWordStats.get_or_insert("cws_" + timespan.key().name() + "_" + chatword.key().name(),
					timespan=timespan,
					chatword=chatword)
			except db.Timeout:
				count += 1
				if count == 3:
					raise

class TeamChatWordStats(db.Model):
	team = db.ReferenceProperty(Team,required=True)
	word = db.StringProperty()
	hiddenword = db.BooleanProperty()
	worddate = db.DateTimeProperty(indexed=False)
	worddate_central = db.DateTimeProperty(indexed=False)
	timespan = db.ReferenceProperty(StatsTimeSpan, indexed=False)
	timespanvalue = db.IntegerProperty()
	year_central = db.IntegerProperty()
	month_central = db.IntegerProperty()
	day_central = db.IntegerProperty()
	hour_central = db.IntegerProperty(indexed=False)
	chatwordstats = db.ReferenceProperty(ChatWordStats)
	usagecount = db.IntegerProperty(required=True,default=0, indexed=False)
	date = db.DateTimeProperty(auto_now_add=True, indexed=False)
	statsdate_central = db.DateTimeProperty()
	date_central = db.DateTimeProperty(indexed=False)

	def usagepercentage(self):
		all_words = TeamChatWordStats.get_by_key_name("tcws_" + self.team.key().name() + "_" + "cws_" + self.timespan.key().name() + "_" + "cw__all_")
		if all_words and all_words.usagecount > 0:
			return (float(self.usagecount) / float(all_words.usagecount)) * 100.0
		else:
			return 0.0

	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)

	def set_calculated_fields(self):
		if not self.is_saved():
			self.date_central = self.date.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)
			self.timespanvalue = self.chatwordstats.timespanvalue
			self.year_central = self.chatwordstats.year_central
			self.month_central = self.chatwordstats.month_central
			self.day_central = self.chatwordstats.day_central
			self.hour_central = self.chatwordstats.hour_central
			self.statsdate_central = TeamChatWordStats.get_statsdate_central(self.timespanvalue, self.year_central, self.month_central, self.day_central, self.hour_central)
			self.word = self.chatwordstats.word
			self.worddate = self.chatwordstats.worddate
			self.worddate_central = self.chatwordstats.worddate.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)
			self.timespan = self.chatwordstats.timespan
			self.hiddenword = self.chatwordstats.chatword.hidden

	@staticmethod
	def get_statsdate_central(timespanvalue, year_central, month_central, day_central, hour_central):
		if timespanvalue == StatsTimeSpan.ALL_TIME_SPAN:
			return datetime.datetime.now()
		elif timespanvalue == StatsTimeSpan.YEAR_SPAN:
			return datetime.datetime(year=year_central,month=1,day=1)
		elif timespanvalue == StatsTimeSpan.MONTH_SPAN:
			return datetime.datetime(year=year_central,month=month_central,day=1)
		elif timespanvalue == StatsTimeSpan.DAY_SPAN:
			return datetime.datetime(year=year_central,month=month_central,day=day_central)
		elif timespanvalue == StatsTimeSpan.HOUR_SPAN:
			return datetime.datetime(year=year_central,month=month_central,day=day_central,hour=hour_central,minute=0,second=0)

	@staticmethod
	def get_or_insert_by_values(team, chatwordstats, date=None):
		count = 0
		while True:
			try:
				if date:
					return TeamChatWordStats.get_or_insert("tcws_" + team.key().name() + "_" + chatwordstats.key().name(),
						team=team,chatwordstats=chatwordstats,date=date)
				else:
					return TeamChatWordStats.get_or_insert("tcws_" + team.key().name() + "_" + chatwordstats.key().name(),
						team=team,chatwordstats=chatwordstats)
			except db.Timeout:
				count += 1
				if count == 3:
					raise

class TeamChatMessageStats(db.Model):
	team = db.ReferenceProperty(Team,required=True)
	timespan = db.ReferenceProperty(StatsTimeSpan)
	timespanvalue = db.IntegerProperty()
	year_central = db.IntegerProperty()
	month_central = db.IntegerProperty()
	day_central = db.IntegerProperty()
	hour_central = db.IntegerProperty(indexed=False)
	postcount = db.IntegerProperty(required=True,default=0)
	date = db.DateTimeProperty(auto_now_add=True, indexed=False)
	statsdate_central = db.DateTimeProperty()
	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		if not self.is_saved():
			self.timespanvalue = self.timespan.timespanvalue
			self.year_central = self.timespan.year_central
			self.month_central = self.timespan.month_central
			self.day_central = self.timespan.day_central
			self.hour_central = self.timespan.hour_central
			if self.timespanvalue == StatsTimeSpan.ALL_TIME_SPAN:
				self.statsdate_central = datetime.datetime.now()
			elif self.timespanvalue == StatsTimeSpan.YEAR_SPAN:
				self.statsdate_central = datetime.datetime(year=self.year_central,month=1,day=1)
			elif self.timespanvalue == StatsTimeSpan.MONTH_SPAN:
				self.statsdate_central = datetime.datetime(year=self.year_central,month=self.month_central,day=1)
			elif self.timespanvalue == StatsTimeSpan.DAY_SPAN:
				self.statsdate_central = datetime.datetime(year=self.year_central,month=self.month_central,day=self.day_central)
			elif self.timespanvalue == StatsTimeSpan.HOUR_SPAN:
				self.statsdate_central = datetime.datetime(year=self.year_central,month=self.month_central,day=self.day_central,hour=self.hour_central,minute=0,second=0)
	def monthname(self):
		return dygutil.get_month_name(self.month_central)
	def displaypostcount(self):
		return dygutil.format_number(self.postcount)
	def displayhour(self):
		if self.hour_central == 0:
			return "12am"
		elif self.hour_central < 12:
			return str(self.hour_central) + "am"
		elif self.hour_central == 12:
			return str(self.hour_central) + "pm"
		else:
			return str(self.hour_central-12) + "pm"

		return dygutil.get_month_name(self.month_central)
	def postpercentage(self):
		if self.timespan.postcount > 0:
			return (float(self.postcount) / float(self.timespan.postcount)) * 100.0
		else:
			return 0.0
	@staticmethod
	def get_or_insert_by_values(team, timespan):
		return TeamChatMessageStats.get_or_insert("tms_" + team.key().name() + "_" + timespan.key().name(),
			team=team,timespan=timespan)

class SettingsElementStats(db.Model):
	PAGE_TITLE_KIND = 1
	VIDEO_KIND = 2
	PHOTO_KIND = 3
	CAPTION_KIND = 4
	THEME_KIND = 5
	element_kind = db.IntegerProperty(choices = [PAGE_TITLE_KIND, VIDEO_KIND, PHOTO_KIND, CAPTION_KIND, THEME_KIND])
	element = db.ReferenceProperty()
	#timespan = db.ReferenceProperty(StatsTimeSpan)
	timespanvalue = db.IntegerProperty()
	year_central = db.IntegerProperty()
	month_central = db.IntegerProperty()
	day_central = db.IntegerProperty()
	hour_central = db.IntegerProperty()
	postcount = db.IntegerProperty(default=0)
	uniqueteamspostingcount = db.IntegerProperty(default=0)
	startdatetime_central = db.DateTimeProperty()
	enddatetime_central = db.DateTimeProperty()
	duration = db.FloatProperty(required=True,default=float(0))
	date = db.DateTimeProperty(auto_now_add=True)
	statsdate_central = db.DateTimeProperty()

	def durationindays(self):
		return self.duration / 24.0

	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)

	def set_calculated_fields(self):
		if not self.is_saved():
			self.timespanvalue = self.timespan.timespanvalue
			#self.postcount = self.timespan.postcount
			#self.uniqueteamspostingcount = self.timespan.uniqueteamspostingcount
			self.year_central = self.timespan.year_central
			self.month_central = self.timespan.month_central
			self.day_central = self.timespan.day_central
			self.hour_central = self.timespan.hour_central
			if self.timespanvalue == StatsTimeSpan.ALL_TIME_SPAN:
				self.statsdate_central = datetime.datetime.now()
			elif self.timespanvalue == StatsTimeSpan.YEAR_SPAN:
				self.statsdate_central = datetime.datetime(year=self.year_central,month=1,day=1)
			elif self.timespanvalue == StatsTimeSpan.MONTH_SPAN:
				self.statsdate_central = datetime.datetime(year=self.year_central,month=self.month_central,day=1)
			elif self.timespanvalue == StatsTimeSpan.DAY_SPAN:
				self.statsdate_central = datetime.datetime(year=self.year_central,month=self.month_central,day=self.day_central)
			elif self.timespanvalue == StatsTimeSpan.HOUR_SPAN:
				self.statsdate_central = datetime.datetime(year=self.year_central,month=self.month_central,day=self.day_central,hour=self.hour_central,minute=0,second=0)

	@staticmethod
	def get_or_insert_by_values(element_kind,element,timespan):
		return SettingsElementStats.get_or_insert("ses_" + str(element_kind) + "_" + element.key().name() + "_" + timespan.key().name(),
			element_kind=element_kind,element=element,timespan=timespan)

class SettingsElementRating(db.Model):
	element = db.ReferenceProperty(collection_name='ratings_set')
	team = db.ReferenceProperty(Team,required=True)
	rating = db.IntegerProperty()
	date = db.DateTimeProperty(auto_now_add=True)
	@staticmethod
	def get_or_insert_by_values(element,team):
		return SettingsElementRating.get_or_insert("ser_" + element.key().name() + "_" + team.key().name(),
			element=element,team=team)

class YouTubeVideo(db.Model):
	youtubeid = db.StringProperty(required=True)
	title = db.StringProperty()
	videodata = db.BlobProperty()
	thumbnaildata = db.BlobProperty()
	video_blob_key = db.StringProperty()
	thumbnail_blob_key = db.StringProperty()
	date = db.DateTimeProperty(auto_now_add=True)
	totalrating = db.IntegerProperty(default=0)
	totalraters = db.IntegerProperty(default=0)
	_myrating = db.IntegerProperty()
	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		if not self.thumbnaildata:
			try:
				youtubeinfo = dygutil.getYoutubeInfo(self.youtubeid)
				photodata = dygutil.getImageUrlInfo(youtubeinfo[1])[0]
				if photodata: self.thumbnaildata = dygutil.getImageThumbnail(photodata,200,150)
			except:
				pass
	def set_myrating(self,team_key_name):
		for rating in self.ratings_set:
			if rating.team.key().name() == team_key_name:
				self._myrating = rating.rating
				break
	def my_displayrating(self):
		if self._myrating:
			return self._myrating
		else:
			return 0
	def date_central(self):
		return self.date.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)
	def average_rating(self):
		if self.totalraters > 0:
			return float(self.totalrating) / float(self.totalraters)
		else:
			return 0.0
	def display_average_rating(self):
		return str(round(self.average_rating(), 1))
	def star18ratingwidth(self):
		return int(round((self.average_rating() / float(5)) * float(90)))
	def star12ratingwidth(self):
		return int(round((self.average_rating() / float(5)) * float(60)))
	def my_star18ratingwidth(self):
		if self._myrating:
			return int(round((self._myrating / float(5)) * float(90)))
		else:
			return 0
	def my_star12ratingwidth(self):
		if self._myrating:
			return int(round((self._myrating / float(5)) * float(60)))
		else:
			return 0
	def compact_title(self):
		if len(self.title) <= 30:
			return self.title
		else:
			return self.title[:28] + "..."

class Photo(db.Model):
	url = db.LinkProperty(required=True)
	original_filename = db.StringProperty(indexed=False)
	photodata = db.BlobProperty()
	thumbnaildata = db.BlobProperty()
	photo_blob_key = db.StringProperty()
	photo_gcs_blob_key = db.StringProperty(indexed=False)
	thumbnail_blob_key = db.StringProperty()
	thumbnail_gcs_blob_key = db.StringProperty(indexed=False)
	height = db.IntegerProperty(indexed=False)
	thumbnail_width = db.IntegerProperty(indexed=False)
	thumbnail_height = db.IntegerProperty(indexed=False)
	width = db.IntegerProperty(indexed=False)
	date = db.DateTimeProperty(auto_now_add=True)
	totalrating = db.IntegerProperty(default=0)
	totalraters = db.IntegerProperty(default=0)
	_myrating = db.IntegerProperty()
	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)
	def set_calculated_fields(self):
		if not self.thumbnaildata:
			if self.photodata: self.thumbnaildata = dygutil.getImageThumbnail(self.photodata,125,163)
	def set_myrating(self,team_key_name):
		for rating in self.ratings_set:
			if rating.team.key().name() == team_key_name:
				self._myrating = rating.rating
				break
	def my_displayrating(self):
		if self._myrating:
			return self._myrating
		else:
			return 0
	def date_central(self):
		return self.date.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)
	def average_rating(self):
		if self.totalraters > 0:
			return float(self.totalrating) / float(self.totalraters)
		else:
			return 0.0
	def display_average_rating(self):
		return str(round(self.average_rating(), 1))
	def star18ratingwidth(self):
		return int(round((self.average_rating() / float(5)) * float(90)))
	def star12ratingwidth(self):
		return int(round((self.average_rating() / float(5)) * float(60)))
	def my_star18ratingwidth(self):
		if self._myrating:
			return int(round((self._myrating / float(5)) * float(90)))
		else:
			return 0
	def my_star12ratingwidth(self):
		if self._myrating:
			return int(round((self._myrating / float(5)) * float(60)))
		else:
			return 0
	def displaywidth(self):
		if self.width and self.height:
			new_width, new_height = dygutil.get_resized_image_dimensions(self.width, self.height, 700, 500, constrain=True)
			return new_width
		else:
			return 0
	def displayheight(self):
		if self.width and self.height:
			new_width, new_height = dygutil.get_resized_image_dimensions(self.width, self.height, 700, 500, constrain=True)
			return new_height
		else:
			return 0
	def popupwidth(self):
		if self.displaywidth():
			return max(self.displaywidth(), 200)
		else:
			return 200
	def popupheight(self):
		if self.displayheight():
			return max(self.displayheight() + 60, 200)
		else:
			return 200

	@classmethod
	def gcs_image_name(cls, url):
		import hashlib
		md5 = hashlib.md5()
		md5.update(url)
		return md5.hexdigest()

	def serving_url(self, size="o"):
		# http://storage.googleapis.com/dyinggiraffe-hrd.appspot.com/images/0658757ff030159b28af87617eabbe51/o.jpg
		gcs_bucket_folder_url = "http://storage.googleapis.com/dyinggiraffe-hrd.appspot.com/images"
		return "%s/%s/%s.jpg" % (gcs_bucket_folder_url, self.__class__.gcs_image_name(self.url), size)

	def thumbnail_serving_url(self):
		return self.serving_url(size="t")

class Caption(db.Model):
	text = db.StringProperty(required=True)
	date = db.DateTimeProperty(auto_now_add=True)
	totalrating = db.IntegerProperty(default=0)
	totalraters = db.IntegerProperty(default=0)
	_myrating = db.IntegerProperty()
	def set_myrating(self,team_key_name):
		for rating in self.ratings_set:
			if rating.team.key().name() == team_key_name:
				self._myrating = rating.rating
				break
	def my_displayrating(self):
		if self._myrating:
			return self._myrating
		else:
			return 0
	def date_central(self):
		return self.date.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)
	def average_rating(self):
		if self.totalraters > 0:
			return float(self.totalrating) / float(self.totalraters)
		else:
			return 0.0
	def display_average_rating(self):
		return str(round(self.average_rating(), 1))
	def star18ratingwidth(self):
		return int(round((self.average_rating() / float(5)) * float(90)))
	def star12ratingwidth(self):
		return int(round((self.average_rating() / float(5)) * float(60)))
	def my_star18ratingwidth(self):
		if self._myrating:
			return int(round((self._myrating / float(5)) * float(90)))
		else:
			return 0
	def my_star12ratingwidth(self):
		if self._myrating:
			return int(round((self._myrating / float(5)) * float(60)))
		else:
			return 0

class PageTitle(db.Model):
	text = db.StringProperty(required=True)
	date = db.DateTimeProperty(auto_now_add=True)
	totalrating = db.IntegerProperty(default=0)
	totalraters = db.IntegerProperty(default=0)
	_myrating = db.IntegerProperty()
	def set_myrating(self,team_key_name):
		for rating in self.ratings_set:
			if rating.team.key().name() == team_key_name:
				self._myrating = rating.rating
				break
	def my_displayrating(self):
		if self._myrating:
			return self._myrating
		else:
			return 0
	def date_central(self):
		return self.date.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)
	def average_rating(self):
		if self.totalraters > 0:
			return float(self.totalrating) / float(self.totalraters)
		else:
			return 0.0
	def display_average_rating(self):
		return str(round(self.average_rating(), 1))
	def star18ratingwidth(self):
		return int(round((self.average_rating() / float(5)) * float(90)))
	def star12ratingwidth(self):
		return int(round((self.average_rating() / float(5)) * float(60)))
	def my_star18ratingwidth(self):
		if self._myrating:
			return int(round((self._myrating / float(5)) * float(90)))
		else:
			return 0
	def my_star12ratingwidth(self):
		if self._myrating:
			return int(round((self._myrating / float(5)) * float(60)))
		else:
			return 0

class Theme(db.Model):
	name = db.StringProperty(required=True)
	stylesheet = db.StringProperty(required=True)
	date = db.DateTimeProperty(auto_now_add=True)
	totalrating = db.IntegerProperty(default=0)
	totalraters = db.IntegerProperty(default=0)
	_myrating = db.IntegerProperty()
	def set_myrating(self,team_key_name):
		for rating in self.ratings_set:
			if rating.team.key().name() == team_key_name:
				self._myrating = rating.rating
				break
	def my_displayrating(self):
		if self._myrating:
			return self._myrating
		else:
			return 0
	def date_central(self):
		return self.date.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).replace(tzinfo=None)
	def average_rating(self):
		if self.totalraters > 0:
			return float(self.totalrating) / float(self.totalraters)
		else:
			return 0.0
	def display_average_rating(self):
		return str(round(self.average_rating(), 1))
	def star18ratingwidth(self):
		return int(round((self.average_rating() / float(5)) * float(90)))
	def star12ratingwidth(self):
		return int(round((self.average_rating() / float(5)) * float(60)))
	def my_star18ratingwidth(self):
		if self._myrating:
			return int(round((self._myrating / float(5)) * float(90)))
		else:
			return 0
	def my_star12ratingwidth(self):
		if self._myrating:
			return int(round((self._myrating / float(5)) * float(60)))
		else:
			return 0

class PageSettings(search.SearchableModel):
	pagetitle = db.ReferenceProperty(PageTitle)
	prompt = db.StringProperty(default='')
	url1 = db.LinkProperty()
	url2 = db.LinkProperty()
	url3 = db.LinkProperty()
	video1 = db.ReferenceProperty(YouTubeVideo, collection_name='pagesettings_set1')
	video2 = db.ReferenceProperty(YouTubeVideo, collection_name='pagesettings_set2')
	photo1 = db.ReferenceProperty(Photo, collection_name='pagesettings_set1')
	photo2 = db.ReferenceProperty(Photo, collection_name='pagesettings_set2')
	photo3 = db.ReferenceProperty(Photo, collection_name='pagesettings_set3')
	caption1 = db.ReferenceProperty(Caption, collection_name='pagesettings_set1')
	caption2 = db.ReferenceProperty(Caption, collection_name='pagesettings_set2')
	caption3 = db.ReferenceProperty(Caption, collection_name='pagesettings_set3')
	video1title = db.StringProperty(default='')
	video2title = db.StringProperty(default='')
	caption1text = db.StringProperty(default='')
	caption2text = db.StringProperty(default='')
	caption3text = db.StringProperty(default='')
	theme = db.ReferenceProperty(Theme)
	team = db.ReferenceProperty(Team,required=True)
	date = db.DateTimeProperty(auto_now_add=True)
	enddate = db.DateTimeProperty()
	ipaddress = db.StringProperty(required=True)
	elementkeys = db.StringListProperty()
	logicaldelete = db.BooleanProperty(required=True,default=False)
	titlestatscomplete = db.BooleanProperty(required=True,default=False)
	titleclosedout = db.BooleanProperty(required=True,default=False)
	photostatscomplete = db.BooleanProperty(required=True,default=False)
	photosclosedout = db.BooleanProperty(required=True,default=False)
	videostatscomplete = db.BooleanProperty(required=True,default=False)
	videosclosedout = db.BooleanProperty(required=True,default=False)
	captionstatscomplete = db.BooleanProperty(required=True,default=False)
	captionsclosedout = db.BooleanProperty(required=True,default=False)
	themestatscomplete = db.BooleanProperty(required=True,default=False)
	themeclosedout = db.BooleanProperty(required=True,default=False)
	allstatscomplete = db.BooleanProperty(required=True,default=False)
	def displaydate(self): return self.date.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).strftime('%m/%d/%Y %I:%M:%S %p')
	def displayenddate(self): return self.enddate.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo()).strftime('%m/%d/%Y %I:%M:%S %p') if self.enddate else ""
	def to_dict(self):
		d = {
			'pagetitle': self.pagetitle.text,
			'prompt': self.prompt,
			'url1': self.url1,
			'url2': self.url2,
			'url3': self.url3,
		}
		import urllib
		if self.photo1:
			import logging
			logging.info("self.photo1.url=%s" % self.photo1.url)
			if self.photo1.photo_blob_key:
				d['photo1url'] = "/blobstore/%s?url=%s" % (self.photo1.photo_blob_key, urllib.quote(self.photo1.url))
			elif self.photo1.photo_gcs_blob_key:
				d['photo1url'] = self.photo1.serving_url(size='t')
			elif self.photo1.photodata:
				d['photo1url'] = "/localimg?photokey=" + str(self.photo1.key())
			else:
				d['photo1url'] = "/images/notfound.gif"
			d['photo1key'] = str(self.photo1.key())
			if self.photo1.popupheight: d['photo1popupheight'] = str(self.photo1.popupheight())
			if self.photo1.popupwidth: d['photo1popupwidth'] = str(self.photo1.popupwidth())
		if self.photo2:
			if self.photo2.photo_blob_key:
				d['photo2url'] = "/blobstore/%s?url=%s" % (self.photo2.photo_blob_key, urllib.quote(self.photo2.url))
			elif self.photo2.photo_gcs_blob_key:
				d['photo2url'] = self.photo2.serving_url(size='t')
			elif self.photo2.photodata:
				d['photo2url'] = "/localimg?photokey=" + str(self.photo2.key())
			else:
				d['photo2url'] = "/images/notfound.gif"
			d['photo2key'] = str(self.photo2.key())
			if self.photo2.popupheight: d['photo2popupheight'] = str(self.photo2.popupheight())
			if self.photo2.popupwidth: d['photo2popupwidth'] = str(self.photo2.popupwidth())
		if self.photo3:
			if self.photo3.photo_blob_key:
				d['photo3url'] = "/blobstore/%s?url=%s" % (self.photo3.photo_blob_key, urllib.quote(self.photo3.url))
			elif self.photo3.photo_gcs_blob_key:
				d['photo3url'] = self.photo3.serving_url(size='t')
			elif self.photo3.photodata:
				d['photo3url'] = "/localimg?photokey=" + str(self.photo3.key())
			else:
				d['photo3url'] = "/images/notfound.gif"
			d['photo3key'] = str(self.photo3.key())
			if self.photo3.popupheight: d['photo3popupheight'] = str(self.photo3.popupheight())
			if self.photo3.popupwidth: d['photo3popupwidth'] = str(self.photo3.popupwidth())
		if self.video1: d['video1id'] = self.video1.youtubeid
		if self.video2: d['video2id'] = self.video2.youtubeid
		if self.caption1: d['caption1'] = self.caption1.text
		if self.caption2: d['caption2'] = self.caption2.text
		if self.caption3: d['caption3'] = self.caption3.text
		if self.theme:
			d['theme'] = self.theme.stylesheet
		else:
			d['theme'] = "basic.css"
		return d

	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)

	def set_calculated_fields(self):
		if self.video1: self.video1title = self.video1.title
		if self.video2: self.video2title = self.video2.title
		if self.caption1: self.caption1text = self.caption1.text
		if self.caption2: self.caption2text = self.caption2.text
		if self.caption3: self.caption3text = self.caption3.text
		elementkeys = [str(self.pagetitle.key())]
		if self.video1: elementkeys.append(str(self.video1.key()))
		if self.video2: elementkeys.append(str(self.video2.key()))
		if self.photo1: elementkeys.append(str(self.photo1.key()))
		if self.photo2: elementkeys.append(str(self.photo2.key()))
		if self.photo3: elementkeys.append(str(self.photo3.key()))
		if self.caption1: elementkeys.append(str(self.caption1.key()))
		if self.caption2: elementkeys.append(str(self.caption2.key()))
		if self.caption3: elementkeys.append(str(self.caption3.key()))
		if self.theme: elementkeys.append(str(self.theme.key()))
		self.elementkeys = elementkeys

class CapPointsTrade(db.Model):
	from_team = db.ReferenceProperty(Team, required=True, collection_name='cappoints_from_team_set')
	to_team = db.ReferenceProperty(Team, required=True, collection_name='cappoints_to_team_set')
	points_traded = db.FloatProperty(required=True)
	trade_date = db.DateProperty()
	offseason_year = db.IntegerProperty(required=True)
	team_ids = db.ListProperty(int)
	dateadded = db.DateTimeProperty(auto_now_add=True)

	def put(self):
		self.set_calculated_fields()
		return db.Model.put(self)

	def set_calculated_fields(self):
		self.team_ids = [int(self.from_team.key().name()[2:]), int(self.to_team.key().name()[2:])]

class UserSentenceData(db.Model):
	team_key_name = db.StringProperty(required=True)
	last_generated_date = db.DateTimeProperty()
	unigram_data = DictProperty()
	bigram_data = DictProperty()
	opening_words = db.StringListProperty()
