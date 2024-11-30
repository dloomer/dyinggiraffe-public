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
from __future__ import with_statement

import logging
import datetime, time, calendar
import re
import struct
import UserDict
import locale
import cookielib
import Cookie
import urllib

import gdata.youtube
import gdata.youtube.service
import gdata.urlfetch

from urlparse import urlparse
from StringIO import StringIO
from Cookie import BaseCookie

from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.api import images
from google.appengine.api import users

import dygsettingsdata
import dygchatdata
import dygmodel

gdata.service.http_request_handler = gdata.urlfetch

class Central_tzinfo(datetime.tzinfo):
	"""Implementation of the Pacific timezone."""
	def utcoffset(self, dt):
		return datetime.timedelta(hours=-6) + self.dst(dt)

	def _FirstSunday(self, dt):
		"""First Sunday on or after dt."""
		return dt + datetime.timedelta(days=(6-dt.weekday()))

	def dst(self, dt):
		# 2 am on the second Sunday in March
		dst_start = self._FirstSunday(datetime.datetime(dt.year, 3, 8, 2))
		# 1 am on the first Sunday in November
		dst_end = self._FirstSunday(datetime.datetime(dt.year, 11, 1, 1))

		if dst_start <= dt.replace(tzinfo=None) < dst_end:
			return datetime.timedelta(hours=1)
		else:
			return datetime.timedelta(hours=0)

	def tzname(self, dt):
		if self.dst(dt) == datetime.timedelta(hours=0):
			return "CST"
		else:
			return "CDT"

class UTC_tzinfo(datetime.tzinfo):
	"""Implementation of the UTC timezone."""
	def utcoffset(self, dt):
		return datetime.timedelta(hours=0) + self.dst(dt)

	def _FirstSunday(self, dt):
		"""First Sunday on or after dt."""
		return dt + datetime.timedelta(days=(6-dt.weekday()))

	def dst(self, dt):
		return datetime.timedelta(hours=0)

	def tzname(self, dt):
		return "UTC"

class Pacific_tzinfo(datetime.tzinfo):
	"""Implementation of the Eastern timezone."""
	def utcoffset(self, dt):
		return datetime.timedelta(hours=-8) + self.dst(dt)

	def _FirstSunday(self, dt):
		"""First Sunday on or after dt."""
		return dt + datetime.timedelta(days=(6-dt.weekday()))

	def dst(self, dt):
		# 2 am on the second Sunday in March
		dst_start = self._FirstSunday(datetime.datetime(dt.year, 3, 8, 2))
		# 1 am on the first Sunday in November
		dst_end = self._FirstSunday(datetime.datetime(dt.year, 11, 1, 1))

		if dst_start <= dt.replace(tzinfo=None) < dst_end:
			return datetime.timedelta(hours=1)
		else:
			return datetime.timedelta(hours=0)

	def tzname(self, dt):
		if self.dst(dt) == datetime.timedelta(hours=0):
			return "PST"
		else:
			return "PDT"

def save_gcs_object(data, file_name, content_type='application/octet-stream', options=None):
	import cloudstorage as gcs
	from google.appengine.ext import blobstore
	from google.appengine.api import app_identity

	bucket_name = app_identity.get_default_gcs_bucket_name()

	if not file_name.startswith("/" + bucket_name):
		file_name = "/" + bucket_name + file_name

	# Open the file and write to it
	with gcs.open(file_name, 'w', content_type=content_type, options=options) as f:
		f.write(data)

	# Blobstore API requires extra /gs to distinguish against blobstore files.
	blobstore_filename = '/gs' + file_name
	blob_key = blobstore.create_gs_key(blobstore_filename)
	return blob_key

def save_to_blobstore(data, mime_type):
	from google.appengine.api import files

	# Create the file
	file_name = files.blobstore.create(mime_type=mime_type)

	# Open the file and write to it
	with files.open(file_name, 'a') as f:
	  f.write(data)

	# Finalize the file. Do this before attempting to read it.
	files.finalize(file_name)
	return files.blobstore.get_blob_key(file_name)

