#!/usr/bin/python3.3
import bs4
import xml.etree.ElementTree as ET
import xml.parsers.expat
import os
import os.path
import sys
import guids
import socket
import difflib
import urllib.request
import re
import datetime
import http
import random
import wwts
RSS_INI_FILE = 'rss.ini'
RSS_DIR = 'RSS'
GUID_FILE = ".guids.sqlite"
UNPRINTABLE = r'/?'
MAX_FILE_NAME_LENGTH = 70
HTML_TEMPLATE = """<html>
<head>
<meta http-equiv=Content-Type content="text/html; charset=utf-8"/>
<style type="text/css">
	html body {{ background-color: #111 }}
	body {{ color: #bbb }}
	a {{ color:#b91 }}
</style>
<title>{0}</title>
</head>
<body>
<h1>{0}</h1>
<p><a href="{1}">{1}</a></p>
<p>{2}</p>
<div>{3}</div>
</body>
</html>"""
HOSTS = [
		"8.8.8.8", # Google DNS
		"8.8.4.4", # Google DNS
		"139.130.4.5", # Australian primary NS
		"208.67.222.222", # OpenDNS
		"208.67.220.220" # OpenDNS
		]

def knock(host):
	return os.system("ping -c 1 -s 1 -W 2 {0} >/dev/null 2>&1".format(host)) == 0

def check_network():
	host = random.choice(HOSTS)
	if knock(host):
		return True
	for host in HOSTS:
		if knock(host):
			return True
	return False

def isonow():
	return datetime.datetime.now().isoformat(' ')

def load_ini(file_name):
	result = {}
	with open(file_name) as f:
		current_group = ''
		for line in f.readlines():
			line = line.strip()
			if line.startswith('#') or not line:
				continue
			if line.startswith('['):
				group = line.lstrip('[').rstrip(']')
				result[group] = []
				continue
			if group:
				result[group].append(line)
	return result

def fetch_items(root):
	items = []
	if root.tag == 'rss':
		items = root.find('channel').findall('item')
	elif root.tag == '{http://www.w3.org/2005/Atom}feed':
		items = root.findall('{http://www.w3.org/2005/Atom}entry')
	return items

def get_guid(item):
	for tagname in ['guid', '{http://www.w3.org/2005/Atom}guid', 'id', '{http://www.w3.org/2005/Atom}id', 'link', '{http://www.w3.org/2005/Atom}link']:
		result = item.find(tagname)
		if result is not None:
			if result.tag.endswith('link') and 'href' in result.attrib:
				return result.attrib['href'].lower()
			if result.tag.endswith('guid') and 'isPermalink' in result.attrib:
				return result.text.lower()
			return result.text
	return ''

def get_title(item):
	for tagname in ['title', '{http://www.w3.org/2005/Atom}title', 'link', '{http://www.w3.org/2005/Atom}link']:
		result = item.find(tagname)
		if result is not None:
			text = result.attrib['href'] if (result.tag.endswith('link') and 'href' in result.attrib) else result.text
			if text is not None and text.count('"') % 2 != 0 and text.endswith('"'):
				text = text[:-1]
			return text or ''
	return ''

def get_date(item):
	for tagname in ['pubDate', '{http://www.w3.org/2005/Atom}pubDate', 'updated', '{http://www.w3.org/2005/Atom}updated']:
		result = item.find(tagname)
		if result is not None:
			return result.text
	return ''

def get_link(item):
	links = {}
	for tagname in ['link', '{http://www.w3.org/2005/Atom}link']:
		for result in item.findall(tagname):
			rel = result.attrib['rel'] if 'rel' in result.attrib else 'self'
			if 'href' in result.attrib:
				links[rel] = result.attrib['href']
			else:
				links[rel] = result.text
	if 'alternate' in links:
		return links['alternate']
	if 'self' in links:
		return links['self']
	if links:
		return links[links.keys()[0]]
	return ''

def get_content(item):
	result = None
	tags = ['fulltext', 'description', 'summary', 'content']
	fulltags = []
	for tag in tags:
		fulltags += [tag, '{http://www.w3.org/2005/Atom}' + tag]
	for tagname in fulltags:
		result = item.find(tagname)
		if result is not None:
			if result.text is None:
				return ET.tostring(result, encoding='utf-8').decode('utf-8')
			else:
				return result.text
	return ''

