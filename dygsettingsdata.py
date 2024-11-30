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

from google.appengine.ext import db,search

import logging
import datetime

import dygutil
import dygmodel
import dygchatdata

def update_settings(self):
	teamkeyname = dygutil.getteamid(self)
	latestsettings = get_latest_settings()
	settings = dygmodel.PageSettings(ipaddress=self.request.remote_addr,team=dygmodel.Team.get_by_key_name(teamkeyname))
	if latestsettings:
		latestsettings.enddate = settings.date
		latestsettings.put()

	settings.url1 = self.request.get("url1")
	settings.url2 = self.request.get("url2")
	settings.url3 = self.request.get("url3")

	entitylist = []

	# page title
	settings.pagetitle = dygmodel.PageTitle.get_or_insert("t_" + self.request.get("title"),text=self.request.get("title"),date=settings.date)

	# photo/video 1
	youtubeid1 = dygutil.get_youtube_id(self.request.get("url1"))
	photourl1 = None
	if youtubeid1 and (self.request.get("url1").find("youtube.com/") >= 0 or self.request.get("url1").find("youtu.be/") >= 0):
		settings.video1 = dygmodel.YouTubeVideo.get_or_insert("v_" + youtubeid1,youtubeid=youtubeid1,date=settings.date)
		if not settings.video1.title:
			try:
				youtubeinfo = dygutil.getYoutubeInfo(settings.video1.youtubeid)
				settings.video1.title = youtubeinfo[0]
				settings.video1.thumbnaildata = dygutil.getImageThumbnail(dygutil.getImageUrlInfo(youtubeinfo[1])[0],200,150)
			except:
				pass
			entitylist.append(settings.video1)
	else:
		photourl1 = self.request.get("url1")
		settings.photo1 = dygutil.get_internal_photo(photourl1)
		if settings.photo1:
			settings.url1 = settings.photo1.url
		else:
			settings.photo1 = dygmodel.Photo.get_or_insert(photourl1,url=photourl1,date=settings.date)
		if not settings.photo1.photo_gcs_blob_key and settings.photo1.photo_blob_key:
			if settings.photo1.photodata:
				photo_info = dygutil.getImageInfo(settings.photo1.photodata)
				thumb = dygutil.getImageThumbnail(settings.photo1.photodata,200,163)
				thumb_info = dygutil.getImageInfo(thumb)

				file_name = "/images/%s/o.jpg" % dygmodel.Photo.gcs_image_name(photourl1)
				settings.photo1.photo_gcs_blob_key = dygutil.save_gcs_object(settings.photo1.photodata, file_name, content_type=photo_info[0], options={'x-goog-acl': 'public-read'})

				file_name = "/images/%s/t.jpg" % dygmodel.Photo.gcs_image_name(photourl1)
				settings.photo1.thumbnail_gcs_blob_key = dygutil.save_gcs_object(thumb, file_name, content_type=thumb_info[0], options={'x-goog-acl': 'public-read'})

				#settings.photo1.photo_blob_key = str(dygutil.save_to_blobstore(settings.photo1.photodata, photo_info[0]))
				#settings.photo1.thumbnail_blob_key = str(dygutil.save_to_blobstore(thumb, thumb_info[0]))
				settings.photo1.photodata = None
				settings.photo1.thumbnaildata = None
			else:
				photo_info = dygutil.getImageUrlInfo(settings.photo1.url)
				settings.photo1.width = photo_info[1][1]
				settings.photo1.height = photo_info[1][2]
				thumb = dygutil.getImageThumbnail(photo_info[0],200,163)
				thumb_info = dygutil.getImageInfo(thumb)

				file_name = "/images/%s/o.jpg" % dygmodel.Photo.gcs_image_name(photourl1)
				settings.photo1.photo_gcs_blob_key = dygutil.save_gcs_object(photo_info[0], file_name, content_type=photo_info[1][0], options={'x-goog-acl': 'public-read'})

				file_name = "/images/%s/t.jpg" % dygmodel.Photo.gcs_image_name(photourl1)
				settings.photo1.thumbnail_gcs_blob_key = dygutil.save_gcs_object(thumb, file_name, content_type=thumb_info[0], options={'x-goog-acl': 'public-read'})

				#settings.photo1.photo_blob_key = str(dygutil.save_to_blobstore(photo_info[0], photo_info[1][0]))
				#settings.photo1.thumbnail_blob_key = str(dygutil.save_to_blobstore(thumb, thumb_info[0]))
			entitylist.append(settings.photo1)

	# photo 2
	photourl2 = self.request.get("url2")
	settings.photo2 = dygutil.get_internal_photo(photourl2)
	if settings.photo2:
		settings.url2 = settings.photo2.url
	else:
		settings.photo2 = dygmodel.Photo.get_or_insert(photourl2,url=photourl2,date=settings.date)
	if not settings.photo2.photo_gcs_blob_key and not settings.photo2.photo_blob_key:
		if settings.photo2.photodata:
			photo_info = dygutil.getImageInfo(settings.photo2.photodata)
			thumb = dygutil.getImageThumbnail(settings.photo2.photodata,125,163)
			thumb_info = dygutil.getImageInfo(thumb)

			file_name = "/images/%s/o.jpg" % dygmodel.Photo.gcs_image_name(photourl2)
			settings.photo2.photo_gcs_blob_key = dygutil.save_gcs_object(settings.photo2.photodata, file_name, content_type=photo_info[0], options={'x-goog-acl': 'public-read'})

			file_name = "/images/%s/t.jpg" % dygmodel.Photo.gcs_image_name(photourl2)
			settings.photo2.thumbnail_gcs_blob_key = dygutil.save_gcs_object(thumb, file_name, content_type=thumb_info[0], options={'x-goog-acl': 'public-read'})

			#settings.photo2.photo_blob_key = str(dygutil.save_to_blobstore(settings.photo2.photodata, photo_info[0]))
			#settings.photo2.thumbnail_blob_key = str(dygutil.save_to_blobstore(thumb, thumb_info[0]))
			settings.photo2.photodata = None
			settings.photo2.thumbnaildata = None
		else:
			photo_info = dygutil.getImageUrlInfo(settings.photo2.url)
			settings.photo2.width = photo_info[1][1]
			settings.photo2.height = photo_info[1][2]
			thumb = dygutil.getImageThumbnail(photo_info[0],125,163)
			thumb_info = dygutil.getImageInfo(thumb)

			file_name = "/images/%s/o.jpg" % dygmodel.Photo.gcs_image_name(photourl2)
			settings.photo2.photo_gcs_blob_key = dygutil.save_gcs_object(photo_info[0], file_name, content_type=photo_info[1][0], options={'x-goog-acl': 'public-read'})

			file_name = "/images/%s/t.jpg" % dygmodel.Photo.gcs_image_name(photourl2)
			settings.photo2.thumbnail_gcs_blob_key = dygutil.save_gcs_object(thumb, file_name, content_type=thumb_info[0], options={'x-goog-acl': 'public-read'})

			#settings.photo2.photo_blob_key = str(dygutil.save_to_blobstore(photo_info[0], photo_info[1][0]))
			#settings.photo2.thumbnail_blob_key = str(dygutil.save_to_blobstore(thumb, thumb_info[0]))
		entitylist.append(settings.photo2)

	# photo/video 3
	youtubeid2 = dygutil.get_youtube_id(self.request.get("url3"))
	photourl3 = None
	if youtubeid2 and (self.request.get("url3").find("youtube.com/") >= 0 or self.request.get("url3").find("youtu.be/") >= 0):
		settings.video2 = dygmodel.YouTubeVideo.get_or_insert("v_" + youtubeid2,youtubeid=youtubeid2,date=settings.date)
		if not settings.video2.title:
			try:
				youtubeinfo = dygutil.getYoutubeInfo(settings.video2.youtubeid)
				settings.video2.title = youtubeinfo[0]
				settings.video2.thumbnaildata = dygutil.getImageThumbnail(dygutil.getImageUrlInfo(youtubeinfo[1])[0],200,150)
			except:
				pass
			entitylist.append(settings.video2)
	else:
		photourl3 = self.request.get("url3")
		settings.photo3 = dygutil.get_internal_photo(photourl3)
		if settings.photo3:
			settings.url3 = settings.photo3.url
		else:
			settings.photo3 = dygmodel.Photo.get_or_insert(photourl3,url=photourl3,date=settings.date)
		if not settings.photo3.photo_gcs_blob_key and not settings.photo3.photo_blob_key:
			if settings.photo3.photodata:
				photo_info = dygutil.getImageInfo(settings.photo3.photodata)
				thumb = dygutil.getImageThumbnail(settings.photo3.photodata,200,163)
				thumb_info = dygutil.getImageInfo(thumb)

				file_name = "/images/%s/o.jpg" % dygmodel.Photo.gcs_image_name(photourl3)
				settings.photo3.photo_gcs_blob_key = dygutil.save_gcs_object(settings.photo3.photodata, file_name, content_type=photo_info[0], options={'x-goog-acl': 'public-read'})

				file_name = "/images/%s/t.jpg" % dygmodel.Photo.gcs_image_name(photourl3)
				settings.photo3.thumbnail_gcs_blob_key = dygutil.save_gcs_object(thumb, file_name, content_type=thumb_info[0], options={'x-goog-acl': 'public-read'})

				#settings.photo3.photo_blob_key = str(dygutil.save_to_blobstore(settings.photo3.photodata, photo_info[0]))
				#settings.photo3.thumbnail_blob_key = str(dygutil.save_to_blobstore(thumb, thumb_info[0]))
				settings.photo3.photodata = None
				settings.photo3.thumbnaildata = None
			else:
				photo_info = dygutil.getImageUrlInfo(settings.photo3.url)
				settings.photo3.width = photo_info[1][1]
				settings.photo3.height = photo_info[1][2]
				thumb = dygutil.getImageThumbnail(photo_info[0],200,163)
				thumb_info = dygutil.getImageInfo(thumb)

				file_name = "/images/%s/o.jpg" % dygmodel.Photo.gcs_image_name(photourl3)
				settings.photo3.photo_gcs_blob_key = dygutil.save_gcs_object(photo_info[0], file_name, content_type=photo_info[1][0], options={'x-goog-acl': 'public-read'})

				file_name = "/images/%s/t.jpg" % dygmodel.Photo.gcs_image_name(photourl3)
				settings.photo3.thumbnail_gcs_blob_key = dygutil.save_gcs_object(thumb, file_name, content_type=thumb_info[0], options={'x-goog-acl': 'public-read'})

				#settings.photo3.photo_blob_key = str(dygutil.save_to_blobstore(photo_info[0], photo_info[1][0]))
				#settings.photo3.thumbnail_blob_key = str(dygutil.save_to_blobstore(thumb, thumb_info[0]))
			entitylist.append(settings.photo3)

	# captions
	if self.request.get("caption1") != "": settings.caption1 = dygmodel.Caption.get_or_insert("c_" + self.request.get("caption1"),text=self.request.get("caption1"),date=settings.date)
	if self.request.get("caption2") != "": settings.caption2 = dygmodel.Caption.get_or_insert("c_" + self.request.get("caption2"),text=self.request.get("caption2"),date=settings.date)
	if self.request.get("caption3") != "": settings.caption3 = dygmodel.Caption.get_or_insert("c_" + self.request.get("caption3"),text=self.request.get("caption3"),date=settings.date)

	# theme
	settings.theme = dygmodel.Theme.get_by_key_name(self.request.get("theme"))

	settings.set_calculated_fields()
	entitylist.append(settings)
	db.put(entitylist)

	# update stats
	#update_page_settings_stats(latestsettings, settings, youtubeid1, youtubeid2, photourl1, photourl2, photourl3)

	def run_slack_sync(pos, caption, url):
		from google.appengine.api import urlfetch
		import urllib
		token = ""
		channel = "general"
		if caption:
			text = (pos + u" [" + caption + u"]: " + url).encode('utf-8')
		else:
			text = (pos + u": " + url).encode('utf-8')
		username = "sammich_bot"

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

	if settings.caption1text != latestsettings.caption1text or settings.url1 != latestsettings.url1:
		run_slack_sync("left", settings.caption1text, settings.url1)
	if settings.caption2text != latestsettings.caption2text or settings.url2 != latestsettings.url2:
		run_slack_sync("middle", settings.caption2text, settings.url2)
	if settings.caption3text != latestsettings.caption3text or settings.url3 != latestsettings.url3:
		run_slack_sync("right", settings.caption3text, settings.url3)
	return settings