def urlify(txt, suppress_images=False):
	from urlparse import urlparse

	media = []
	if txt.find('http') >= 0:
		last_end = 0
		urlified = ""
		for match in re.finditer('((?:http|https)://(?:[^ \n\r<\)]+))(\s)', txt + ' '):
			matched = match.group(0).strip()
			import logging
			logging.info("matched=%s" % matched)
			base_url = matched
			if base_url.find("?") > 0: base_url = base_url[:base_url.find("?")]

			urlinfo = urlparse(base_url)
			url_hostname = urlinfo.hostname + (':' + str(urlinfo.port) if urlinfo.port else '')
			internal_photo = get_internal_photo(base_url)
			if internal_photo:
				media.append({
					'type': "photo",
					'source_url': matched,
					'image_url': matched,
					'db_photo': internal_photo,
				})

			if internal_photo and base_url.find("/uploads/") >= 0:
				display_url = "Uploaded photo"
			else:
				display_url = matched
				if len(display_url) > 80:
					display_url = display_url[:40] + "..." + display_url[-40:]
			urlified += txt[last_end:match.start(0)] + '<a href="%s" target="_blank">%s</a>' % (matched, display_url) + " "
			last_end = match.end(0)

			if not internal_photo:
				if base_url.lower().endswith(".jpg") or base_url.lower().endswith(".jpeg") or base_url.lower().endswith(".png") or base_url.lower().endswith(".gif"):
					media.append({
						'type': "photo",
						'source_url': matched,
						'image_url': matched,
					})
				elif matched.find("youtube.com/") >= 0 or matched.find("youtu.be/") >= 0:
					youtube_id = get_youtube_id(matched)
					if youtube_id:
						media.append({
							'type': "youtube",
							'source_url': matched,
							'youtube_id': youtube_id,
						})
				elif matched.find("fuckyeahnouns.com/") >= 0:
					term = matched.split('/')[-1]
					media.append({
						'type': "photo",
						'source_url': matched,
						'image_url': "http://fuckyeahnouns.com/images/%s.jpg" % term,
					})
					import logging
					logging.info("media=%s" % media)
				elif matched.find("fuckyeah.herokuapp.com/") >= 0:
					term = matched.split('/')[-1]
					media.append({
						'type': "photo",
						'source_url': matched,
						'image_url': matched,
					})
					import logging
					logging.info("media=%s" % media)
				elif matched.find("twitter.com/") >= 0:
					parts = matched.split('/')
					if len(parts) > 5 and parts[4].lower() in ["status", "statuses"]:
						import logging
						logging.info("parts=%s" % parts)
						try:
							status_str = parts[5]
							if status_str.find("?") > 0:
								status_str = status_str[:status_str.find("?")]
							status_id = int(status_str)
							media.append({
								'type': "tweet",
								'source_url': matched,
								'status_id': status_id,
							})
						except:
							pass
		if last_end < len(txt):
			urlified += txt[last_end:]
		for m in media:
			if m['type'] == "youtube":
				if m.get('youtube_id'):
					video = dygmodel.YouTubeVideo.get_or_insert("v_" + m['youtube_id'],youtubeid=m['youtube_id'],date=datetime.datetime.now())
					if not video.title:
						try:
							youtubeinfo = getYoutubeInfo(video.youtubeid)
							video.title = youtubeinfo[0]
							video.thumbnaildata = getImageThumbnail(getImageUrlInfo(youtubeinfo[1])[0],200,150, constrain=True)
						except:
							pass
						video.put()

					m['video_key'] = str(video.key())
			elif m['type'] == "tweet":
				if m.get('status_id'):
					parms = {'id': m['status_id'], 'maxwidth': 500, 'hide_thread': 1, 'omit_script': 1}
					response = get_tweepy_response("get_oembed", **parms)
					import logging
					logging.info("tweepy response=%s" % response)
					m['embed_html'] = response['html']
					#Make sure <script> block is on page
					#<script async src="//platform.twitter.com/widgets.js" charset="utf-8"></script>
			else:
				if m.get('db_photo'):
					photo = m['db_photo']
					del m['db_photo']
				else:
					photo = get_internal_photo(m['image_url'])
					if not photo:
						photo = dygmodel.Photo.get_or_insert(m['image_url'],url=m['image_url'],date=datetime.datetime.now())
				if not photo.photo_blob_key and not photo.photo_gcs_blob_key:
					if photo.photodata:
						photo_info = getImageInfo(photo.photodata)
						thumb = getImageThumbnail(photo.photodata,300,180, constrain=True)
						thumb_info = getImageInfo(thumb)

						file_name = "/images/%s/o.jpg" % dygmodel.Photo.gcs_image_name(photo.url)
						photo.photo_gcs_blob_key = save_gcs_object(photo.photodata, file_name, content_type=photo_info[0], options={'x-goog-acl': 'public-read'})

						file_name = "/images/%s/t.jpg" % dygmodel.Photo.gcs_image_name(photo.url)
						photo.thumbnail_gcs_blob_key = save_gcs_object(thumb, file_name, content_type=thumb_info[0], options={'x-goog-acl': 'public-read'})

						#photo.photo_blob_key = str(save_to_blobstore(photo.photodata, photo_info[0]))
						#photo.thumbnail_blob_key = str(save_to_blobstore(thumb, thumb_info[0]))
						photo.photodata = None
						photo.thumbnaildata = None
					else:
						photo_info = getImageUrlInfo(photo.url)
						content_type = photo_info[1][0]
						photo.width = photo_info[1][1]
						photo.height = photo_info[1][2]

						file_name = "/images/%s/o.jpg" % dygmodel.Photo.gcs_image_name(photo.url)
						photo.photo_gcs_blob_key = save_gcs_object(photo_info[0], file_name, content_type=photo_info[1][0], options={'x-goog-acl': 'public-read'})

						#photo.photo_blob_key = str(save_to_blobstore(photo_info[0], photo_info[1][0]))
						if content_type == "image/gif" or photo.url.lower().endswith(".gif"):
							file_name = "/images/%s/t.jpg" % dygmodel.Photo.gcs_image_name(photo.url)
							photo.thumbnail_gcs_blob_key = save_gcs_object(photo_info[0], file_name, content_type=photo_info[1][0], options={'x-goog-acl': 'public-read'})
							thumbnail_width = photo.width
							thumbnail_height = photo.height
						else:
							thumb = getImageThumbnail(photo_info[0],300,180, constrain=True)
							thumb_info = getImageInfo(thumb)
							try:
								file_name = "/images/%s/t.jpg" % dygmodel.Photo.gcs_image_name(photo.url)
								photo.thumbnail_gcs_blob_key = save_gcs_object(thumb, file_name, content_type=thumb_info[0], options={'x-goog-acl': 'public-read'})

								#photo.thumbnail_blob_key = str(save_to_blobstore(thumb, thumb_info[0]))
								thumbnail_width = thumb_info[1]
								thumbnail_height = thumb_info[2]
							except:
								photo.thumbnail_gcs_blob_key = photo.photo_gcs_blob_key
								#photo.thumbnail_blob_key = photo.photo_blob_key
								thumbnail_width = photo.width
								thumbnail_height = photo.height
						photo.thumbnail_width = thumbnail_width
						photo.thumbnail_height = thumbnail_height
					photo.put()
				else:
					# TODO
					if photo.thumbnail_width:
						thumbnail_width = photo.thumbnail_width
						thumbnail_height = photo.thumbnail_height
					else:
						from google.appengine.ext import blobstore
						if photo.thumbnail_blob_key:
							thumb = blobstore.BlobInfo.get(photo.thumbnail_blob_key).open().read()
						else:
							thumb = blobstore.BlobReader(photo.thumbnail_gcs_blob_key).read()
						thumb_info = getImageInfo(thumb)
						thumbnail_width = thumb_info[1]
						thumbnail_height = thumb_info[2]
				m['photo_key'] = str(photo.key())
				m['photo_width'] = photo.width
				m['photo_height'] = photo.height
				m['thumbnail_width'] = thumbnail_width
				m['thumbnail_height'] = thumbnail_height
				m['photo_blob_key'] = photo.photo_blob_key
				m['thumbnail_blob_key'] = photo.thumbnail_blob_key
				m['photo_gcs_blob_key'] = photo.photo_gcs_blob_key
				m['thumbnail_gcs_blob_key'] = photo.thumbnail_gcs_blob_key
				m['photo_serving_url'] = photo.serving_url()
				m['thumbnail_serving_url'] = photo.serving_url(size="t")
				m['popup_height'] = photo.popupheight()
				m['popup_width'] = photo.popupwidth()
	else:
		urlified = txt
	return urlified.strip(), media

