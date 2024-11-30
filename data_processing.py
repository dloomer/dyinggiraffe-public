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
from __future__ import with_statement

import os
import datetime, time
import copy
import logging

from google.appengine.api import taskqueue
from google.appengine.ext import webapp, db
from google.appengine.api import app_identity
from google.appengine.api import memcache
from google.appengine.ext import blobstore

import json

import webapp2

from mapreduce import base_handler
from mapreduce import mapreduce_pipeline
from mapreduce import operation as op
from mapreduce import shuffler
from mapreduce import context

import dygfantasystatsmodel

class StoreOutput(base_handler.PipelineBase):
    """A pipeline to store the result of the MapReduce job in the database.
    Args:
        mr_type: the type of mapreduce job run (e.g., WordCount, Index)
        encoded_key: the DB key corresponding to the metadata of this job
        output: the gcs file path where the output of the job is stored
    """

    def run(self, mr_type, encoded_key, output):
        import logging
        logging.debug("StoreOutput: output is %s" % str(output))

        blobstore_filename = "/gs" + output[0]
        blobstore_gs_key = blobstore.create_gs_key(blobstore_filename)
        url_path = "/blobstore/" + blobstore_gs_key

        logging.debug("StoreOutput: url_path is %s" % url_path)

'''
import data_processing
blobstore_filename = ""
blob_key = ""
pipeline = data_processing.AdhocPipeline(blobstore_filename, blob_key)
pipeline.start()
print pipeline.base_path + "/status?root=" + pipeline.pipeline_id
'''
class AdhocPipeline(base_handler.PipelineBase):
    def run(self, filekey, blobkey):
        bucket_name = app_identity.get_default_gcs_bucket_name()
        #"entity_kind": "model.ChatterVideo",
        #"filters": [("source_string_id", "=", "VINE")],
        output = yield mapreduce_pipeline.MapreducePipeline(
                "adhoc",
                "data_processing.adhoc_map",
                "data_processing.adhoc_reduce",
                "mapreduce.input_readers.DatastoreInputReader",
                "mapreduce.output_writers.GoogleCloudStorageConsistentOutputWriter",
                mapper_params={
                		"bucket_name": bucket_name,
                        "input_reader": {
                            "entity_kind": "dygfantasystatsmodel.FantasyPlayer",
                            "shard_count": 16,
                        },
                },
                reducer_params={
                        "output_writer": {
                            "bucket_name": bucket_name,
                            "mime_type": "text/plain",
                            "shard_count": 16,
                        },
                },
                shards=16)

        yield StoreOutput("AdhocMap", filekey, output)

def adhoc_map(player):
	if player.fantasyteam is not None: return
	if player.most_recent_season_year < 2015: return
	
	player_seasons = dygfantasystatsmodel.FantasyPlayerSeason.all().filter("player = ", player).fetch(15)
	nonzero_seasons = [_ for _ in player_seasons if _.stat_fpts > 0]
	player.most_recent_season = None
	player.most_recent_season_year = None
	latest_year = 0
	for player_season in nonzero_seasons:
		if player_season.season.year > latest_year:
			latest_year = player_season.season.year
	if latest_year:
		player.most_recent_season = db.Key.from_path("FantasySeason", "y_" + str(latest_year))
		
	player.set_calculated_fields()
	yield op.db.Put(player)

def adhoc_reduce(grouping, values):
    line = "\"%s\",%s" % (grouping, len(values))
    yield ("%s\n" % line).encode('utf-8')