def run_page_settings_stats(settings, prevsettings, stats_step, loop_limit=0):
	dt_central = settings.date.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo())

	if settings.photo1:
		photourl1 = settings.photo1.url
	else:
		photourl1 = ""
	if settings.photo2:
		photourl2 = settings.photo2.url
	else:
		photourl2 = ""
	if settings.photo3:
		photourl3 = settings.photo3.url
	else:
		photourl3 = ""
	if settings.video1:
		youtubeid1 = settings.video1.youtubeid
	else:
		youtubeid1 = ""
	if settings.video2:
		youtubeid2 = settings.video2.youtubeid
	else:
		youtubeid2 = ""
	if settings.caption1:
		caption1text = settings.caption1.text
	else:
		caption1text = ""
	if settings.caption2:
		caption2text = settings.caption2.text
	else:
		caption2text = ""
	if settings.caption3:
		caption3text = settings.caption3.text
	else:
		caption3text = ""

	is_completed = True

	if stats_step == "titlecloseout":
		if prevsettings and prevsettings.pagetitle.text != settings.pagetitle.text:
			prev_element = dygmodel.PageTitle.get_by_key_name("t_" + prevsettings.pagetitle.text)
			is_completed = close_out_settings_element(dygmodel.SettingsElementStats.PAGE_TITLE_KIND, prev_element, dt_central, loop_limit)
	elif stats_step == "titlestats":
		new_element = dygmodel.PageTitle.get_by_key_name("t_" + settings.pagetitle.text)
		is_completed = update_settings_element_stats(dygmodel.SettingsElementStats.PAGE_TITLE_KIND, new_element, dt_central, loop_limit)
	elif stats_step == "videocloseout":
		if is_completed and \
			prevsettings and \
			prevsettings.video1 and \
			prevsettings.video1.youtubeid not in set([youtubeid1,youtubeid2]):
			prev_element = dygmodel.YouTubeVideo.get_by_key_name("v_" + prevsettings.video1.youtubeid)
			is_completed = close_out_settings_element(dygmodel.SettingsElementStats.VIDEO_KIND, prev_element, dt_central, loop_limit)

		if is_completed and \
			prevsettings and \
			prevsettings.video2 and \
			prevsettings.video2.youtubeid not in set([youtubeid1,youtubeid2]):
			prev_element = dygmodel.YouTubeVideo.get_by_key_name("v_" + prevsettings.video2.youtubeid)
			is_completed = close_out_settings_element(dygmodel.SettingsElementStats.VIDEO_KIND, prev_element, dt_central, loop_limit)
	elif stats_step == "videostats":
		if is_completed and settings.video1:
			new_element = dygmodel.YouTubeVideo.get_by_key_name("v_" + settings.video1.youtubeid)
			is_completed = update_settings_element_stats(dygmodel.SettingsElementStats.VIDEO_KIND, new_element, dt_central, loop_limit)

		if is_completed and settings.video2:
			new_element = dygmodel.YouTubeVideo.get_by_key_name("v_" + settings.video2.youtubeid)
			is_completed = update_settings_element_stats(dygmodel.SettingsElementStats.VIDEO_KIND, new_element, dt_central, loop_limit)
	elif stats_step == "photocloseout":
		if is_completed and \
			prevsettings and \
			prevsettings.photo1 and \
			prevsettings.photo1.url not in set([photourl1,photourl2,photourl3]):
			prev_element = dygmodel.Photo.get_by_key_name(prevsettings.photo1.url)
			is_completed = close_out_settings_element(dygmodel.SettingsElementStats.PHOTO_KIND, prev_element, dt_central, loop_limit)

		if is_completed and \
			prevsettings and \
			prevsettings.photo2 and \
			prevsettings.photo2.url not in set([photourl1,photourl2,photourl3]):
			prev_element = dygmodel.Photo.get_by_key_name(prevsettings.photo2.url)
			is_completed = close_out_settings_element(dygmodel.SettingsElementStats.PHOTO_KIND, prev_element, dt_central, loop_limit)

		if is_completed and \
			prevsettings and \
			prevsettings.photo3 and \
			prevsettings.photo3.url not in set([photourl1,photourl2,photourl3]):
			prev_element = dygmodel.Photo.get_by_key_name(prevsettings.photo3.url)
			is_completed = close_out_settings_element(dygmodel.SettingsElementStats.PHOTO_KIND, prev_element, dt_central, loop_limit)
	elif stats_step == "photostats":
		if is_completed and settings.photo1:
			new_element = dygmodel.Photo.get_by_key_name(settings.photo1.url)
			is_completed = update_settings_element_stats(dygmodel.SettingsElementStats.PHOTO_KIND, new_element, dt_central, loop_limit)

		if is_completed and settings.photo2:
			new_element = dygmodel.Photo.get_by_key_name(settings.photo2.url)
			is_completed = update_settings_element_stats(dygmodel.SettingsElementStats.PHOTO_KIND, new_element, dt_central, loop_limit)

		if is_completed and settings.photo3:
			new_element = dygmodel.Photo.get_by_key_name(settings.photo3.url)
			is_completed = update_settings_element_stats(dygmodel.SettingsElementStats.PHOTO_KIND, new_element, dt_central, loop_limit)
	elif stats_step == "captioncloseout":
		if is_completed and \
			prevsettings and \
			prevsettings.caption1 and \
			prevsettings.caption1.text != '' and \
			prevsettings.caption1.text not in set([caption1text,caption2text,caption3text]):
			prev_element = dygmodel.Caption.get_by_key_name("c_" + prevsettings.caption1.text)
			is_completed = close_out_settings_element(dygmodel.SettingsElementStats.CAPTION_KIND, prev_element, dt_central, loop_limit)

		if is_completed and \
			prevsettings and \
			prevsettings.caption2 and \
			prevsettings.caption2.text != '' and \
			prevsettings.caption2.text not in set([caption1text,caption2text,caption3text]):
			prev_element = dygmodel.Caption.get_by_key_name("c_" + prevsettings.caption2.text)
			is_completed = close_out_settings_element(dygmodel.SettingsElementStats.CAPTION_KIND, prev_element, dt_central, loop_limit)

		if is_completed and \
			prevsettings and \
			prevsettings.caption3 and \
			prevsettings.caption3.text != '' and \
			prevsettings.caption3.text not in set([caption1text,caption2text,caption3text]):
			prev_element = dygmodel.Caption.get_by_key_name("c_" + prevsettings.caption3.text)
			is_completed = close_out_settings_element(dygmodel.SettingsElementStats.CAPTION_KIND, prev_element, dt_central, loop_limit)
	elif stats_step == "captionstats":
		if is_completed and settings.caption1 and settings.caption1.text != '':
			new_element = dygmodel.Caption.get_by_key_name("c_" + settings.caption1.text)
			is_completed = update_settings_element_stats(dygmodel.SettingsElementStats.CAPTION_KIND, new_element, dt_central, loop_limit)

		if is_completed and settings.caption2 and settings.caption2.text != '':
			new_element = dygmodel.Caption.get_by_key_name("c_" + settings.caption2.text)
			is_completed = update_settings_element_stats(dygmodel.SettingsElementStats.CAPTION_KIND, new_element, dt_central, loop_limit)

		if is_completed and settings.caption3 and settings.caption3.text != '':
			new_element = dygmodel.Caption.get_by_key_name("c_" + settings.caption3.text)
			is_completed = update_settings_element_stats(dygmodel.SettingsElementStats.CAPTION_KIND, new_element, dt_central, loop_limit)
	elif stats_step == "themecloseout":
		if is_completed and prevsettings and prevsettings.theme and prevsettings.theme.stylesheet != settings.theme.stylesheet:
			prev_element = dygmodel.Theme.get_by_key_name(prevsettings.theme.stylesheet)
			is_completed = close_out_settings_element(dygmodel.SettingsElementStats.THEME_KIND, prev_element, dt_central, loop_limit)
	elif stats_step == "themestats":
		if is_completed and settings.theme:
			new_element = dygmodel.Theme.get_by_key_name(settings.theme.stylesheet)
			is_completed = update_settings_element_stats(dygmodel.SettingsElementStats.THEME_KIND, new_element, dt_central, loop_limit)

	return is_completed