def string_to_datetime(s):
	ms = 0
	period = s.find('.')
	if period >= 0:
		s_ms = s[period+1:]
		if len(s_ms) > 3: s_ms = s_ms[:3] + '.' + s_ms[3:]
		ms = float(s_ms)
		s = s[0:period]

	return datetime.datetime(*time.strptime(s,"%Y-%m-%d %H:%M:%S")[:6]) + datetime.timedelta(milliseconds=ms)

def get_youtube_id(url):
	if url.find("&eurl=") >= 0:
		url = url[:url.find("&eurl=")]
	urlinfo = urlparse(url)
	if urlinfo.query:
		if urlinfo.query.find("=") >= 0:
			params = dict([part.split('=') for part in urlinfo.query.split('&')])
			return params.get('v', None)
		else:
			return None
	else:
		if urlinfo.path[1:].find("/") < 0:
			return urlinfo.path[1:]

def get_url_filename(url):
	urlinfo = urlparse(url)
	pathparts = urlinfo.path.split("/")
	return pathparts[len(pathparts)-1]

def wrap_url(url, maxcharwidth):
	parts = url.split("/")
	new_str = ""
	cur_length = 0
	for part in parts:
		if cur_length + len(part) < maxcharwidth:
			new_str += part + "/"
		else:
			new_str += " " + part + "/"
			cur_length = 0
		cur_length += len(part + "/")

	return new_str[:len(new_str)-1]

def settings_to_memcache(settings):
	if settings:
		memcache.set("settings", settings.to_dict())

		logging.info("settings.to_dict()=%s" % settings.to_dict())
		# Weird bug popped up making this necessary.
		assert memcache.get("settings") is not None
	else:
		memcache.set("settings", {})

def getImageUrlInfo(url):
	from google.appengine.runtime import apiproxy_errors
	from google.appengine import runtime
	max_retries=15
	response = None
	for i in range(max_retries):
		try:
			response = urlfetch.fetch(url, deadline=10)
			break
		except runtime.DeadlineExceededError:
			if (i == max_retries-1):
				import logging
				try:
					logging.error("Error accessing url " + url)
				except:
					logging.error("Error accessing URL")
				raise
			import logging
			logging.warning("DeadlineExceededError loading URL %s after %s attempts; will retry" % (url, i+1))
		except apiproxy_errors.DeadlineExceededError:
			if (i == max_retries-1):
				import logging
				try:
					logging.error("Error accessing url " + url)
				except:
					logging.error("Error accessing URL")
				raise
			import logging
			logging.warning("DeadlineExceededError loading URL %s after %s attempts; will retry" % (url, i+1))
		except:
			if (i == max_retries-1):
				import logging
				try:
					logging.error("Error accessing url " + url)
				except:
					logging.error("Error accessing URL")
				raise
			import sys
			e = sys.exc_value
			if str(e).find("ApplicationError: 5") >= 0 or str(e).find("ApplicationError: 2") >= 0 or str(e).find("The API call urlfetch.Fetch() took too long to respond and was cancelled") >= 0 or str(e).find("Deadline exceeded") >= 0 or str(e).find("Unable to fetch URL:") >= 0:
				import logging
				logging.warning("Error '%s' loading URL %s after %s attempts; will retry" % (e, url, i+1))
			else:
				raise

	info = getImageInfo(response.content)
	return response.content, info

