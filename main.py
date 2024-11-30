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
import os, sys
import datetime, time, calendar
import logging

import dygutil
import dygmodel
import dygsettingsdata
import dygchatdata

from google.appengine.ext.webapp import template
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db,search
from google.appengine.api import memcache

from google.appengine.api import urlfetch
from google.appengine.api import users

logdebug = True
CHAT_PAGE_SIZE = 100

import jinja2
jinja_environment = jinja2.Environment(
		loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

def is_mancow(handler, teamkeyname, set_cookie=False):
	mancow = teamkeyname in ['t_16', 't_19', 't_6']
	if mancow and set_cookie: dygutil.set_mancow(handler)
	mancow = mancow or dygutil.get_mancow(handler)
	mancow = mancow or handler.request.remote_addr in ['108.82.98.113'] or handler.request.remote_addr.startswith('66.87.2.') or handler.request.remote_addr.startswith('66.87.7.') or handler.request.remote_addr.startswith('66.87.0.') or handler.request.remote_addr.startswith('66.87.4.') or handler.request.remote_addr.startswith('141.0.8.') or handler.request.remote_addr.startswith('141.0.9.') or handler.request.remote_addr.startswith('141.0.10.') or handler.request.remote_addr.startswith('141.0.11.')
	return mancow

class MainHandler(webapp.RequestHandler):
	def get(self):
		#dygutil.make_themes()

		#photo = db.Model.get(db.Key("ahJkeWluZ2dpcmFmZmVsZWFndWVyYwsSBVBob3RvIlhodHRwOi8vYTI5My5hYy1pbWFnZXMubXlzcGFjZWNkbi5jb20vaW1hZ2VzMDEvMTA0L2xfYmMxMTNiZjYxNzkwZWZkYjIzYTJmMjMyY2ZkYzM3MzQuanBnDA"))
		#photo.delete()

		browserinfo = dygutil.get_browser_info(self.request)
		firefox_win = (browserinfo['browser'] == "firefox" and browserinfo["os"] == "windows")
		ie_win = (browserinfo['browser'] == "ie" and browserinfo["os"] == "windows")

		teamkeyname = dygutil.getteamid(self,enforce=True)
		if teamkeyname is None or teamkeyname == "": return

		mancow = is_mancow(self, teamkeyname)

		newlastchatmessagesortindex = ""
		firstsortindex = ""

		has_more = False
		chatmessages = dygchatdata.fetch_chat_messages(CHAT_PAGE_SIZE + 1)
		if len(chatmessages) > CHAT_PAGE_SIZE:
			has_more = True
			chatmessages = chatmessages[:CHAT_PAGE_SIZE]

		team_owner_name = dygchatdata.fetch_team_ownername(teamkeyname)

		if not memcache.get("settings"):
			dygutil.settings_to_memcache(dygsettingsdata.get_latest_settings())

		latestsettings = memcache.get("settings")

		hidephotos = dygutil.gethidephotos(self)
		hideinlinemedia = dygutil.gethideinlinemedia(self)
		hidecountdown = dygutil.gethidecountdown(self)

		d = {}
		d['hidephotos'] = hidephotos
		d['hideinlinemedia'] = hideinlinemedia
		d['hidecountdown'] = hidecountdown
		if chatmessages:
			d['chat_messages'] = chatmessages
		d['settings'] = latestsettings
		d['has_more'] = has_more
		if 'theme' not in latestsettings:
			latestsettings['theme'] = "basic.css"
		import simplejson
		template_values = {
			'team_owner_name': team_owner_name,
			'team_key_name': teamkeyname,
			'hidephotos': hidephotos,
			'hideinlinemedia': hideinlinemedia,
			'hidecountdown': hidecountdown,
			'firefox_win': firefox_win,
			'theme': latestsettings['theme'],
			'ie_win': ie_win,
			'json': simplejson.dumps(d),
		}
		template = jinja_environment.get_template('templates/index.html')
		self.response.out.write(template.render(template_values))

class AjaxChatMessageHandler(webapp.RequestHandler):
	def get(self):
		self.ajax_refresh()
	def post(self):
		teamkeyname = dygutil.getteamid(self)
		mancow = is_mancow(self, teamkeyname, set_cookie=True)

		is_retry = self.request.get("retry", default_value="false").lower() == "true"
		d = dygchatdata.create_chat_message(
			dygchatdata.fetch_team(teamkeyname),
			self.request.get("local_id"),
			self.request.get("trash"),
			self.request.remote_addr,
			is_retry,
			mancow=mancow,
			chat_page_size=CHAT_PAGE_SIZE)
		import time
		#time.sleep(1)
		self.ajax_refresh(d)
	def ajax_refresh(self, new_msg=None):
		expires_date = datetime.datetime.utcnow() + datetime.timedelta(-1)
		expires_str = expires_date.strftime("%d %b %Y %H:%M:%S GMT")
		self.response.headers["Expires"] = expires_str
		self.response.headers["pragma"] = "no-cache"
		self.response.headers.add_header("cache-control","no-store")
		self.response.headers.add_header("cache-control","no-cache")

		if self.request.get("sortindex",default_value="") == "" and not new_msg: return

		debugstr = ''

		lastsortindex = self.request.get("sortindex",default_value="")
		newlastsortindex = lastsortindex

		hidephotos = dygutil.gethidephotos(self)
		hideinlinemedia = dygutil.gethideinlinemedia(self)
		hidecountdown = dygutil.gethidecountdown(self)

		if not memcache.get("settings"):
			latestsettings = dygsettingsdata.get_latest_settings()
			if latestsettings is not None:
				dygutil.settings_to_memcache(latestsettings)

		d = {}
		if new_msg:
			import simplejson
			self.response.out.write(simplejson.dumps({'new_msg': new_msg}))
			return
		elif lastsortindex != memcache.get("newestsortindex"):
			chatmessages = dygchatdata.fetch_chat_messages(CHAT_PAGE_SIZE + 1)
			if chatmessages:
				filtered = [m for m in chatmessages if m['sortindex'] > lastsortindex]
				if filtered: d['chat_messages'] = filtered

		settingscache = memcache.get("settings")
		d['settings'] = settingscache
		d['hidephotos'] = hidephotos
		d['hideinlinemedia'] = hideinlinemedia
		d['hidecountdown'] = hidecountdown
		if 'theme' not in d['settings']:
			d['settings']['theme'] = "basic.css"
		d['debuginfo'] = debugstr
		d['currenttime'] = datetime.datetime.now().replace(tzinfo=dygutil.UTC_tzinfo()).strftime("%a %b %d %H:%M:%S UTC %Y")

		import time
		#time.sleep(1)
		import simplejson
		self.response.out.write(simplejson.dumps(d))
		#time.sleep(1)

class AjaxChatPagingHandler(webapp.RequestHandler):
	def get(self):
		prevsortindex = self.request.get("firstsortindex")
		firstsortindex = ""
		has_more = False
		chatmessages = dygmodel.ChatMessage.all().filter("sortindex < ", prevsortindex).order("-sortindex").fetch(CHAT_PAGE_SIZE + 1)
		if len(chatmessages) > CHAT_PAGE_SIZE:
			has_more = True
			chatmessages = chatmessages[:CHAT_PAGE_SIZE]

		d = {
			'chat_messages': [m.to_dict() for m in chatmessages],
			'has_more': has_more,
		}
		import simplejson
		self.response.out.write(simplejson.dumps(d))

class MemcachePurgeHandler(webapp.RequestHandler):
	def get(self):
		memcache.flush_all()
		self.response.out.write("memcache purged.<br/><br/><a href='/'>Chat home</a>")

class ImageHandler(webapp.RequestHandler):
	def get(self):
		if self.request.get("photokey"):
			photo = dygmodel.Photo.get(self.request.get("photokey"))
			if self.request.get("thumbnail").lower() == "true":
				photodata = photo.thumbnaildata
			else:
				photodata = photo.photodata
			url = photo.url
		elif self.request.get("videokey"):
			video = dygmodel.YouTubeVideo.get(self.request.get("videokey"))
			photodata = video.thumbnaildata
			url = video.youtubeid
		photoinfo = dygutil.getImageInfo(photodata)
		self.response.headers['Content-Type'] = photoinfo[0]
		self.response.headers['Content-Disposition'] = "inline;filename=" + str(dygutil.get_url_filename(url))
		expires_date = datetime.datetime.utcnow() + datetime.timedelta(30)
		expires_str = expires_date.strftime("%d %b %Y %H:%M:%S GMT")
		self.response.headers['Expires'] = expires_str
		self.response.headers['cache-control'] = "max-age=" + str(60*60*24*30)
		if photodata:
			self.response.out.write(photodata)
		else:
			self.response.out.write(urlfetch.fetch("http://dyinggiraffeleague.appspot.com/images/notfound.gif").content)

from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.ext import blobstore
class BlobHandler(blobstore_handlers.BlobstoreDownloadHandler):
	def get(self, key):
		import urllib
		key = str(urllib.unquote(key))
		blob_info = blobstore.BlobInfo.get(key)
		url = self.request.get("url")
		expires_date = datetime.datetime.utcnow() + datetime.timedelta(30)
		expires_str = expires_date.strftime("%d %b %Y %H:%M:%S GMT")
		self.response.headers['Expires'] = expires_str
		self.response.headers['cache-control'] = "max-age=" + str(60*60*24*30)
		if blob_info:
			photoinfo = dygutil.getImageInfo(blob_info.open().read())
			self.response.headers['Content-Type'] = photoinfo[0]
			self.response.headers['Content-Disposition'] = "inline;filename=" + str(dygutil.get_url_filename(url))
			self.send_blob(blob_info)
		else:
			self.response.headers['Content-Type'] = "image/gif"
			self.response.out.write(urlfetch.fetch("http://dyinggiraffeleague.appspot.com/images/notfound.gif").content)

class PhotoPopupHandler(webapp.RequestHandler):
	def get(self):
		import urllib
		photo = dygmodel.Photo.get(self.request.get("photokey"))
		maxcharwidth = float(photo.displaywidth()) / 5.7
		if photo.photo_blob_key:
			url = "/blobstore/%s?url=%s" % (photo.photo_blob_key, urllib.quote(photo.url))
		elif photo.photo_gcs_blob_key:
			url = photo.serving_url()
		else:
			url = "/localimg?photokey=" + str(photo.key())
		template_values = {
			'url': url,
			'width': photo.displaywidth(),
			'height': photo.displayheight(),
			'originalurl': dygutil.wrap_url(photo.url,maxcharwidth),
			'originalurl_linkable': photo.url,
		}
		template = jinja_environment.get_template('templates/photo.html')
		self.response.out.write(template.render(template_values))

class VideoPopupHandler(webapp.RequestHandler):
	def get(self):
		video = dygmodel.YouTubeVideo.get(self.request.get("videokey"))
		template_values = {
			'youtubeid': video.youtubeid,
		}
		template = jinja_environment.get_template('templates/video.html')
		self.response.out.write(template.render(template_values))

class RateElementHander(webapp.RequestHandler):
	def post(self):
		rating_value = int(self.request.get("rating"))
		key_val = self.request.get("id")[7:]

		team = dygchatdata.fetch_team(dygutil.getteamid(self))
		element = db.get(key_val)

		rating = dygmodel.SettingsElementRating.get_or_insert_by_values(element, team)
		rating.rating = rating_value
		rating.put()

		totalrating = 0
		totalraters = 0
		for rating in element.ratings_set:
			totalrating += rating.rating
			totalraters += 1

		element.totalrating = totalrating
		element.totalraters = totalraters
		element.put()

		self.response.out.write(str(float(totalrating) / float(totalraters)))

class LoginHandler(webapp.RequestHandler):
	def get(self):
		teams = db.GqlQuery("SELECT * FROM Team WHERE is_interactive=TRUE").fetch(100)
		teams = sorted(teams, key=lambda (t): t.teamname)
		latestsettings = dygsettingsdata.get_latest_settings()
		settingsdict = latestsettings.to_dict() if latestsettings else {}
		if 'theme' not in settingsdict: settingsdict['theme'] = "basic.css"
		template_values = {
			'teams': teams,
			'theme': settingsdict["theme"],
		}
		template = jinja_environment.get_template('templates/login.html')
		self.response.out.write(template.render(template_values))
	def post(self):
		if self.request.get("password") != "nocab":
			logging.info("LoginHandler: supplied password is " + str(self.request.get("password")))
		if self.request.get("setupTeamId") != "" and self.request.get("password") == "nocab":
			dygutil.setteamid(self, self.request.get("setupTeamId"))
		self.redirect("/")

class LogoutHandler(webapp.RequestHandler):
	def get(self):
		dygutil.logout(self)
		if users.get_current_user():
			self.redirect(users.create_logout_url("/login"))
		else:
			self.redirect("/login")

from google.appengine.ext.webapp import blobstore_handlers
# BLOBSTORETODO
class ImageUploadPostHandler(blobstore_handlers.BlobstoreUploadHandler):
	def post(self):
		#http://www.dyinggiraffe.com/blobstore/AMIfv945l_bt9V2tRnrQy7jNom4xxCOVJZidnOOwkfIEfj6tkAySj7k-4PeK1wB1PhHw4j0uD4t2zfccpsHEIYpFFx72LCVzpSjq0a4edby5ojxF9QkJKZR4pDhb7PmP_QQNo7UM0w6y773BXiohEwbB7OIHWxxXbCHl5AqhRsg14u7g-DKtLk0?url=http%3A//farm3.static.flickr.com/2038/2335244431_0ec1914fb4.jpg%3Fv%3D0

		upload_files = self.get_uploads('files[]')
		blob_info = upload_files[0]
		blob_data = blob_info.open().read()
		photo_info = dygutil.getImageInfo(blob_data)

		unique_s = blob_info.filename + str(int(time.mktime(datetime.datetime.now().timetuple())))

		width = photo_info[1]
		height = photo_info[2]
		photo_gcs_blob_key = None
		photo_blob_key = None
		if width * height > 500000:
			# Resize the image
			resized = dygutil.getImageThumbnail(blob_data,1000,1000, constrain=True)
			resized_info = dygutil.getImageInfo(resized)
			file_name = "/images/%s/o.jpg" % dygmodel.Photo.gcs_image_name(unique_s)
			resized_gcs_blob_key = dygutil.save_gcs_object(resized, file_name, content_type=resized_info[0], options={'x-goog-acl': 'public-read'})

			gcs_bucket_url = "http://storage.googleapis.com/dyinggiraffe-hrd.appspot.com"
			image_url = "%s%s" % (gcs_bucket_url, file_name)

			# Remove the original image
			blobstore.delete(blob_info.key())
			photo_gcs_blob_key = resized_gcs_blob_key
		else:
			photo_blob_key = str(blob_info.key())
			image_url = self.request.headers['Origin'] + '/uploads/' + photo_blob_key

		photo = dygmodel.Photo.get_or_insert(image_url,url=image_url,date=datetime.datetime.now())
		photo.original_filename = blob_info.filename
		content_type = photo_info[0]
		photo.width = photo_info[1]
		photo.height = photo_info[2]
		photo.photo_blob_key = photo_blob_key
		photo.photo_gcs_blob_key = photo_gcs_blob_key
		if content_type == "image/gif" or blob_info.filename.lower().endswith(".gif"):
			photo.thumbnail_blob_key = photo.photo_blob_key
			photo.thumbnail_gcs_blob_key = photo.photo_gcs_blob_key
			thumbnail_width = photo.width
			thumbnail_height = photo.height
		else:
			# TODO: thumbnail different for inline vs. top photos?
			thumb = dygutil.getImageThumbnail(blob_data,460,276, constrain=True)
			thumb_info = dygutil.getImageInfo(thumb)
			file_name = "/images/%s/t.jpg" % dygmodel.Photo.gcs_image_name(image_url)
			try:
				photo.thumbnail_gcs_blob_key = dygutil.save_gcs_object(thumb, file_name, content_type=thumb_info[0], options={'x-goog-acl': 'public-read'})
				photo.thumbnail_width = thumb_info[1]
				photo.thumbnail_height = thumb_info[2]
			except:
				photo.thumbnail_blob_key = photo.photo_blob_key
				photo.thumbnail_gcs_blob_key = photo.photo_gcs_blob_key
				photo.thumbnail_width = photo.width
				photo.thumbnail_height = photo.height
		photo.put()

		#serving_url = self.request.headers['Origin'] + '/' + str(blob_info.key()) + '?filename=' + blob_info.filename	# Host does not include protocol
		import simplejson
		self.response.out.write(simplejson.dumps({'success': True, 'filename': blob_info.filename, 'blob_key': str(blob_info.key()), 'serving_url': image_url}))

class ImageUploadHandler(webapp.RequestHandler):
	def get(self):
		from google.appengine.ext import blobstore
		target_id = self.request.get("target_id")
		replace = self.request.get("replace", default_value="false").lower() == "true"
		upload_url = blobstore.create_upload_url('/image_upload_post')
		template = jinja_environment.get_template('templates/image_upload.html')
		self.response.out.write(template.render({'upload_url': upload_url, 'target_id': target_id, 'replace': str(replace).lower()}))

class FynHandler(webapp.RequestHandler):
	def get(self):
		self.response.out.write("<a href=\"javascript:var%20text=document.getSelection().toString();if(text!=''){var%20url='http://fuckyeah.herokuapp.com/'+encodeURI(text);window.open(url);}\">FYN</a>")

class AdHocHandler(webapp.RequestHandler):
	def get(self):
		t = dygmodel.Team.get_or_insert("t_23", teamid=23, teamname="Come Back Cyrus!", ownername="Cyrus Khazai", postindex=0)

class GenerateQuoteHandler(webapp.RequestHandler):
	def get(self):
		team_key_name = self.request.get("team")
		filter_term = self.request.get("keyword")
		use_memcache = self.request.get("use_memcache", default_value="true").lower() == "true"

		memcache_key = "markov-" + team_key_name
		if filter_term:
			memcache_key += "-" + filter_term
		markov_chain = memcache.get(memcache_key) if use_memcache else None

		if not markov_chain:
			sentence_data = dygmodel.UserSentenceData.get_or_insert(team_key_name, team_key_name=team_key_name)

			markov_chain = dygutil.MarkovChain([])
			markov_chain.unigram_data = sentence_data.unigram_data
			markov_chain.bigram_data = sentence_data.bigram_data
			markov_chain.opening_words = sentence_data.opening_words

			if filter_term:
				q = dygmodel.ChatMessage.all()
				q.search(filter_term)
				q.filter("team = ", db.Key.from_path("Team", team_key_name))
				chatmessages = q.fetch(200)
				terms_chain = dygutil.MarkovChain([msg.text for msg in chatmessages])
				markov_chain.opening_words.extend(terms_chain.opening_words)
				for unigram_key, data in terms_chain.unigram_data.items():
					markov_chain.unigram_data.setdefault(unigram_key, []).extend(data)
				for bigram_key, data in terms_chain.bigram_data.items():
					markov_chain.bigram_data.setdefault(bigram_key, []).extend(data)
			memcache.set(memcache_key, markov_chain)

		def term_in_sentence(term, sentence):
			if not term: return False
			term_lower = term.lower()
			return len(set([term_lower, "#" + term_lower]).intersection(set(sentence.lower().replace(',', ' ').replace('.', ' ').replace('-', ' ').replace('"', ' ').replace(';', ' ').replace(':', ' ').replace('!', ' ').replace('?', ' ').replace('/', ' ').split(' ')))) > 0

		generated_sentence = None
		for i in range(200):
			sentence = markov_chain.get_random_sentence()
			if (not filter_term) or term_in_sentence(filter_term, sentence):
				if i > 3 or len(sentence.lower().split(' ')) > 4:
					generated_sentence = sentence
					break
		if generated_sentence is None:
			d = {
				'ok': False,
				'error_message': "Nothing could be found. Try again!",
			}
		else:
			if team_key_name == "t_12":
				fake_user_name = "Fake DOGGER"
			else:
				real_team_ownername = dygchatdata.fetch_team_ownername(team_key_name)
				if team_key_name == "t_23":
					fake_word = "Faux"
				else:
					fake_word = "Fake"
				fake_user_name = fake_word + " " + real_team_ownername
				if real_team_ownername == real_team_ownername.upper():
					fake_user_name = fake_user_name.upper()
				elif real_team_ownername == real_team_ownername.lower():
					fake_user_name = fake_user_name.lower()
			d = {
				'ok': True,
				'sentence': generated_sentence.strip(),
				'user_name': fake_user_name,
			}

		import simplejson
		self.response.headers['Content-Type'] = 'application/json'
		self.response.out.write(simplejson.dumps(d))

class RunTaskHandler(webapp.RequestHandler):
	def post(self):
		from google.appengine.api import taskqueue
		task_url = self.request.get("task_url")
		task_name = self.request.get("task_name")
		queue_name = self.request.get("queue_name")
		target = self.request.get("target")
		countdown = 1 if target else 0
		if task_name:
			t = taskqueue.Task(url=task_url, method='GET', target=target, name=task_name, countdown=countdown)
		else:
			t = taskqueue.Task(url=task_url, method='GET', target=target, countdown=countdown)
		t.add(queue_name = queue_name)

	def get(self):
		html = "<html><body><form method='post'>URL <input type='text' name='task_url' size='100'><br/>Name <input type='text' name='task_name' size='100'><br/>Target <input type='text' name='target' size='100'><br/>Queue <select name='queue_name'><option value='default'>default</option><option value='cbs-data'>cbs-data</option><option value='chat-stats'>chat-stats</option><option value='post-words'>post-words</option></select><br/><input type='submit'></form></body></html>"
		self.response.out.write(html)

class CsvHandler(webapp.RequestHandler):
	def get(self):
		import csv, StringIO
		csv_file = StringIO.StringIO()
		csv_writer = csv.writer(csv_file, quoting=csv.QUOTE_MINIMAL)
		# msgs.extend([
		# 	dygmodel.ChatMessage.get_by_id(129617850),
		# 	dygmodel.ChatMessage.get_by_id(134697830)
		# ])


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
			  "email": None
		   },
	       "t_31":{
	          "owner_name":"DA CHI TOWN PLAYA",
	          "email":None
	       }
		}

		cursor = None
		msgs = []
		for i in range(1):
			q = dygmodel.ChatMessage.all().order("-date")
			if cursor:
				q.with_cursor(cursor)
			msgs.extend(q.fetch(200))
			cursor = q.cursor()

		msgs = sorted(msgs, key=lambda (m): m.date)
		for msg in msgs:
			team_key_name = \
				dygmodel.ChatMessage.team.get_value_for_datastore(msg).name()
			# team = msg.team
			# if team.google_id and team.google_id.lower() != "none@gmail.com":
			# 	email = team.google_id
			# else:
			# 	email = team.email
			# email_mapping = {
			# 	't_8': "benhoug@gmail.com",
			# 	't_4': "andypt7@gmail.com",
			# 	't_21': "joe.r.schmidt@gmail.com",
			# 	't_24': "williamschet67@yahoo.com",
			# 	't_27': "kolbeck04@gmail.com"
			# }
			# email = email_mapping.get(team_key_name, email)
			# d = msg.date \
			# 	.replace(tzinfo=dygutil.Central_tzinfo()) \
			# 	.astimezone(dygutil.Pacific_tzinfo()) \
			# 	.replace(tzinfo=None)
			msg_date = msg.date.replace(tzinfo=None)

			csv_writer.writerow(
			  [
				time.mktime(msg_date.timetuple()),
				"general",
				user_mapping[team_key_name]['owner_name'],
					msg.text.encode('utf-8')
			  ]
			)

		self.response.headers['Content-Type'] = 'text/csv'
		self.response.out.write(csv_file.getvalue())
		csv_file.close()