def close_out_settings_element(element_kind, element, newdatetime_central, loop_limit=0):
	newhour_central = newdatetime_central.hour
	newday_central = newdatetime_central.day
	newmonth_central = newdatetime_central.month
	newyear_central = newdatetime_central.year

	is_completed = True

	# 1. get most recent hour-level stats for this element

	seshour = dygmodel.SettingsElementStats.gql(
		"WHERE element_kind=:1 AND timespanvalue=:2 AND element=:3 ORDER BY date DESC",
		element_kind, dygmodel.StatsTimeSpan.HOUR_SPAN, element.key()).get()

	# This shouldn't happen, ever, but has happened once.
	if not seshour: return True

	ts = seshour.timespan

	# 2. If duration is not filled in for the hour-level stats, calculate the duration.
	if seshour.duration is None or seshour.duration == 0:
		if ts.year_central == newyear_central and ts.month_central == newmonth_central and ts.day_central == newday_central and ts.hour_central == newhour_central:
			seshour.enddatetime_central = newdatetime_central
			seshour.put()
		# 3. Now fill in new hour level-duration,
		# and roll the new duration into the element stats at day, month, year, and all-time levels.
		set_new_settings_stats_durations(seshour, element_kind, element)

	# 4. Now create and fill in subsequent time spans, up to and including the new date/time.
	new_hour_datetime_central = datetime.datetime(newyear_central, newmonth_central, newday_central, newhour_central)
	this_hour_datetime_central = datetime.datetime(ts.year_central,ts.month_central,ts.day_central,ts.hour_central) + datetime.timedelta(hours=1)
	entitylist = []
	i = 0
	while this_hour_datetime_central <= new_hour_datetime_central:
		i += 1
		if loop_limit > 0 and i > loop_limit:
			is_completed = False
			break

		logging.debug("close_out_settings_element: filling in time spans through " + str(new_hour_datetime_central) + "; currently at " + str(this_hour_datetime_central))
		ts = dygmodel.StatsTimeSpan.get_or_insert_by_values(
			dygmodel.StatsTimeSpan.HOUR_SPAN,
			this_hour_datetime_central.year,
			this_hour_datetime_central.month,
			this_hour_datetime_central.day,
			this_hour_datetime_central.hour)

		seshour = dygmodel.SettingsElementStats.get_or_insert_by_values(element_kind, element, ts)
		if seshour.duration is None or seshour.duration == 0:
			if ts.year_central == newyear_central and ts.month_central == newmonth_central and ts.day_central == newday_central and ts.hour_central == newhour_central:
				seshour.enddatetime_central = newdatetime_central
				entitylist.append(seshour)
			set_new_settings_stats_durations(seshour, element_kind, element)

		this_hour_datetime_central = datetime.datetime(ts.year_central,ts.month_central,ts.day_central,ts.hour_central) + datetime.timedelta(hours=1)

	db.put(entitylist)
	return is_completed