DOCTYPE = b'''
<!DOCTYPE naughtyxml [
	<!ENTITY nbsp "&#0160;">
	<!ENTITY copy "&#0169;">
]>
'''
# Yields: guid, title, date, link, content
def parse_feed(url, attempts_left=3):
	try:
		req = urllib.request.Request(url, headers={ 'User-Agent': 'Mozilla/5.0 (Linux)' })
		handle = urllib.request.urlopen(req)
		text = handle.read()
		text = text.replace(b'\x10', b' ')
		text = text.replace(b'', b' ')
		text = text.replace(b'\x0d', b' ')
		text = text.replace(b'& ', b'&amp; ')
		if attempts_left < 3:
			xml_decl_end = text.find(b'>') + 1
			text = text[:xml_decl_end] + DOCTYPE + text[xml_decl_end:]
		root = ET.fromstring(text)
		if root.tag not in ['rss', '{http://www.w3.org/2005/Atom}feed']:
			print('{0} at {1} instead of <rss> or <feed>'.format(root.tag, url))
			return
		for item in fetch_items(root):
			title = get_title(item)
			title = title.strip() or title
			yield get_guid(item), title, get_date(item), get_link(item), get_content(item)
	except UnicodeEncodeError as e:
		print(isonow(), url, 'unicode:', e)
	except socket.error as e:
		print(isonow(), url, 'socket:', e)
	except http.client.IncompleteRead as e:
		if attempts_left > 0:
			yield from parse_feed(url, attempts_left - 1)
		else:
			print(isonow(), url, 'incomplete read:', e)
	except http.client.BadStatusLine as e:
		print(isonow(), url, 'bad status line:', e)
	except urllib.error.URLError as e:
		print(isonow(), url, 'url:', e)
	except xml.etree.ElementTree.ParseError as e:
		if attempts_left > 0:
			yield from parse_feed(url, attempts_left - 1)
		else:
			print(isonow(), url, 'parse:', e)
	except xml.parsers.expat.ExpatError as e:
		print(isonow(), url, 'expat:', e)

def make_text(title, date, link, content):
	return HTML_TEMPLATE.format(title, link, date, content)

def extract_tags_from_text(text):
	try:
		soup = bs4.BeautifulSoup(text, "html5lib")
		tags = soup.find_all('a', class_='tag')
		return [tag.text for tag in tags]
	except TypeError as e:
		print(isonow(), 'type:', e)
	return []

def make_filename(path, title, text):
	if not os.path.exists(path):
		os.makedirs(path)
	filename = title if title else isonow()
	filename = ''.join(['[{0}]'.format(tag) for tag in extract_tags_from_text(text)]) + filename
	filename = filename.replace('/', '_')
	filename = filename.replace('\\', '_')
	filename = filename.replace('\n', '_')
	filename = filename[:MAX_FILE_NAME_LENGTH]
	while os.path.exists(os.path.join(path, filename + '.html')):
		filename += '_'
	return os.path.join(path, filename + '.html')

def pull_feed(group, url, db, bayes):
	for guid, title, date, link, content in parse_feed(url):
		exists = db.guid_exists(url, guid)
		if exists:
			continue

		savedir = RSS_DIR
		text_to_guess = content if content is not None else ""
		text_to_guess += title if title is not None else ""
		text_to_guess += link if link is not None else ""
		bayes_result = dict(bayes.guess(text_to_guess if text_to_guess else url))
		if 'good' not in bayes_result:
			bayes_result['good'] = 0
		if 'bad' not in bayes_result:
			bayes_result['bad'] = 0
		if bayes_result['bad'] > bayes_result['good']:
			savedir = os.path.join(savedir, 'unwanted')
		else:
			savedir = os.path.join(savedir, group)

		text = make_text(title, date, link, content)
		if 'twitter.com' in url or 'twitter-rss.com' in url:
			parts = url.split('/');
			title = url[-1] + '_' + title
		filename = make_filename(savedir, title, content)
		#filename = make_filename(os.path.join(RSS_DIR, group), title, content)
		"""
		if not guid: print(isonow(), url, "guid", guid)
		if not title: print(isonow(), url, "title", title)
		if not date: print(isonow(), url, "date", date)
		if not link: print(isonow(), url, "link", link)
		if not content: print(isonow(), url, "content", content)
		"""
		with open(filename, 'w') as f:
			f.write(text)
		db.add_guid(url, guid)

BayesData = wwts.BayesData
def main():
	global RSS_INI_FILE
	global RSS_DIR
	global GUID_FILE
	home = os.path.expanduser("~")
	RSS_INI_FILE = os.path.join(home, RSS_INI_FILE)
	RSS_DIR = os.path.join(home, RSS_DIR)
	GUID_FILE = os.path.join(home, GUID_FILE)

	if not check_network():
		print(isonow() + ": Network is down")
		return

	rsslinks = load_ini(RSS_INI_FILE )
	available_groups = rsslinks.keys()
	groups = sys.argv[1:]
	if not groups:
		groups = available_groups
	has_incorrect_groups = False
	for group in groups:
		if group not in available_groups:
			print("Group '{0}' is not available in links!".format(group))
			has_incorrect_groups = True
	if has_incorrect_groups:
		print("Available groups: {0}".format(', '.join(["'{0}'".format(group) for group in available_groups])))
		return

	db = guids.GuidDatabase(GUID_FILE)
	bayes = wwts.Bayes(tokenizer=wwts.Tokenizer(lower=True))
	try:
		bayes.load()
	except Exception as e:
		print(isonow(), 'bayes:', e)

	for group in groups:
		for url in rsslinks[group]:
			pull_feed(group, url, db, bayes)
	db.close()

if __name__ == "__main__":
	main()
