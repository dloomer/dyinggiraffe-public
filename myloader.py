#!/usr/bin/env python
# encoding: utf-8
"""
myloader.py

Created by David Loomer on 2008-12-02.
Copyright (c) 2008 __MyCompanyName__. All rights reserved.
"""

import bulkload
import main
import dygmodel
import dygchatdata
import dygsettingsdata
import dygutil
from google.appengine.api import datastore_types,datastore
from google.appengine.ext import db,search
import logging
import datetime

class TeamLoader(bulkload.Loader):
	def __init__(self):
		bulkload.Loader.__init__(self, 'Team',
			[('teamid', int),
			('teamname', str),
			('ownername', str),
			('email', datastore_types.Email),
			('postindex', int),
			('cbsteamid', int),
			])

	def HandleEntity(self, entity):
		if entity.kind() == "Team":
			team = datastore.Entity('Team', name="t_" + str(entity["teamid"]))
			team["teamname"] = entity["teamname"]
			team["ownername"] = entity["ownername"]
			team["email"] = entity["email"]
			team["postindex"] = entity["postindex"]
			team["cbsteamid"] = entity["cbsteamid"]
			team.update(entity)
			newent = team

		return newent

class ChatLoader(bulkload.Loader):
	global stopwords
	stopwords = open('stop_words.txt', 'r').read().split()
	def __init__(self):
		bulkload.Loader.__init__(self, 'ChatMessage',
			[('team', lambda x: dygchatdata.fetch_team("t_" + str(x)).key()),
			('text', lambda x: unicode(x,'utf-8')),
			('date', lambda x: dygutil.string_to_datetime(x+".0001").replace(tzinfo=dygutil.Central_tzinfo()).astimezone(dygutil.UTC_tzinfo()).replace(tzinfo=None)),
			('ipaddress', str),
			])

	def HandleEntity(self, entity):
		dygchatdata.create_chat_message(dygmodel.Team.get(entity['team']),entity['text'],entity['ipaddress'],False,entity['date'])
		