def update_settings_element_stats(element_kind, element, newdatetime_central, loop_limit=0):
	newhour_central = newdatetime_central.hour
	newday_central = newdatetime_central.day
	newmonth_central = newdatetime_central.month
	newyear_central = newdatetime_central.year

	is_completed = True

	# 1. get most recent hour-level stats for this element

	seshour = dygmodel.SettingsElementStats.gql(
		"WHERE element_kind=:1 AND timespanvalue=:2 AND element=:3 ORDER BY date DESC",
		element_kind, dygmodel.StatsTimeSpan.HOUR_SPAN, element.key()).get()
	if seshour and not seshour.enddatetime_central:
		logging.debug("seshour.key()=" + str(seshour.key()))
		ts = seshour.timespan
		this_hour_datetime_central = datetime.datetime(ts.year_central,ts.month_central,ts.day_central,ts.hour_central)
		new_hour_datetime_central = datetime.datetime(newyear_central, newmonth_central, newday_central, newhour_central)

		# update duration, including related day, month, year, and alltime timespans, as long as the hour has passed
		# and a duration isn't already filled in for the hour.
		if this_hour_datetime_central < new_hour_datetime_central and \
			(not seshour.duration or seshour.duration == 0):
			set_new_settings_stats_durations(seshour, element_kind, element)

		# create subsequent timespans up to (but not including) current one.
		logging.debug("current ts.key()=" + str(ts.key()))
		next_hour_datetime_central = datetime.datetime(ts.year_central,ts.month_central,ts.day_central,ts.hour_central) + datetime.timedelta(hours=1)
		entitylist = []
		i = 0
		while next_hour_datetime_central < new_hour_datetime_central:
			i += 1
			if loop_limit > 0 and i > loop_limit:
				is_completed = False
				break

			logging.debug("update_settings_element_stats: filling in time spans through " + str(new_hour_datetime_central) + "; currently at " + str(next_hour_datetime_central))
			ts = dygmodel.StatsTimeSpan.get_or_insert_by_values(
				dygmodel.StatsTimeSpan.HOUR_SPAN,
				next_hour_datetime_central.year,
				next_hour_datetime_central.month,
				next_hour_datetime_central.day,
				next_hour_datetime_central.hour)
			logging.debug("next ts.key()=" + str(ts.key()))

			seshour = dygmodel.SettingsElementStats.get_or_insert_by_values(element_kind, element, ts)
			logging.debug("new seshour.key()=" + str(seshour.key()))
			logging.debug("seshour.element.key()=" + str(seshour.element.key()))
			if seshour.duration is None or seshour.duration == 0:
				set_new_settings_stats_durations(seshour, element_kind, element, entitylist)

			next_hour_datetime_central = datetime.datetime(ts.year_central,ts.month_central,ts.day_central,ts.hour_central) + datetime.timedelta(hours=1)

		db.put(entitylist)

		# As long as we're past the hour of the most recent hour span that had existed, create a new one
		# for the current hour.
		if is_completed and this_hour_datetime_central < new_hour_datetime_central:
			create_element_settings_stats(element_kind, element, newdatetime_central)
	else:
		# Element must be new, or not previously active.  Create empty new stats records.
		create_element_settings_stats(element_kind, element, newdatetime_central, initial=True)

	return is_completed