def getImageInfo(data):
	data = str(data)
	size = len(data)
	height = -1
	width = -1
	content_type = ''
	# handle GIFs
	if (size >= 10) and data[:6] in ('GIF87a', 'GIF89a'):
		# Check to see if content_type is correct
		content_type = 'image/gif'
		w, h = struct.unpack("<HH", data[6:10])
		width = int(w)
		height = int(h)
	# See PNG 2. Edition spec (http://www.w3.org/TR/PNG/)
	# Bytes 0-7 are below, 4-byte chunk length, then 'IHDR'
	# and finally the 4-byte width, height
	elif ((size >= 24) and data.startswith('\211PNG\r\n\032\n')
		  and (data[12:16] == 'IHDR')):
		content_type = 'image/png'
		w, h = struct.unpack(">LL", data[16:24])
		width = int(w)
		height = int(h)
	# Maybe this is for an older PNG version.
	elif (size >= 16) and data.startswith('\211PNG\r\n\032\n'):
		# Check to see if we have the right content type
		content_type = 'image/png'
		w, h = struct.unpack(">LL", data[8:16])
		width = int(w)
		height = int(h)
	# handle JPEGs
	elif (size >= 2) and data.startswith('\377\330'):
		content_type = 'image/jpeg'
		jpeg = StringIO(data)
		jpeg.read(2)
		b = jpeg.read(1)
		try:
			while (b and ord(b) != 0xDA):
				while (ord(b) != 0xFF): b = jpeg.read
				while (ord(b) == 0xFF): b = jpeg.read(1)
				if (ord(b) >= 0xC0 and ord(b) <= 0xC3):
					jpeg.read(3)
					h, w = struct.unpack(">HH", jpeg.read(4))
					break
				else:
					jpeg.read(int(struct.unpack(">H", jpeg.read(2))[0])-2)
				b = jpeg.read(1)
			width = int(w)
			height = int(h)
		except struct.error:
			pass
		except ValueError:
			pass
	return content_type, width, height

def getYoutubeInfo(youtubeid):
	yt_service = gdata.youtube.service.YouTubeService()
	entry = yt_service.GetYouTubeVideoEntry(video_id=youtubeid)

	thumburl = entry.media.thumbnail[0].url
	for thumbnail in entry.media.thumbnail:
	   if int(thumbnail.width) >= 320:
		  thumburl = thumbnail.url
		  break
	return unicode(entry.media.title.text,'utf-8'), thumburl

def getImageThumbnail(data, width, height, constrain=False):
	info = getImageInfo(data)
	new_width, new_height = get_resized_image_dimensions(info[1], info[2], width, height, constrain=constrain)

	img = images.Image(data)
	img.resize(int(new_width), int(new_height))
	#return img.execute_transforms(output_encoding=images.JPEG)
	try:
		return img.execute_transforms(output_encoding=images.JPEG)
	except:
		return img

def get_resized_image_dimensions(current_width, current_height, desired_width, desired_height, constrain=False):
	desired_width = float(desired_width)
	desired_height = float(desired_height)

	current_width = float(current_width)
	current_height = float(current_height)

	if current_width > desired_width or current_height > desired_height:
		if constrain:
			# constrain = ensure both dimensions are within desired box.
			if (current_width / desired_width) <= (current_height / desired_height):
				# width needs less adjustment; set height within desired value and scale width as appropriate.
				new_height = min(desired_height, current_height)
				new_width = (new_height/current_height) * current_width
			else:
				# height needs less adjustment; set width within desired value and scale height as appropriate.
				new_width = min(desired_width, current_width)
				new_height = (new_width/current_width) * current_height
		else:
			# just make sure one dimension is within desired boundary. Correct dimension that needs most adjustment.
			if (current_width / desired_width) <= (current_height / desired_height):
				# width needs less adjustment; set width within desired value and scale height as appropriate.
				new_width = min(desired_width, current_width)
				new_height = (new_width/current_width) * current_height
			else:
				# height needs less adjustment; set height within desired value and scale width as appropriate.
				new_height = min(desired_height, current_height)
				new_width = (new_height/current_height) * current_width
	else:
		new_width = current_width
		new_height = current_height

	return new_width, new_height

def http_login(url, payload):
	from google.appengine.runtime import apiproxy_errors

	max_retries = 10
	response = None
	for i in range(max_retries):
		try:
			response = urlfetch.fetch(url, payload, urlfetch.POST, {}, False, False)
			break
		except apiproxy_errors.DeadlineExceededError:
			if (i == max_retries-1):
				try:
					logging.error("Error accessing url " + url)
				except:
					logging.error("Error accessing URL")
				raise
			logging.warning("DeadlineExceededError loading URL %s after %s attempts; will retry" % (url, i+1))
		except:
			if (i == max_retries-1):
				try:
					logging.error("Error accessing url " + url)
				except:
					logging.error("Error accessing URL")
				raise
			import sys
			e = sys.exc_value
			if str(e).find("ApplicationError: 5") >= 0 or str(e).find("ApplicationError: 2") >= 0 or str(e).find("The API call urlfetch.Fetch() took too long to respond and was cancelled") >= 0 or str(e).find("Deadline exceeded") >= 0 or str(e).find("Unable to fetch URL:") >= 0:
				logging.warning("Error '%s' loading URL %s after %s attempts; will retry" % (e, url, i+1))
			else:
				raise

	logging.info(response.content)

	sc = Cookie.SimpleCookie()
	logging.info("response.headers=%s" % response.headers.keys())
	logging.info("response.headers['set-cookie']=%s" % response.headers['set-cookie'])

	sc.load(response.headers['set-cookie'])

	cookie = ""
	for a, b in sc.items():
		cookie += b.key + "=" + b.value + ";"

	logging.info("cookie=%s" % cookie)
	# cookie=fly-sess=;

	return cookie