class SettingsLoader(bulkload.Loader):
	def __init__(self):
		bulkload.Loader.__init__(self, 'PageSettings',
			[('pagetitlestr', lambda x: unicode(x,'utf-8')),
			('url1', str),
			('url3', str),
			('url2', str),
			('caption1str', lambda x: unicode(x,'utf-8')),
			('caption2str', lambda x: unicode(x,'utf-8')),
			('caption3str', lambda x: unicode(x,'utf-8')),
			('date', lambda x: dygutil.string_to_datetime(x+".0001")),
			('team', lambda x: dygmodel.Team.get_by_key_name("t_" + str(x)).key()),
			('ipaddress', str),
			])


	def HandleEntity(self, entity):
		if entity.kind() == "PageSettings":			
			settings = dygmodel.PageSettings(ipaddress=entity["ipaddress"],team=entity["team"])
			latestsettings = dygsettingsdata.get_latest_settings()

			settings.date = entity["date"].replace(tzinfo=dygutil.Central_tzinfo()).astimezone(dygutil.UTC_tzinfo())
			if latestsettings:
				latestsettings.enddate = settings.date
				latestsettings.put()
			
			url1 = entity["url1"]
			if url1[:4] != "http" and url1.find("\\") < 0:
				if url1[:1] == "/":
					url1 = "http://www.dyinggiraffe.com" + url1
				else:
					url1 = "http://www.dyinggiraffe.com/" + url1
			url2 = entity["url2"]
			if url2[:4] != "http" and url2.find("\\") < 0:
				if url2[:1] == "/":
					url2 = "http://www.dyinggiraffe.com" + url2
				else:
					url2 = "http://www.dyinggiraffe.com/" + url2
			url3 = entity["url3"]
			if url3[:4] != "http" and url3.find("\\") < 0:
				if url3[:1] == "/":
					url3 = "http://www.dyinggiraffe.com" + url3
				else:
					url3 = "http://www.dyinggiraffe.com/" + url3

			try:
				settings.url1 = url1
			except:
				pass
			try:
				settings.url2 = url2
			except:
				pass
			try:
				settings.url3 = url3
			except:
				pass

			url1 = settings.url1
			url2 = settings.url2
			url3 = settings.url3

			# page title
			settings.pagetitle = dygmodel.PageTitle.get_or_insert("t_" + entity["pagetitlestr"],text=entity["pagetitlestr"])
			if datetime.datetime.now() - settings.pagetitle.date < datetime.timedelta(seconds=5):
				settings.pagetitle.date = settings.date
				settings.pagetitle.put()

			# photo/video 1
			youtubeid1 = dygutil.get_youtube_id(entity["url1"])
			photourl1 = None
			if youtubeid1 and entity["url1"].find("youtube.com/") >= 0:
				settings.video1 = dygmodel.YouTubeVideo.get_or_insert("v_" + youtubeid1,youtubeid=youtubeid1)
				if datetime.datetime.now() - settings.video1.date < datetime.timedelta(seconds=5):
					settings.video1.date = settings.date
					settings.video1.put()
				if not settings.video1.title:
					try:
						youtubeinfo = dygutil.getYoutubeInfo(settings.video1.youtubeid)
						settings.video1.title = youtubeinfo[0]
						settings.video1.thumbnaildata = dygutil.getImageThumbnail(dygutil.getImageUrlInfo(youtubeinfo[1])[0],200,150)
					except:
						pass
					settings.video1.put()
			elif url1 and url1 != "":
				photourl1 = url1
				settings.photo1 = dygmodel.Photo.get_or_insert(photourl1,url=photourl1)
				if datetime.datetime.now() - settings.photo1.date < datetime.timedelta(seconds=5):
					settings.photo1.date = settings.date
					settings.photo1.put()
				if not settings.photo1.photodata:
					try:
						photoinfo = dygutil.getImageUrlInfo(settings.photo1.url)
						if photoinfo[1][1] > 0:
							settings.photo1.photodata = photoinfo[0]
							settings.photo1.width = photoinfo[1][1]
							settings.photo1.height = photoinfo[1][2]
							settings.photo1.thumbnaildata = dygutil.getImageThumbnail(settings.photo1.photodata,125,163)
							settings.photo1.put()
					except:
						pass

			# photo 2
			photourl2 = None
			if url2 and url2 != "":
				photourl2 = url2
				settings.photo2 = dygmodel.Photo.get_or_insert(photourl2,url=photourl2)
				if datetime.datetime.now() - settings.photo2.date < datetime.timedelta(seconds=5):
					settings.photo2.date = settings.date
					settings.photo2.put()
				if not settings.photo2.photodata:
					try:
						photoinfo = dygutil.getImageUrlInfo(settings.photo2.url)
						if photoinfo[1][1] > 0:
							settings.photo2.photodata = photoinfo[0]
							settings.photo2.width = photoinfo[1][1]
							settings.photo2.height = photoinfo[1][2]
							settings.photo2.thumbnaildata = dygutil.getImageThumbnail(settings.photo2.photodata,200,163)
							settings.photo2.put()
					except:
						pass

			# photo/video 3
			youtubeid2 = dygutil.get_youtube_id(entity["url3"])
			photourl3 = None
			if youtubeid2 and entity["url3"].find("youtube.com/") >= 0:
				settings.video2 = dygmodel.YouTubeVideo.get_or_insert("v_" + youtubeid2,youtubeid=youtubeid2)
				if datetime.datetime.now() - settings.video2.date < datetime.timedelta(seconds=5):
					settings.video2.date = settings.date
					settings.video2.put()
				if not settings.video2.title:
					try:
						youtubeinfo = dygutil.getYoutubeInfo(settings.video2.youtubeid)
						settings.video2.title = youtubeinfo[0]
						settings.video2.thumbnaildata = dygutil.getImageThumbnail(dygutil.getImageUrlInfo(youtubeinfo[1])[0],200,150)
					except:
						pass
					settings.video2.put()
			elif url3 and url3 != "":
				photourl3 = url3
				settings.photo3 = dygmodel.Photo.get_or_insert(photourl3,url=photourl3)
				if datetime.datetime.now() - settings.photo3.date < datetime.timedelta(seconds=5):
					settings.photo3.date = settings.date
					settings.photo3.put()
				if not settings.photo3.photodata:
					try:
						photoinfo = dygutil.getImageUrlInfo(settings.photo3.url)
						if photoinfo[1][1] > 0:
							settings.photo3.photodata = photoinfo[0]
							settings.photo3.width = photoinfo[1][1]
							settings.photo3.height = photoinfo[1][2]
							settings.photo3.thumbnaildata = dygutil.getImageThumbnail(settings.photo3.photodata,200,163)
							settings.photo3.put()
					except:
						pass

			# captions
			if entity["caption1str"] != "": 
				settings.caption1 = dygmodel.Caption.get_or_insert("c_" + entity["caption1str"],text=entity["caption1str"])
				if datetime.datetime.now() - settings.caption1.date < datetime.timedelta(seconds=5):
					settings.caption1.date = settings.date
					settings.caption1.put()
			if entity["caption2str"] != "": 
				settings.caption2 = dygmodel.Caption.get_or_insert("c_" + entity["caption2str"],text=entity["caption2str"])
				if datetime.datetime.now() - settings.caption2.date < datetime.timedelta(seconds=5):
					settings.caption2.date = settings.date
					settings.caption2.put()
			if entity["caption3str"] != "": 
				settings.caption3 = dygmodel.Caption.get_or_insert("c_" + entity["caption3str"],text=entity["caption3str"])
				if datetime.datetime.now() - settings.caption3.date < datetime.timedelta(seconds=5):
					settings.caption3.date = settings.date
					settings.caption3.put()

			settings.video1title = ""
			settings.video2title = ""
			settings.caption1text = ""
			settings.caption2text = ""
			settings.caption3text = ""

			if settings.video1: settings.video1title = settings.video1.title
			if settings.video2: settings.video2title = settings.video2.title
			if settings.caption1: settings.caption1text = settings.caption1.text
			if settings.caption2: settings.caption2text = settings.caption2.text
			if settings.caption3: settings.caption3text = settings.caption3.text
			settings.put()

			# update stats
			#dygsettingsdata.update_page_settings_stats(latestsettings, settings, youtubeid1, youtubeid2, photourl1, photourl2, photourl3)

			return

if __name__ == '__main__':
  bulkload.main(TeamLoader())
  #bulkload.main(ChatLoader())
  #bulkload.main(SettingsLoader())