def create_element_settings_stats(element_kind,element,newdatetime_central,initial=False):
	newhour_central = newdatetime_central.hour
	newday_central = newdatetime_central.day
	newmonth_central = newdatetime_central.month
	newyear_central = newdatetime_central.year

	if not dygmodel.StatsTimeSpan.all().get():
		dygchatdata.initialize_stats_timespans(newdatetime_central)

	entitylist = []

	tshour = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.HOUR_SPAN, newyear_central, newmonth_central, newday_central, newhour_central)
	seshour = dygmodel.SettingsElementStats.get_or_insert_by_values(element_kind=element_kind, element=element, timespan=tshour)
	if initial: seshour.startdatetime_central = newdatetime_central
	entitylist.append(seshour)
	tsday = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.DAY_SPAN, newyear_central, newmonth_central, newday_central, 0)
	sesday = dygmodel.SettingsElementStats.get_or_insert_by_values(element_kind=element_kind, element=element, timespan=tsday)
	if initial: sesday.startdatetime_central = newdatetime_central
	entitylist.append(sesday)
	tsmonth = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.MONTH_SPAN, newyear_central, newmonth_central, 1, 0)
	sesmonth = dygmodel.SettingsElementStats.get_or_insert_by_values(element_kind=element_kind, element=element, timespan=tsmonth)
	if initial: sesmonth.startdatetime_central = newdatetime_central
	entitylist.append(sesmonth)
	tsyear = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.YEAR_SPAN, newyear_central, 1, 1, 0)
	sesyear = dygmodel.SettingsElementStats.get_or_insert_by_values(element_kind=element_kind, element=element, timespan=tsyear)
	if initial: sesyear.startdatetime_central = newdatetime_central
	entitylist.append(sesyear)
	tsalltime = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.ALL_TIME_SPAN, 0, 0, 0, 0)
	sesalltime = dygmodel.SettingsElementStats.get_or_insert_by_values(element_kind=element_kind, element=element, timespan=tsalltime)
	if initial: sesalltime.startdatetime_central = newdatetime_central
	entitylist.append(sesalltime)

	db.put(entitylist)