def get_page(cookie, url):
	from google.appengine.runtime import apiproxy_errors
	logging.info("getting %s" % url)
	max_retries = 10
	response = None
	for i in range(max_retries):
		try:
			if cookie:
				response = urlfetch.fetch(url, None, urlfetch.GET,
									  {'cookie': cookie})
			else:
				response = urlfetch.fetch(url, None, urlfetch.GET)
			break
		except apiproxy_errors.DeadlineExceededError:
			if (i == max_retries-1):
				try:
					logging.error("Error accessing url " + url)
				except:
					logging.error("Error accessing URL")
				raise
			logging.warning("DeadlineExceededError loading URL %s after %s attempts; will retry" % (url, i+1))
		except:
			if (i == max_retries-1):
				try:
					logging.error("Error accessing url " + url)
				except:
					logging.error("Error accessing URL")
				raise
			import sys
			e = sys.exc_value
			if str(e).find("ApplicationError: 5") >= 0 or str(e).find("ApplicationError: 2") >= 0 or str(e).find("The API call urlfetch.Fetch() took too long to respond and was cancelled") >= 0 or str(e).find("Deadline exceeded") >= 0 or str(e).find("Unable to fetch URL:") >= 0:
				logging.warning("Error '%s' loading URL %s after %s attempts; will retry" % (e, url, i+1))
			else:
				raise

	return unicode(response.content, 'latin-1')

def make_themes():
	t = dygmodel.Theme(name="Basic", stylesheet="basic.css", key_name="basic.css")
	t.put()
	t = dygmodel.Theme(name="Brewiz", stylesheet="brewers.css", key_name="brewers.css")
	t.put()
	t = dygmodel.Theme(name="Cub-ez", stylesheet="cubs.css", key_name="cubs.css")
	t.put()
	t = dygmodel.Theme(name="Packiz", stylesheet="packers.css", key_name="packers.css")
	t.put()
	t = dygmodel.Theme(name="Da Bearz", stylesheet="bears.css", key_name="bears.css")
	t.put()
	t = dygmodel.Theme(name="X-Maz", stylesheet="xmas.css", key_name="xmas.css")
	t.put()

def getteamid(handler, enforce=False):
	cookies = Cookies(handler,max_age=5*365*24*60*60)
	teamid = cookies.get('teamid')
	import logging
	logging.info("teamid=%s" % teamid)
	if teamid and teamid != "":
		team_key_name = teamid
		if enforce:
			team = dygchatdata.fetch_team(team_key_name)
			if not team:
				handler.redirect("/login")
				return None
			if team.user_google_login == True:
				if (not users.get_current_user()) or (users.get_current_user().email().lower() != team.google_id):
					handler.redirect(users.create_login_url(handler.request.path))
		logging.info("returning %s" % team_key_name)
		return team_key_name
	else:
		if enforce: handler.redirect("/login")

def getkeeperids(handler):
	playerids = []
	cookies = Cookies(handler,max_age=5*365*24*60*60)
	keep_players = cookies.get('keep_players')
	import logging
	logging.info("cookies=%s" % cookies)
	logging.info("handler.request.cookies=%s" % handler.request.cookies)

	if keep_players and keep_players != "":
		for playerid in keep_players.split('|'):
			playerids.append(int(playerid))

	return playerids

def gethidephotos(handler):
	cookies = Cookies(handler,max_age=5*365*24*60*60)
	if cookies.get('hidephotos') and cookies['hidephotos'] != "":
		return (cookies['hidephotos']=="True")
	else:
		return False

def gethidecountdown(handler):
	cookies = Cookies(handler,max_age=5*365*24*60*60)
	if cookies.get('hidecountdown') and cookies['hidecountdown'] != "":
		return (cookies['hidecountdown']=="True")
	else:
		return False

def gethideinlinemedia(handler):
	cookies = Cookies(handler,max_age=5*365*24*60*60)
	if cookies.get('hideinlinemedia') and cookies['hideinlinemedia'] != "":
		return (cookies['hideinlinemedia']=="True")
	else:
		return False

def get_mancow(handler):
	cookies = Cookies(handler,max_age=5*365*24*60*60)
	if cookies.get('mancow') and cookies['mancow'] != "":
		return (cookies['mancow']=="True")
	else:
		return False

def setteamid(handler, teamid):
	cookies = Cookies(handler,max_age=5*365*24*60*60)
	cookies['teamid'] = teamid

def set_mancow(handler):
	cookies = Cookies(handler,max_age=5*365*24*60*60)
	cookies['mancow'] = True

def sethidephotos(handler, hidephotos):
	cookies = Cookies(handler,max_age=5*365*24*60*60)
	cookies['hidephotos'] = hidephotos

def sethidecountdown(handler, hidecountdown):
	cookies = Cookies(handler,max_age=5*365*24*60*60)
	cookies['hidecountdown'] = hidecountdown

def sethideinlinemedia(handler, hideinlinemedia):
	cookies = Cookies(handler,max_age=5*365*24*60*60)
	cookies['hideinlinemedia'] = hideinlinemedia

