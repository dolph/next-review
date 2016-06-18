# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""
Select a code review from gerrit that needs attention.

This module queries gerrit for a code review that needs attention and presents
it to the user without any hassle of navigating the gerrit UI to select a
review manually.

Older reviews that are ready for human eyes are given priority.

"""

from __future__ import print_function

import argparse
try:
    import ConfigParser as configparser
except ImportError:
    import configparser
import errno
import getpass
import json
import os
import sys
import time
import webbrowser

import paramiko
import pkg_resources
import requests


__version__ = pkg_resources.require('next-review')[0].version


BOTS = frozenset(['jenkins', 'smokestack'])
DEFAULT_GERRIT_HOST = 'review.openstack.org'
DEFAULT_GERRIT_PORT = 29418
CONFIG_FILE_OPTIONS = frozenset(['host', 'port', 'username', 'email', 'key',
                                 'projects', 'nodownvotes'])
REVIEWDAY_JSON_URL = 'http://status.openstack.org/reviews/reviewday.json'


class ReviewDayData(object):

    def __init__(self):
        self._cache_file = os.path.expanduser('~/.reviewday.json')
        self._data = {}

    def _is_cache_old(self):
        try:
            stat = os.stat(self._cache_file)
        except OSError as e:
            if e.errno == errno.ENOENT:  # file not found
                return True
            raise
        one_day = 60 * 60 * 24
        return time.time() > (stat.st_mtime + one_day)

    def _update_data(self):
        r = requests.get(REVIEWDAY_JSON_URL)
        with open(self._cache_file, 'w') as f:
            f.write(r.content)

    def load(self):
        if self._is_cache_old():
            self._update_data()

        self._data = json.load(open(self._cache_file))
        return self

    def get_score(self, review):
        # remove openstack/ from project name
        project_name = review['project'].split('/')[-1]
        if project_name not in self._data['projects']:
            return -1
        url_parts = review['url'].rsplit('/', 1)
        project_url = url_parts[0] + '/#change,' + url_parts[1]
        return self._data['projects'][project_name][project_url]['score']


def ssh_client(host, port, user=None, key=None):
    """Build an SSH client to gerrit."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.load_system_host_keys()
    try:
        client.connect(host, port=port, key_filename=key, username=user)
    except paramiko.PasswordRequiredException:
        password = getpass.getpass('SSH Key Passphrase: ')
        client.connect(host, port=port, key_filename=key, username=user,
                       password=password)
    return client


def get_reviews(client, projects, nodownvotes, onlyplusone, onlyplustwo,
                noplustwo):
    """Query gerrit for a list of reviews in the given project(s)."""
    reviews = []

    if projects:
        # prefix each project name with the project search operator
        projects = ['project:' + project for project in projects]

        project_query = '(' + ' OR '.join(projects) + ')'
    else:
        project_query = '(is:watched OR is:starred)'

    query = [
        project_query, 'is:open',
        'label:Verified+1,jenkins',
        'NOT label:Code-Review<=+2,self', 'label:Workflow+0', 'limit:1000']

    # The API for this method is a bit of a mess with all the filtering options
    # below, but I can't think of a way to simplify the API without changing
    # the method's behavior?
    if nodownvotes:
        query.append('NOT label:Code-Review<=-1')
    if onlyplusone:
        query.append('label:Code-Review>=+1')
    if onlyplustwo:
        query.append('label:Code-Review>=+2')
    if noplustwo:
        query.append('NOT label:Code-Review=+2')

    command = ['gerrit', 'query']
    command.extend(query)
    command.extend(['--current-patch-set', '--comments', '--format=JSON'])
    stdin, stdout, stderr = client.exec_command(' '.join(command))

    for line in stdout:
        reviews.append(json.loads(line))

    return reviews[:-1]


def sort_review_by_reviewday_score(reviews):
    return sorted(reviews,
                  key=lambda review: (-review['score'], review['lastUpdated']))


def votes_for_review(review):
    """Return a list of votes for the specified review."""
    return [int(x['value'])
            for x in review['currentPatchSet'].get('approvals', [])
            if x['type'] in ('Code-Review', 'Verified')]


def _name(ref):
    """Return the username or email of a reference."""
    return ref.get('username', ref.get('email'))


def render_reviews(reviews, maximum=None):
    """Render one or more review links back to the CLI."""
    class Colorize(object):
        NORMAL = '\033[0m'
        LINK = '\x1b[34m'
        PROJECT = '\x1b[33m'

        @property
        def enabled(self):
            return os.environ.get('CLICOLOR')

        def link(self, s):
            return self.LINK + s + self.NORMAL if self.enabled else s

        def project(self, name):
            return self.PROJECT + name + self.NORMAL if self.enabled else name

    colorize = Colorize()

    for review in reviews[:maximum]:
        print('{} {} {}'.format(colorize.link(review['url']),
                                colorize.project(review['project']),
                                review['subject'].strip()))


def ignore_my_good_reviews(reviews, username=None, email=None):
    """Ignore reviews created by me unless they need my attention."""
    for review in reviews:
        vote_values = set(votes_for_review(review))
        if _name(review['owner']) not in (username, email):
            # either it's not our own review
            yield review
        elif (_name(review['owner']) in (username, email)
                and set((-1, -2)) & vote_values):
            # or it is our own review, and it has a downvote
            yield review


def ignore_previously_commented(reviews, username=None, email=None):
    """Ignore reviews where I'm the last commenter."""
    for review in reviews:
        if _name(review['comments'][-1]['reviewer']) not in (username, email):
            yield review


def filter_ignore_file(reviews, ignore_file):
    reviews_to_ignore = open(ignore_file).read().split()
    for review in reviews:
        if review['url'] in reviews_to_ignore:
            continue
        yield review


