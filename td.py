#!/usr/bin/env python
#coding: utf-8

import logging
import os
import subprocess
import argparse
import datetime
import jsonlib

log = logging.getLogger('transmission-dropbox')


class TransmissionDropbox(object):

    def __init__(self, dropbox_uploader_script, dropbox_uploader_config_file, dropbox_folder, transmission_remote_binary,
                 transmission_config_file, transmission_auth, tmp_folder):
        self.dropbox_uploader_script = dropbox_uploader_script
        self.dropbox_uploader_config_file = dropbox_uploader_config_file
        self.dropbox_folder = dropbox_folder
        self.transmission_remote_binary = transmission_remote_binary
        self.transmission_config_file = transmission_config_file
        self.transmission_auth = transmission_auth
        self.tmp_folder = tmp_folder
        ok, std_out = self._sudo('cat %s' % self.transmission_config_file)
        self.transmission_config = jsonlib.read(std_out)

    def _run(self, cmd):
        self.log('CMD: %s' % cmd, 'debug')
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        value = process.wait()
        std_out, std_err = process.communicate()
        if value != 0:
            self.log(std_err, 'error')
        return value, std_out

    def _sudo(self, cmd):
        return self._run('/usr/bin/sudo ' + cmd)

    def _du_cmd(self, arg):
        cmd = self._get_du_cmd_prefix() + ' ' + arg
        return self._run(cmd)

    def _get_du_cmd_prefix(self):
        ret = '/usr/bin/env bash %s -q' % self.dropbox_uploader_script
        if self.dropbox_uploader_config_file:
            ret += ' -f %s' % self.dropbox_uploader_config_file
        return ret

    def _tr_cmd(self, arg):
        cmd = self._get_tr_cmd_prefix() + ' ' + arg
        return self._run(cmd)

    def _get_tr_cmd_prefix(self):
        ret = self.transmission_remote_binary
        if self.transmission_auth:
            ret += ' -n %s' % self.transmission_auth
        return ret

    def log(self, message, level='info'):
        func = getattr(log, level)
        func('%s %s %s' % (datetime.datetime.now(), level.upper(), message))

    def _get_recursive_list(self, path):
        list_data = []
        ok, std_out = self._du_cmd('list "%s"' % path)
        for l in std_out.split('\n'):
            ft, fn = l[:5].strip(), l[5:]
            if ft == '[F]' and fn.lower().endswith('.torrent'):
                relative_path = path.lstrip(self.dropbox_folder)
                download_path = self.transmission_config['download-dir']
                if relative_path:
                    download_path += '/'+relative_path
                list_data.append((path+'/'+fn, download_path))
            elif ft == '[D]':
                list_data.extend(self._get_recursive_list(path+'/'+fn))
        return list_data

    def _download_file(self, f):
        destination = os.path.join(self.tmp_folder, os.path.split(f)[-1])
        if os.path.exists(destination):
            self.log('%s exists, skipping...' % destination)
            return destination
        ok, std_out = self._du_cmd('download "%s" "%s"' % (f, destination))
        if ok == 0:
            self.log('%s downloaded to %s' % (f, destination))
            return destination

    def list(self, only_count):
        list_data = self._get_recursive_list(self.dropbox_folder)
        if only_count:
            self.log('Torrent count: %d' % len(list_data))
            return
        for f, path in list_data:
            self.log('%s -> %s' % (f, path))

    def download(self):
        list_data = self._get_recursive_list(self.dropbox_folder)
        last_path = None
        for f, path in list_data:
            if path != last_path:
                last_path = path
                self._tr_cmd('-w "%s"' % path)
            tmp_file = self._download_file(f)
            ok, std_err = self._tr_cmd('-a "%s"' % tmp_file)

            if ok == 0 and False:
                self._du_cmd('delete "%s"' % f)

    def test(self):
        ok, std_out = self._tr_cmd('-l')
        print ok, std_out

def do_list(args, td):
    td.list(args.count)

def do_download(args, td):
    td.download()

def do_test(args, td):
    td.test()

parser = argparse.ArgumentParser(description='Download with transmission-daemon from Dropbox folder')
parser.add_argument('-d', metavar='/path/to/dropbox_uploader.sh', help='dropbox uploader script location',
                    action='store', default='dropbox_uploader.sh')
parser.add_argument('-dc', metavar='/path/to/.dropbox_uploader', help='dropbox uploader config file location',
                    action='store', default='~/.dropbox_uploader')
parser.add_argument('-df', metavar='dropbox/folder', help='dropbox folder',
                    action='store', default='Downloads/torrent')
parser.add_argument('-t', metavar='/path/to/transmission-remote', help='transmission-remote location',
                    action='store', default='/usr/bin/transmission-remote')
parser.add_argument('-tc', metavar='/path/to/settings.json', help='transmission config file location',
                    action='store', default='/etc/transmission-daemon/settings.json')
parser.add_argument('-tn', metavar='user:pw', help='transmission-remote auth',
                    action='store', default='')
parser.add_argument('-tmp', metavar='/path/to/tmp', help='tmp folder', action='store', default='/tmp')

subparsers = parser.add_subparsers()
parser_list = subparsers.add_parser('list', help='List torrents')
parser_list.add_argument('--count', action='store_true', help='only count torrent files')
parser_list.set_defaults(func=do_list)

parser_list = subparsers.add_parser('download', help='Download torrents')
parser_list.set_defaults(func=do_download)

parser_test = subparsers.add_parser('test', help='Just a test')
parser_test.set_defaults(func=do_test)

if __name__ == '__main__':
    log.setLevel(logging.DEBUG)
    console = logging.StreamHandler()
    log.addHandler(console)
    args = parser.parse_args()
    td = TransmissionDropbox(args.d, args.dc, args.df, args.t, args.tc, args.tn, args.tmp)
    args.func(args, td)