class SlackHandler(webapp.RequestHandler):
	def get(self):
		pass
	def post(self):
		import re
		# look for user_id != 'USLACKBOT' and text doesn't start with /
		logging.debug("token=%s" % self.request.get("token"))
		logging.debug("team_domain=%s" % self.request.get("team_domain"))
		logging.debug("channel_name=%s" % self.request.get("channel_name"))
		logging.debug("timestamp=%s" % self.request.get("timestamp"))
		logging.debug("user_id=%s" % self.request.get("user_id"))
		logging.debug("user_name=%s" % self.request.get("user_name"))
		logging.debug("text=%s" % self.request.get("text"))

		slack_mapping = {
			'U3B29A6EN': {'owner_name': 'KEITH STRADLEY', 'email': 'kstrad@hotmail.com', 'team_key_name': 't_13'},
			'U3BUCB9RC': {'owner_name': 'Sean Disch', 'email': 'sean_disch@hotmail.com', 'team_key_name': 't_5'},
			'U3BNGKG95': {'owner_name': 'Shellers', 'email': 'williamschet67@yahoo.com', 'team_key_name': 't_24'},
			'U39QY8F25': {'owner_name': 'Ben Houg', 'email': 'benhoug@gmail.com', 'team_key_name': 't_8'},
			'U3BN52PML': {'owner_name': 'Noah Montague', 'email': 'noahmontague@yahoo.com', 'team_key_name': 't_14'},
			'U3BAR5US0': {'owner_name': 'Nate Tormoehlen', 'email': 'joerote@hotmail.com', 'team_key_name': 't_10'},
			'U3BNGKLR5': {'owner_name': 'Mr. Kolbeck', 'email': 'kolbeck04@gmail.com', 'team_key_name': 't_27'},
			'U3ABT8H1P': {'owner_name': 'Joe Schmidt', 'email': 'joe.r.schmidt@gmail.com', 'team_key_name': 't_21'},
			'U3AH421T2': {'owner_name': 'Phil Sauer', 'email': 'phil.sauer@ey.com', 'team_key_name': 't_9'},
			'U39PVQM09': {'owner_name': 'Dave Loomer', 'email': 'dloomer@gmail.com', 'team_key_name': 't_1'},
			'U3AH4294G': {'owner_name': 'Erik Peterson', 'email': 'ep2kp2@msn.com', 'team_key_name': 't_3'},
			'U3B0A525R': {'owner_name': 'matt schuster', 'email': 'mjschuster@fuse.net', 'team_key_name': 't_15'},
			'U3B8GE3D0': {'owner_name': 'Andy Peterson', 'email': 'andypt7@gmail.com', 'team_key_name': 't_4'},
			'U3AJ0ECMP': {'owner_name': 'Trent Tormoehlen', 'email': 'ttor68@yahoo.com', 'team_key_name': 't_2'},
			'U3ABT8G2D': {'owner_name': 'Cyrus Khazai', 'email': 'ckhazai@gmail.com', 'team_key_name': 't_23'},
			'U3BAR5VTN': {'owner_name': 'Michael Ermitage', 'email': 'mermitage@hotmail.com', 'team_key_name': 't_7'},
			'U3B6HDTMH': {'owner_name': 'Bart Beatty', 'email': 'btbeatty@hotmail.com', 'team_key_name': 't_11'},
			'U3AJ0EH5F': {'owner_name': 'Dogger', 'email': 'michael_judy513@hotmail.com', 'team_key_name': 't_12'},
			'U3B0A55T5': {'owner_name': 'Cory Snyder', 'email': 'patmrclutchtabler@gmail.com', 'team_key_name': 't_22'},
			'U3ABT8JJD': {'owner_name': 'Jim Ermitage', 'email': 'ermitagej@gmail.com', 'team_key_name': 't_20'},
			# 'U3BNGKLR5': {'owner_name': 'Craig McMurtrey', 'email': 'craig@dyinggiraffe.com', 'team_key_name': 't_28'},
		}

		text = self.request.get("text")
		user_id = self.request.get("user_id")
		if text and user_id and user_id in slack_mapping and not text.startswith("/"):
			for match in re.finditer('(<(?:http|https)://(?:[^ \n\r<\)]+)>)(\s)', text + ' '):
				matched = match.group(0).strip()
				text = text.replace(matched, matched[1:-1])

			teamkeyname = slack_mapping[user_id]['team_key_name']
			mancow = False
			is_retry = False
			d = dygchatdata.create_chat_message(
				dygchatdata.fetch_team(teamkeyname),
				"1",
				text,
				self.request.remote_addr,
				is_retry,
				mancow=mancow,
				chat_page_size=CHAT_PAGE_SIZE,
				from_slack=True)

app = webapp2.WSGIApplication([
		('/', MainHandler), \
		('/index.html', MainHandler), \
		('/default.asp', MainHandler), \
		('/posttochat', AjaxChatMessageHandler), \
		('/newposts', AjaxChatMessageHandler), \
		('/nextchatpage', AjaxChatPagingHandler), \
		('/photopopup', PhotoPopupHandler), \
		('/videopopup', VideoPopupHandler), \
		('/localimg', ImageHandler), \
		('/blobstore/(.*)', BlobHandler), \
		('/uploads/(.*)', BlobHandler), \
		('/rate_element', RateElementHander), \
		('/login', LoginHandler), \
		('/logout', LogoutHandler), \
		('/fyn', FynHandler), \
		('/adhoc', AdHocHandler), \
		('/image_upload', ImageUploadHandler), \
		('/image_upload_post', ImageUploadPostHandler), \
		('/purge_memcache', MemcachePurgeHandler),
		('/generate_quote_service', GenerateQuoteHandler),
		('/run_task', RunTaskHandler), \
		('/download', CsvHandler),
		('/slack', SlackHandler),
		],
									   debug=False)