def add_reviewday_scores(reviews, reviewday):
    for review in reviews:
        review['score'] = reviewday.get_score(review)
        yield review


def get_config():
    """Load the configuration."""
    options = []
    modified = set()
    parser = argparse.ArgumentParser(
        prog='next-review',
        description='Start your next gerrit code review without any hassle.')
    options.append(parser.add_argument('--version', action='store_true',
                                       help='Show version number and exit'))
    options.append(parser.add_argument(
        '-f', '--config-file', type=str,
        default=os.path.expanduser('~/.next_review'),
        help='Path to configuration file. Default: %(default)s'))
    options.append(parser.add_argument(
        '-s', '--config-section', type=str, default=None,
        help='If multiple gerrit servers are configured in your configuration '
             'file, use --config-section to specify the section to use'))
    options.append(parser.add_argument(
        '-H', '--host', type=str, default=DEFAULT_GERRIT_HOST,
        help='SSH hostname for gerrit'))
    options.append(parser.add_argument(
        '-p', '--port', type=int, default=DEFAULT_GERRIT_PORT,
        help='SSH port for gerrit'))
    options.append(parser.add_argument(
        '-u', '--username', type=str, default=getpass.getuser(),
        help='Your SSH username for gerrit'))
    options.append(parser.add_argument(
        '-e', '--email', type=str, default=None,
        help='Your email address for gerrit'))
    options.append(parser.add_argument(
        '-k', '--key', type=str, default=None,
        help='Path to your SSH public key for gerrit'))
    parser.add_argument(
        '-l', '--list', action='store_true',
        help='List recommended code reviews in order of descending priority')
    options.append(parser.add_argument(
        '-n', '--nodownvotes', action='store_true',
        help='Ignore reviews that have a downvote from anyone'))
    upvote_group = parser.add_mutually_exclusive_group()
    options.append(upvote_group.add_argument(
        '-t', '--noplustwo', action='store_true',
        help='Ignore reviews that already have a +2 from anyone'))
    options.append(upvote_group.add_argument(
        '-1', '--onlyplusone', action='store_true',
        help='Only show reviews that have an upvote from anyone'))
    options.append(upvote_group.add_argument(
        '-2', '--onlyplustwo', action='store_true',
        help='Only show reviews that have a +2 from a human'))
    options.append(parser.add_argument(
        'projects', metavar='project', nargs='*', default=None,
        help='Projects to include when checking reviews'))
    options.append(parser.add_argument(
        '--ignore-file', type=str, default=None,
        help='An file containing a list of reviews to ignore'))

    option_dict = {opt.dest: opt for opt in options}
    args = parser.parse_args()
    config_parser = configparser.ConfigParser()
    try:
        with open(args.config_file, 'r') as cfg:
            config_parser.readfp(cfg)
    except IOError:
        return args

    sections = ['DEFAULT']

    if args.config_section is not None:
        if config_parser.has_section(args.config_section):
            sections.append(args.config_section)

    for section in sections:
        for option in CONFIG_FILE_OPTIONS:
            opt_cfg = option_dict[option]
            # CLI arguments win every time. Defaults can be overridden by the
            # config file
            if getattr(args, option) == opt_cfg.default or option in modified:
                if config_parser.has_option(section, option):
                    value = config_parser.get(section, option)
                    # Type expected and type received in the config file
                    # is important.
                    if (opt_cfg.type == type(value) or option == 'projects' or
                            option == 'port'):
                        if option == 'projects':
                            if type(value) != str:
                                raise Exception('OMG')
                            else:
                                value = value.split(',')
                        elif option == 'port':
                            try:
                                value = opt_cfg.type(value)
                            except Exception:
                                print(('Option {0} in config file is of wrong '
                                       'type.').format(option))
                                continue
                        setattr(args, option, value)
                        modified.add(option)
                        continue
                    else:
                        print(('Option {0} in config file is of wrong '
                               'type.').format(option))

    return args


def main(args):
    """Query gerrit, filter reviews, and render the result."""
    client = ssh_client(
        host=args.host, port=args.port, user=args.username, key=args.key)

    reviews = get_reviews(
        client, args.projects, args.nodownvotes, args.onlyplusone,
        args.onlyplustwo, args.noplustwo)

    # filter out reviews that are not prime review targets
    reviews = ignore_my_good_reviews(
        reviews, username=args.username, email=args.email)
    reviews = ignore_previously_commented(
        reviews, username=args.username, email=args.email)
    if args.ignore_file:
        reviews = filter_ignore_file(reviews, args.ignore_file)

    reviewday = ReviewDayData().load()
    reviews = add_reviewday_scores(reviews, reviewday)
    reviews = sort_review_by_reviewday_score(reviews)

    if args.list:
        render_reviews(reviews)
    elif reviews:
        render_reviews(reviews, maximum=1)

        # open the oldest code review in a browser
        webbrowser.open(reviews[0]['url'])
    else:
        print('Nothing to review!')

    sys.exit(len(reviews))


def merge_ssh_config(args):
    """Merge the local SSH config into next-review's config."""
    ssh_config = paramiko.SSHConfig()

    try:
        ssh_config.parse(open(os.path.expanduser('~/.ssh/config')))
    except IOError:
        # The user does not have an SSH config file (FileNotFoundError on py3),
        # so just bail.
        return

    host_config = ssh_config.lookup(args.host)

    if 'user' in host_config and not args.username:
        args.username = host_config['user']
    if 'identityfile' in host_config and not args.key:
        args.key = host_config['identityfile']


def cli():
    """Run the CLI."""
    args = get_config()
    merge_ssh_config(args)

    if args.version:
        print(pkg_resources.require('next-review')[0])
        sys.exit()

    main(args)


if __name__ == '__main__':
    cli()