def logout(handler):
	cookies = Cookies(handler,max_age=5*365*24*60*60)
	if cookies.get('teamid'):
		cookies['teamid'] = ""
	if cookies.get('hidephotos'):
		cookies['hidephotos'] = ""

def words_from_text(text, minlength=1, stopwords=None, unique=False):
	words = re.compile(r'\w+').findall(text.lower())
	words = [word for word in words if len(word) >= minlength]
	if unique:
		words = list(set(words))
	if stopwords:
		words = [word for word in words if word not in stopwords]
	return words

def fetch_stopwords():
	stopwords = memcache.get("stopwords")
	if not stopwords:
		stopwords = open('stop_words.txt', 'r').read().split()
		memcache.add("stopwords", stopwords)
	return stopwords

def get_browser_info(req):
	agent = str(req.headers["user-agent"]).lower()
	browser = "unknown"
	os = "unknown"
	if agent.find("firefox") >= 0:
		browser = "firefox"
	elif agent.find("safari") >= 0:
		browser = "safari"
	elif agent.find("msie") >= 0:
		browser = "ie"
	elif agent.find("opera") >= 0:
		browser = "opera"
	elif agent.find("chrome") >= 0:
		browser = "chrome"

	if agent.find("windows") >= 0:
		os = "windows"
	elif agent.find("os x") >= 0:
		os = "os x"
	elif agent.find("macintosh") >= 0:
		os = "mac"
	elif agent.find("linux") >= 0:
		os = "linux"
	elif agent.find("unix") >= 0:
		os = "unix"

	return {'browser': browser, 'os': os,}

def format_number(num, places=0):
	#locale.setlocale(locale.LC_ALL, "")
	#return locale.format("%.*f", (places, num), grouping=True)
	s = str(num)
	num_commas = (len(s)-1)/3
	num_chunks = num_commas
	if len(s) > num_chunks * 3: num_chunks += 1
	r = ""
	last_end = 0
	for i in range(0, num_chunks):
		if i == 0:
			l = len(s) - num_commas * 3
		else:
			l = 3
		start = last_end
		end = start+l
		r += s[start:end] + ","
		last_end = end
	return r[0:len(r)-1]

def add_months_to_datetime(dt,months=1,first_day_of_month=True):
	m = dt.month + months
	y = dt.year
	if m > 12:
		y +=1
		m += -12
	elif m < 1:
		y += -1
		m += 12
	if first_day_of_month:
		d = 1
	else:
		d = dt.day
	return dt.replace(year=y,month=m,day=d)

def get_internal_photo(url):
	from google.appengine.api import app_identity
	default_version_hostname = app_identity.get_default_version_hostname()
	#logging.info("default_version_hostname=%s" % default_version_hostname)

	urlinfo = urlparse(url)
	url_hostname = urlinfo.hostname + (':' + str(urlinfo.port) if urlinfo.port else '')
	photo = None
	if urlinfo.hostname.find("dyinggiraffe") >= 0 or url_hostname.find(default_version_hostname) >= 0:
		if urlinfo.path.startswith('/blobstore/') or urlinfo.path.startswith('/uploads/'):
			base_url = url
			if base_url.find("?") > 0: base_url = base_url[:base_url.find("?")]
			photo = dygmodel.Photo.get_by_key_name(base_url)
		elif urlinfo.query:
			try:
				params = dict([part.split('=') for part in urlinfo.query.split('&')])
			except:
				logging.info("url=%s; urlinfo.query=%s" % (url, urlinfo.query))
				raise
			key = params.get('photokey', None)
			if key: photo = dygmodel.Photo.get(key)

	return photo

def get_month_name(m):
	return ["January","February","March","April","May","June","July","August","September","October","November","December"][m-1]

_LegalCharsPatt	 = r"\w\d!#%&'~_`><@,:/\$\*\+\-\.\^\|\)\(\?\}\{\="
_FixedCookiePattern = re.compile(
	r"(?x)"						  # This is a Verbose pattern
	r"(?P<key>"					  # Start of group 'key'
	"["+ _LegalCharsPatt +"]+?"		# Any word of at least one letter, nongreedy
	r")"						  # End of group 'key'
	r"\s*=\s*"					  # Equal Sign
	r"(?P<val>"					  # Start of group 'val'
	r'"(?:[^\\"]|\\.)*"'			# Any doublequoted string
	r"|"							# or
	"["+ _LegalCharsPatt +"\ ]*"		# Any word or empty string
	r")"						  # End of group 'val'
	r"\s*;?"					  # Probably ending in a semi-colon
	)

def calculate_age(born):
	"""Calculate the age of a user."""
	today = datetime.date.today()
	try:
		birthday = datetime.date(today.year, born.month, born.day)
	except ValueError:
		# Raised when person was born on 29 February and the current
		# year is not a leap year.
		birthday = datetime.date(today.year, born.month, born.day - 1)
	if birthday > today:
		return today.year - born.year - 1
	else:
		return today.year - born.year

class FixedCookie(Cookie.SimpleCookie):
	def load(self, rawdata):
		"""Load cookies from a string (presumably HTTP_COOKIE) or
		from a dictionary.	Loading cookies from a dictionary 'd'
		is equivalent to calling:
			map(Cookie.__setitem__, d.keys(), d.values())
		"""
		if type(rawdata) == type(""):
			self._BaseCookie__ParseString(rawdata, _FixedCookiePattern)
		else:
			self.update(rawdata)
		return