def set_new_settings_stats_durations(seshour, element_kind, element, entitylist=None):
	ts = seshour.timespan

	tsday = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.DAY_SPAN, ts.year_central, ts.month_central, ts.day_central, 0)
	sesday = dygmodel.SettingsElementStats.get_or_insert_by_values(element_kind, element, tsday)
	tsmonth = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.MONTH_SPAN, ts.year_central, ts.month_central, 1, 0)
	sesmonth = dygmodel.SettingsElementStats.get_or_insert_by_values(element_kind, element, tsmonth)
	tsyear = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.YEAR_SPAN, ts.year_central, 1, 1, 0)
	sesyear = dygmodel.SettingsElementStats.get_or_insert_by_values(element_kind, element, tsyear)
	tsalltime = dygmodel.StatsTimeSpan.get_or_insert_by_values(dygmodel.StatsTimeSpan.ALL_TIME_SPAN, 0, 0, 0, 0)
	sesalltime = dygmodel.SettingsElementStats.get_or_insert_by_values(element_kind, element, tsalltime)

	if seshour.enddatetime_central:
		enddatetime_central = seshour.enddatetime_central
	else:
		enddatetime_central = datetime.datetime(ts.year_central,ts.month_central,ts.day_central,ts.hour_central,tzinfo=dygutil.Central_tzinfo()) + datetime.timedelta(hours=1)
	if seshour.startdatetime_central:
		startdatetime_central = seshour.startdatetime_central
	else:
		startdatetime_central = datetime.datetime(ts.year_central,ts.month_central,ts.day_central,ts.hour_central,tzinfo=dygutil.Central_tzinfo())

	if not startdatetime_central.tzinfo:
		startdatetime_central = startdatetime_central.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo())
	if not enddatetime_central.tzinfo:
		enddatetime_central = enddatetime_central.replace(tzinfo=dygutil.UTC_tzinfo()).astimezone(dygutil.Central_tzinfo())

	logging.debug("startdatetime_central=" + str(startdatetime_central) + ",enddatetime_central=" + str(enddatetime_central))
	td = enddatetime_central - startdatetime_central
	update_settings_stats_durations(
		float(td.days*24 + float(td.seconds)/3600),
		seshour.enddatetime_central,
		ts.postcount,
		ts.uniqueteamspostingcount,
		seshour.key(),
		sesday.key(),
		sesmonth.key(),
		sesyear.key(),
		sesalltime.key(),
		entitylist)

