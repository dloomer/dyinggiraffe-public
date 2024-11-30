from google.appengine.api import urlfetch
from hashlib import sha1
from hmac import new as hmac
from random import getrandbits
from time import time
from urllib import urlencode
from urllib import quote as urlquote
from urllib import unquote as urlunquote

CONSUMER_KEY = "E9ltS0kfAKdbgdt6xJqnw"
CONSUMER_SECRET = "ITDaBX6RbuWWDVxETPG73cAsP5hTUxEF14YGzgyc8E"

def prepare_request(url, token, secret, additional_params=None,
										method=urlfetch.GET):
	"""Prepare Request.

	Prepares an authenticated request to any OAuth protected resource.

	Returns the payload of the request.
	"""

	def encode(text):
		return urlquote(str(text), "")

	params = {
		"oauth_consumer_key": CONSUMER_KEY,
		"oauth_signature_method": "HMAC-SHA1",
		"oauth_timestamp": str(int(time())),
		"oauth_nonce": str(getrandbits(64)),
		"oauth_version": "1.0"
	}

	if token:
		params["oauth_token"] = token

	if additional_params:
			params.update(additional_params)

	for k,v in params.items():
			if isinstance(v, unicode):
					params[k] = v.encode('utf8')

	# Join all of the params together.
	params_str = "&".join(["%s=%s" % (encode(k), encode(params[k]))
												 for k in sorted(params)])

	# Join the entire message together per the OAuth specification.
	message = "&".join(["GET" if method == urlfetch.GET else "POST",
											encode(url), encode(params_str)])

	# Create a HMAC-SHA1 signature of the message.
	key = "%s&%s" % (CONSUMER_SECRET, secret) # Note compulsory "&".
	signature = hmac(key, message, sha1)
	digest_base64 = signature.digest().encode("base64").strip()
	params["oauth_signature"] = digest_base64

	# Construct the request payload and return it
	return urlencode(params)

def make_async_request(url, token, secret, additional_params=None,
								 protected=False, method=urlfetch.GET):
	"""Make Request.

	Make an authenticated request to any OAuth protected resource.

	If protected is equal to True, the Authorization: OAuth header will be set.

	A urlfetch response object is returned.
	"""			
	payload = prepare_request(url, token, secret, additional_params,
																 method)
	if method == urlfetch.GET:
			url = "%s?%s" % (url, payload)
			payload = None
	headers = {"Authorization": "OAuth"} if protected else {}
	rpc = urlfetch.create_rpc(deadline=10.0)
	urlfetch.make_fetch_call(rpc, url, method=method, headers=headers, payload=payload)
	return rpc

def make_request(url, token, secret, additional_params=None,
																		protected=False, method=urlfetch.GET):
	return make_async_request(url, token, secret, additional_params, protected, method).get_result()


''''
#url = "http://api.twitter.com/1/statuses/update.xml"
#additional_params ={'status': urllib.quote("this is a test")}

#url = "http://search.twitter.com/search.atom?q=twitter"
#print make_request(url, "E9ltS0kfAKdbgdt6xJqnw", "ITDaBX6RbuWWDVxETPG73cAsP5hTUxEF14YGzgyc8E", "rsgJSXHUuG0v8tYhoACJ3jXlKIlv0M5XUS3HHK09s", "chKe0vU5OUuYYYbqVLFPsuFeCDNBqy4h2D6TkYHF0Js",additional_params=additional_params,method=urlfetch.POST).content


#url = "http://twitter.com/account/verify_credentials.json"
url = "http://api.twitter.com/1/statuses/update.xml"
additional_params ={'status': "this is a test"}
print make_request(url, "E9ltS0kfAKdbgdt6xJqnw", "ITDaBX6RbuWWDVxETPG73cAsP5hTUxEF14YGzgyc8E", "105559656-HRt08YpJaQC8r0qAaNfY1CYAavDcD5nCMkJu387g", "dL770fJ63z37sfEpITidESANKLyfJGVT6QjE12XZM0I",additional_params=additional_params,method=urlfetch.POST).content
'''