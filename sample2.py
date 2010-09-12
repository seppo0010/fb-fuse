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
import urllib2
from multipart import Multipart

fuse.fuse_python_api = (0, 2)

class MyFS(fuse.Fuse):
	albums = {};
	access_token = None;
	tempfiles = {};

	def __init__(self, *args, **kw):
		fuse.Fuse.__init__(self, *args, **kw)
		home = os.getenv('HOME');
		if home == None:
			sys.exit('No access token set');

		try:
			config = ConfigParser.ConfigParser()
			config.read([home + '/.fbfuserc'])
			self.access_token = config.get('facebook', 'access_token');
			if self.access_token == None:
				sys.exit('No access token set');
		except ConfigParser.Error:
			sys.exit('No access token set');

	def getattr(self, path):
		st = fuse.Stat()
		if path == '/' or path == '/photos' or (path.startswith('/photos') and path.count('/') == 2):
			st.st_mode = stat.S_IFDIR | 0755
			st.st_nlink = 2
		else:
			st.st_mode = stat.S_IFREG | 0755
			st.st_nlink = 1
		st.st_atime = int(time.time())
		st.st_mtime = st.st_atime
		st.st_ctime = st.st_atime

		return st

	def mknod(self, path, mode, dev):
		return -EINVAL

	def open(self, path, flags):
		return 0

	def release(self, path, flags):
		if path.startswith('/photos/'):
			if len(self.albums) == 0:
				self.fetch_albums();
			tmp = self.tempfiles[path];
			tmp.seek(0, os.SEEK_SET);
			file = tmp.read();
			m = Multipart()
			m.field('access_token',self.access_token)
			m.file('source','image',file,{'Content-Type':'image/jpeg'})
			ct,body = m.get()

			request = urllib2.Request('https://graph.facebook.com/' + self.albums[path[8:path.find('/', 8)]]['id'] + '/photos',body,{'Content-Type':ct});
			reply = urllib2.urlopen(request)
			tempfile = tmp.name;
			tmp.close();
			del self.tempfiles[path]
			os.unlink = tempfile;

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
		return 0

	def rmdir(self, path):
		return 0

	def rename(self, pathfrom, pathto):
		return 0

	def fsync(self, path, isfsyncfile):
		return 0

	def fetch_albums(self):
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

	def readdir(self, path, offset):
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

			conn = httplib.HTTPSConnection('graph.facebook.com');
			try:
				conn.connect()
				conn.request('GET', '/' +self.albums[path[8:]]['id']+ '/photos?access_token=' + self.access_token);
				response = conn.getresponse();
				decoder = json.JSONDecoder('latin_1');
				info = decoder.decode(response.read());
				listdata = info.get('data', [])
				for item in listdata:
					name = str(item.get('id', '').encode('utf8'));
					yield fuse.Direntry(name);
			except KeyError:
				print 'File not found';
			conn.close()

if __name__ == '__main__':
	fs = MyFS()
	fs.parse(errex=1)
	fs.main()