def update_settings_stats_durations(new_duration, new_end_date_time_central, postcount, uniqueteamspostingcount, hour_key_val, day_key_val, month_key_val, year_key_val, all_time_key_val,entitylist=None):
	ses = dygmodel.SettingsElementStats.get(hour_key_val)
	if ses:
		ses.duration += new_duration
		ses.enddatetime_central = new_end_date_time_central
		ses.postcount += postcount
		ses.uniqueteamspostingcount += uniqueteamspostingcount
		if entitylist:
			entitylist.append(ses)
		else:
			ses.put()

	ses = dygmodel.SettingsElementStats.get(day_key_val)
	if ses:
		ses.duration += new_duration
		ses.enddatetime_central = new_end_date_time_central
		ses.postcount += postcount
		ses.uniqueteamspostingcount += uniqueteamspostingcount
		if entitylist:
			entitylist.append(ses)
		else:
			ses.put()

	ses = dygmodel.SettingsElementStats.get(month_key_val)
	if ses:
		ses.duration += new_duration
		ses.enddatetime_central = new_end_date_time_central
		ses.postcount += postcount
		ses.uniqueteamspostingcount += uniqueteamspostingcount
		if entitylist:
			entitylist.append(ses)
		else:
			ses.put()

	ses = dygmodel.SettingsElementStats.get(year_key_val)
	if ses:
		ses.duration += new_duration
		ses.enddatetime_central = new_end_date_time_central
		ses.postcount += postcount
		ses.uniqueteamspostingcount += uniqueteamspostingcount
		if entitylist:
			entitylist.append(ses)
		else:
			ses.put()

	ses = dygmodel.SettingsElementStats.get(all_time_key_val)
	if ses:
		ses.duration += new_duration
		ses.enddatetime_central = new_end_date_time_central
		ses.postcount += postcount
		ses.uniqueteamspostingcount += uniqueteamspostingcount
		if entitylist:
			entitylist.append(ses)
		else:
			ses.put()

def get_latest_settings(currentdate=None):
	if currentdate:
		q = db.GqlQuery("SELECT * FROM PageSettings " +
						"WHERE date < :1 " +
						"ORDER BY date DESC", currentdate)
	else:
		q = db.GqlQuery("SELECT * FROM PageSettings " +
						"ORDER BY date DESC")
	return q.get()