class Cookies(UserDict.DictMixin):
	def __init__(self,handler,**policy):
		self.response = handler.response
		self._in = handler.request.cookies
		self.policy = policy
		if 'secure' not in policy and handler.request.environ.get('HTTPS', '').lower() in ['on', 'true']:
			policy['secure']=True
		self._out = {}
	def __getitem__(self, key):
		if key in self._out:
			return self._out[key]
		if key in self._in:
			return self._in[key]
		raise KeyError(key)
	def __setitem__(self, key, item):
		self._out[key] = item
		self.set_cookie(key, item, **self.policy)
	def __contains__(self, key):
		return key in self._in or key in self._out
	def keys(self):
		return self._in.keys() + self._out.keys()
	def __delitem__(self, key):
		if key in self._out:
			del self._out[key]
			self.unset_cookie(key)
		if key in self._in:
			del self._in[key]
			p = {}
			if 'path' in self.policy: p['path'] = self.policy['path']
			if 'domain' in self.policy: p['domain'] = self.policy['domain']
			self.delete_cookie(key, **p)
	#begin WebOb functions
	def set_cookie(self, key, value='', max_age=None,
				   path='/', domain=None, secure=None, httponly=False,
				   version=None, comment=None):
		"""
		Set (add) a cookie for the response
		"""
		cookies = BaseCookie()
		cookies[key] = value
		for var_name, var_value in [
			('max-age', max_age),
			('path', path),
			('domain', domain),
			('secure', secure),
			('HttpOnly', httponly),
			('version', version),
			('comment', comment),
			]:
			if var_value is not None and var_value is not False:
				cookies[key][var_name] = str(var_value)
			if max_age is not None:
				cookies[key]['expires'] = max_age
		header_value = cookies[key].output(header='').lstrip()
		try:
			self.response.headers._headers.append(('Set-Cookie', header_value))
		except:
			self.response.headers.add('Set-Cookie', header_value)

	def delete_cookie(self, key, path='/', domain=None):
		"""
		Delete a cookie from the client.  Note that path and domain must match
		how the cookie was originally set.
		This sets the cookie to the empty string, and max_age=0 so
		that it should expire immediately.
		"""
		self.set_cookie(key, '', path=path, domain=domain,
						max_age=0)
	def unset_cookie(self, key):
		"""
		Unset a cookie with the given name (remove it from the
		response).	If there are multiple cookies (e.g., two cookies
		with the same name and different paths or domains), all such
		cookies will be deleted.
		"""
		existing = self.response.headers.get_all('Set-Cookie')
		if not existing:
			raise KeyError(
				"No cookies at all have been set")
		del self.response.headers['Set-Cookie']
		found = False
		for header in existing:
			cookies = BaseCookie()
			cookies.load(header)
			if key in cookies:
				found = True
				del cookies[key]
			header = cookies.output(header='').lstrip()
			if header:
				self.response.headers.add('Set-Cookie', header)
		if not found:
			raise KeyError(
				"No cookie has been set with the name %r" % key)
	#end WebOb functions

class MedianCalculator(object):
	def __init__(self):
		self.sortedlist = []

	def add_entry(self, value):
		if len(self.sortedlist) == 0:
			self.sortedlist.append(value)
		else:
			inserted = False
			for i in range(0, len(self.sortedlist)):
				if value > self.sortedlist[i]:
					self.sortedlist.insert(i, value)
					inserted = True
					break
			if not inserted:
				self.sortedlist.append(value)
	def median(self):
		if (float(len(self.sortedlist)) + 1.0) / 2.0 == int((len(self.sortedlist) + 1) / 2):
			return sortedpoints[(len(self.sortedlist) - 1) / 2]
		else:
			middle1 = self.sortedlist[(len(self.sortedlist) - 2) / 2]
			middle2 = self.sortedlist[len(self.sortedlist) / 2]
			return float(middle1 + middle2) / 2.0

#
def get_twitter_oauth_users():
	return [{'login_name': "kidneybingos", 'oauth_token': "3064231-qH8ezrCzkS1uDIqLeGJqz9nss0SiqG022LNJyalUw", 'oauth_token_secret': "SUsernc6GVuMAQDfnnvb70zkL8vJ2MPDVCegEMy9ri8"}]

