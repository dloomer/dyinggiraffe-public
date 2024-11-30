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

import dygchatdata

from google.appengine.ext.webapp import template
from google.appengine.ext import webapp
from google.appengine.ext import db,search
from google.appengine.api import memcache

# DeadlineExceededError can live in two different places
try:
    # When deployed
    from google.appengine.runtime import DeadlineExceededError
except ImportError:
    # In the development server
    from google.appengine.runtime.apiproxy_errors import DeadlineExceededError

logdebug = True

class RecordChatwordHandler(webapp.RequestHandler):
    def get(self):
        key_value = int(self.request.get("msg_key_id"))
        dygchatdata.record_chat_words(key_value)

class ChatMessageStatsHandler(webapp.RequestHandler):
    def get(self):
        key_value = int(self.request.get("msg_key_id"))
        dygchatdata.run_chat_stats(key_value)

class SlackSyncHandler(webapp.RequestHandler):
    def get(self):
        key_value = int(self.request.get("msg_key_id"))
        dygchatdata.run_slack_sync(key_value)

app = webapp2.WSGIApplication([
        ('/tasks/record_chatwords', RecordChatwordHandler), \
        ('/tasks/chatmessage_stats', ChatMessageStatsHandler), \
        ('/tasks/slack_sync', SlackSyncHandler)
        ], \
                                       debug=True)
