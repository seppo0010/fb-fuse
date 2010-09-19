#!/usr/bin/env python
# -*- coding: utf-8 -*-
import errno
import fuse
import stat
import time
import httplib
import json
import os
import sys
import ConfigParser
import tempfile
import urllib
import urllib2
import pycurl
from urlparse import urlparse

fuse.fuse_python_api = (0, 2)

class MyFS(fuse.Fuse):
	albums = {};
	photos = {}
	access_token = None;
	max_upload_speed = 0;
	tempfiles = {};
	tempnodes = [];

	def __init__(self, *args, **kw):
		fuse.Fuse.__init__(self, *args, **kw)
		home = os.getenv('HOME');
		if home == None:
			sys.exit('No access token set');

		config = ConfigParser.ConfigParser()
		config.read([home + '/.fbfuserc'])

		try:
			self.max_upload_speed = int(config.get('connection', 'max_upload_speed'));
		except ConfigParser.Error:
			pass

		try:
			self.access_token = config.get('facebook', 'access_token');
			if self.access_token == None:
				sys.exit('No access token set');
		except ConfigParser.Error:
			sys.exit('No access token set');

	def get_photo_from_path(self, path):
		try:
			album_name = path[8:path.find('/', 8)];
			album_id = self.albums[album_name]['id'];
			pos = (8 + 1 + len(album_name))
			photo_id = path[pos:]
			photo = self.photos[album_id][photo_id];
			return photo
		except KeyError:
			return None

	def getattr(self, path):
		st = fuse.Stat()
		if self.tempnodes.count(path) > 0:
			st.st_mode = stat.S_IFREG | 0755
			st.st_nlink = 1
		elif path == '/' or path == '/photos' or (path.startswith('/photos') and path.count('/') == 2):
			if (path.startswith('/photos') and path.count('/') == 2):
				album = path[8:]
				self.fetch_albums();
				if self.albums.has_key(album):
					st.st_mode = stat.S_IFDIR | 0755
					st.st_nlink = 2
				else:
					return -errno.ENOENT
			else:
				st.st_mode = stat.S_IFDIR | 0755
				st.st_nlink = 2
		else:
			st.st_mode = stat.S_IFREG | 0755
			st.st_nlink = 1
			photo = self.get_photo_from_path(path)
			if photo is None:
				return -errno.ENOENT

			url = urlparse(photo['source']);
			conn = httplib.HTTPConnection(url.netloc)
			conn.request("HEAD", url.path)
			response = conn.getresponse();
			st.st_size = int(response.getheader('content-length'))

		st.st_atime = int(time.time())
		st.st_mtime = st.st_atime
		st.st_ctime = st.st_atime

		return st

	def mknod(self, path, mode, dev):
		self.tempnodes.append(path);
		return 0

	def open(self, path, flags):
		return 0

	def read(self, path, size, offset):
		photo = self.get_photo_from_path(path)
		if photo is None:
			return "";

		url = urlparse(photo['source']);
		conn = httplib.HTTPConnection(url.netloc)
		conn.connect()
		conn.request("GET", url.path, None, {'Range': str(offset) + '-' + str(offset+size)})
		response = conn.getresponse();
		if response.status == 206:
			return response.read()
		else:
			if offset > 0:
				response.read(offset);
			return response.read(size);

	def release(self, path, flags):
		if path.startswith('/photos/'):
			if len(self.albums) == 0:
				self.fetch_albums();
			try:
				tmp = self.tempfiles[path];
				c = pycurl.Curl()
				c.setopt(pycurl.POST, 1)
				url = "https://graph.facebook.com/" + self.albums[path[8:path.find('/', 8)]]['id'] + "/photos";
				c.setopt(pycurl.URL, str(url));
				c.setopt(pycurl.HTTPPOST, [('access_token', self.access_token), ("image", (c.FORM_FILE, tmp.name))]);
				c.setopt(pycurl.MAX_SEND_SPEED_LARGE, self.max_upload_speed);
				c.perform()
				c.close()
				del self.tempfiles[path]
				os.unlink = tempfile;

			except KeyError:
				return

	def write(self, path, buf, offset):
		tmp = None;
		if self.tempfiles.has_key(path):
			tmp = self.tempfiles[path];
		else:
			self.tempfiles[path] = tmp = tempfile.NamedTemporaryFile();
		tmp.seek(offset)
		tmp.write(buf)
		return len(buf);

	def truncate(self, path, size):
		return 0

	def utime(self, path, times):
		return 0

	def mkdir(self, path, mode):
		if path.startswith('/photos/') and path.count('/') == 2:
			album = path[8:]
			conn = httplib.HTTPSConnection('graph.facebook.com');
			conn.connect()
			conn.request('POST', '/me/albums', urllib.urlencode({'access_token': str(self.access_token), 'name': str(album)}));
			response = conn.getresponse();
			decoder = json.JSONDecoder('latin_1');
			info = decoder.decode(response.read());
			albumid = info.get('id', None);
			if albumid != None:
				self.albums[album] = {'id': albumid, 'name': album, 'description': ''}
		return 0

	def rmdir(self, path):
		return 0

	def rename(self, pathfrom, pathto):
		return 0

	def fsync(self, path, isfsyncfile):
		return 0

	def fetch_albums(self):
		if len(self.albums) > 0:
			return;
		self.albums.clear();
		conn = httplib.HTTPSConnection('graph.facebook.com');
		conn.connect()
		conn.request('GET', '/me/albums?access_token=' + self.access_token)
		response = conn.getresponse();
		decoder = json.JSONDecoder('latin_1');
		info = decoder.decode(response.read());
		listdata = info.get('data', [])
		for item in listdata:
			name = str(item.get('name', '').encode('utf8'));
			self.albums[name] = item;
		conn.close()

	def fetch_photos_from_album(self, album_id):
		conn = httplib.HTTPSConnection('graph.facebook.com');
		conn.connect()
		conn.request('GET', '/' +album_id+ '/photos?access_token=' + self.access_token);
		response = conn.getresponse();
		decoder = json.JSONDecoder('latin_1');
		info = decoder.decode(response.read());
		listdata = info.get('data', [])
		self.photos[album_id] = {};
		for item in listdata:
			name = str(item.get('id', '').encode('utf8'));
			self.photos[album_id][name] = item;
		conn.close()

	def readdir(self, path, offset):
		try:
			for e in '.', '..':
				yield fuse.Direntry(e);
			if path == '/':
				yield fuse.Direntry('photos');
			elif path == '/photos':
				self.fetch_albums();
				for item in self.albums.iterkeys():
					yield fuse.Direntry(item);
			elif path.startswith('/photos') and path.count('/') == 2:
				if len(self.albums) == 0:
					self.fetch_albums();

				album_id = self.albums[path[8:]]['id']
				self.fetch_photos_from_album(album_id);
				for item in self.photos[album_id].iterkeys():
					yield fuse.Direntry(item);
		except KeyError:
			print 'File not found';

if __name__ == '__main__':
	fs = MyFS()
	fs.parse(errex=1)
	fs.multithreaded = False
	fs.main()
