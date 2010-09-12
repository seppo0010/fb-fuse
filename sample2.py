#!/usr/bin/env python
# -*- coding: utf-8 -*-
import errno
import fuse
import stat
import time
import httplib
import json

fuse.fuse_python_api = (0, 2)

class MyFS(fuse.Fuse):
	albums = {};
	access_token = '<fill me>';

	def __init__(self, *args, **kw):
		fuse.Fuse.__init__(self, *args, **kw)

	def getattr(self, path):
		st = fuse.Stat()
		st.st_mode = stat.S_IFDIR | 0755
		st.st_nlink = 2
		st.st_atime = int(time.time())
		st.st_mtime = st.st_atime
		st.st_ctime = st.st_atime

		return st

	def readdir(self, path, offset):
		for e in '.', '..':
			yield fuse.Direntry(e);
		if path == '/':
			yield fuse.Direntry('photos');
		elif path == '/photos':
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
				yield fuse.Direntry(name);
				self.albums[name] = item;

		elif path.startswith('/photos') and path.count('/') == 2:
			if len(self.albums) == 0:
				self.readdir('/photos',0);

			conn = httplib.HTTPSConnection('graph.facebook.com');
			conn.connect()
			conn.request('GET', '/' +self.albums[path[8:]]['id']+ '/photos?access_token=' + self.access_token);
			response = conn.getresponse();
			decoder = json.JSONDecoder('latin_1');
			info = decoder.decode(response.read());
			listdata = info.get('data', [])
			for item in listdata:
				name = str(item.get('id', '').encode('utf8'));
				yield fuse.Direntry(name);

if __name__ == '__main__':
	fs = MyFS()
	fs.parse(errex=1)
	fs.main()