def get_tweepy_response(method, *args, **kwargs):
	login_name = kwargs.get('login_name', "*")
	if 'login_name' in kwargs:
		del kwargs['login_name']
	from google.appengine.api import memcache
	users = get_twitter_oauth_users()

	if login_name == "*":
		if memcache.get("twitter-login-index"):
			index = memcache.get("twitter-login-index")
		else:
			index = 0
			memcache.set("twitter-login-index", index)
	else:
		for i in range(len(users)):
			if users[i]['login_name'] == login_name:
				index = i
				break

	import twitter_oauth
	import tweepy
	import types
	import logging
	auth = tweepy.OAuthHandler(twitter_oauth.CONSUMER_KEY, twitter_oauth.CONSUMER_SECRET)
	for try_num in range(len(users)):
		user = users[index]

		auth.set_access_token(user['oauth_token'], user['oauth_token_secret'])

		api = tweepy.API(auth, api_root='/1.1')
		api.get_oembed = types.MethodType(tweepy.binder.bind_api(
			path='/statuses/oembed.json',
			payload_type = 'json',
			allowed_param = ['id', 'url', 'maxwidth', 'hide_media', 'omit_script', 'align', 'related', 'lang']), api)

		tweepy_method = getattr(api, method)
		rate_limited = False
		MAX_TRIES = 15
		for i in range(MAX_TRIES):
			try:
				return tweepy_method(*args, **kwargs)
			except tweepy.TweepError:
				import sys
				e = sys.exc_value
				if str(e).startswith("[{"):
					error_d = eval(str(e))[0]
					if error_d['code'] == 88:
						rate_limited = True
					elif error_d['code'] == 187: 	# Status is a duplicate
						return {}
					else:
						raise
				elif str(e).find("Deadline exceeded while waiting for HTTP response") >= 0:
					if i < MAX_TRIES - 1:
						import logging
						logging.warning("Deadline exceeded while getting Tweepy response after %s tries; will re-try" % (i+1))
					else:
						raise
				else:
					if str(e) == "Not authorized":
						return None
					else:
						raise

		if rate_limited and login_name == "*":
			logging.info("Rate limited while making Twitter call using login %s with args %s, kwargs %s; trying next login" % (user['login_name'], args, kwargs))
			index += 1
			if index >= len(users): index = 0
			memcache.set("twitter-login-index", index)
		if try_num == len(users) - 1:
			exception_s = "Error encountered accessing method %s using login %s with args %s, kwargs %s after %s tries" % (method, user['login_name'], args, kwargs, try_num + 1)
			raise Exception(exception_s)
import sys
import random

class MarkovChain:
	@staticmethod
	def cleanse_key(txt):
		if txt in [",", "..."]:	# comma and elipses treated as a word.
			return txt
		s = ""
		for i in range(0, len(txt)):
			c = txt[i]
			if c.isalpha() or c.isdigit() or c in [" ", "-", ",", ";", ":"]:
				s += c
		return s.lower().replace("  ", " ").replace("  ", " ")

	def __init__(self, sentences):
		self.unigram_data = dict()
		self.bigram_data = dict()
		self.opening_words = []

		for sentence in sentences:
			if sentence.find(" AM) ") > 0 or sentence.find(" PM) ") > 0:
				continue
			words = sentence.replace(",", " , ").replace("...", " ... ").strip().split(' ')
			words = [w for w in words if w.strip() != ""]
			if not len(words): continue
			if not words[0].lower().startswith("http"):
				self.opening_words.append(words[0])

			for idx in range(0, len(words)):
				if words[idx].lower().startswith("http"): continue
				unigram_key = MarkovChain.cleanse_key(words[idx])
				next_word = words[idx+1] if idx+1 < len(words) else "<<stop>>"
				if next_word.strip() != "":
					self.unigram_data.setdefault(unigram_key, []).append(next_word)
				if idx + 1 < len(words):
					bigram_key = MarkovChain.cleanse_key(words[idx] + ' ' + words[idx+1])
					third_word = words[idx+2] if idx+2 < len(words) else "<<stop>>"
					if third_word.strip() != "":
						self.bigram_data.setdefault(bigram_key, []).append(third_word)
		#print "self.bigram_data=%s" % self.bigram_data

	def get_random_sentence(self):
		if not self.opening_words:
			return "..."
		random_opening_word = random.choice(self.opening_words)
		if random_opening_word[-1] in [".", "!", "?"]:
			return random_opening_word
		random_next_word = random.choice(self.unigram_data[MarkovChain.cleanse_key(random_opening_word)])
		if random_next_word == "<<stop>>":
			return random_opening_word
		current_bigram_key = MarkovChain.cleanse_key(random_opening_word + " " + random_next_word)
		current_unigram_key = MarkovChain.cleanse_key(random_opening_word)

		if random_next_word[-1] in [".", "!", "?"]:
			return random_opening_word + " " + random_next_word

		s = [random_opening_word + " " + random_next_word]

		def get_unigram_value(unigram_key, unigram_options):
			if unigram_key in ["a", "the", "an", "my", "your" "their", "its", "our", "he", "she", "it", "through", "at", "from", "and", "with", "of", "have", "has", "as", "if", "can", "on", "by", "that", "be", "do", "into", "has", "had", "have", "is", "are", "was", "about"]:
				return random.choice(unigram_options)
		while current_bigram_key in self.bigram_data or current_unigram_key in self.unigram_data:
			#if current_unigram_key in ["a", "the", "an", "my", "your" "their", "its", "our", "he", "she", "it", "to", "through", "at", "from", "and", "with", "of", "have", "has", "as", "if", "can", "on", "in", "by", "that", "be", "do", "into", "has", "had", "have"]:
			random_value = None
			unigram_options = self.unigram_data.get(current_unigram_key, [])
			if current_bigram_key in self.bigram_data:
				bigram_options = self.bigram_data[current_bigram_key]
				if len(bigram_options) <= 3:
					random_value = get_unigram_value(current_unigram_key, unigram_options)
				if not random_value:
					random_value = random.choice(bigram_options)
			else:
				random_value = get_unigram_value(current_unigram_key, unigram_options)
			if random_value is None or len(random_value) == 0 or random_value == "<<stop>>":
				break
			s.append(random_value)
			if random_value[-1] in [".", "!", "?"]:
				break
			current_bigram_key = MarkovChain.cleanse_key(current_bigram_key.split(' ')[1] + ' ' + random_value)
			current_unigram_key = MarkovChain.cleanse_key(random_value)
		return u''.join(map(lambda x: unicode(x) + u' ', s)).replace("\"", "").replace("(", "").replace(")", "").replace(" ,", ",")
