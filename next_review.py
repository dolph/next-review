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
import getpass
import json
import os
import sys
import webbrowser

import paramiko
import pkg_resources


__version__ = pkg_resources.require('next-review')[0].version


BOTS = frozenset(['jenkins', 'smokestack'])
DEFAULT_GERRIT_HOST = 'review.openstack.org'
DEFAULT_GERRIT_PORT = 29418
CONFIG_FILE_OPTIONS = frozenset(['host', 'port', 'username', 'email', 'key',
                                 'projects', 'nodownvotes'])


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


def get_reviews(client, projects, include_downvotes=True):
    """Query gerrit for a list of reviews in the given project(s)."""
    reviews = []

    if projects:
        # prefix each project name with the project search operator
        projects = ['project:' + project for project in projects]

        project_query = '(' + ' OR '.join(projects) + ')'
    else:
        project_query = '(is:watched OR is:starred)'

    query = [
        'gerrit', 'query', project_query, 'is:open',
        'label:Verified+1,jenkins', 'NOT label:Code-Review-2',
        'NOT label:Code-Review<=+2,self', 'label:Workflow+0', 'limit:1000']

    if not include_downvotes:
        query.append('NOT label:Code-Review<=-1')

    query.extend(['--current-patch-set', '--comments', '--format=JSON'])
    stdin, stdout, stderr = client.exec_command(' '.join(query))

    for line in stdout:
        reviews.append(json.loads(line))

    return reviews[:-1]


def sort_reviews_by_last_updated(reviews):
    """Sort reviews in ascending order by last update date."""
    return sorted(reviews, key=lambda review: review['lastUpdated'])


def votes_by_name(review):
    """Return a dict of votes like {'name': -1}."""
    return dict([(_name(x['by']), int(x['value']))
                 for x in review['currentPatchSet'].get('approvals', [])
                 if x['type'] in ('Code-Review', 'Verified')])


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
    filtered_reviews = []
    for review in reviews:
        vote_values = set(votes_by_name(review).values())
        if _name(review['owner']) not in (username, email):
            # either it's not our own review
            filtered_reviews.append(review)
        elif (_name(review['owner']) in (username, email)
                and set((-1, -2)) & vote_values):
            # or it is our own review, and it has a downvote
            filtered_reviews.append(review)
    return filtered_reviews


def ignore_previously_commented(reviews, username=None, email=None):
    """Ignore reviews where I'm the last commenter."""
    filtered_reviews = []
    for review in reviews:
        if _name(review['comments'][-1]['reviewer']) not in (username, email):
            filtered_reviews.append(review)
    return filtered_reviews


def require_plus_x(reviews, threshold):
    """Require a minimum Code-Review score."""
    filtered_reviews = []
    for review in reviews:
        votes = votes_by_name(review)
        for reviewer, vote in votes.iteritems():
            if reviewer not in BOTS and vote >= threshold:
                filtered_reviews.append(review)
                break
            return filtered_reviews


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
        '-1', '--onlyplusone', action='store_true',
        help='Only show reviews that have an upvote from a human'))
    options.append(upvote_group.add_argument(
        '-2', '--onlyplustwo', action='store_true',
        help='Only show reviews that have a +2 from a human'))
    options.append(parser.add_argument(
        'projects', metavar='project', nargs='*', default=None,
        help='Projects to include when checking reviews'))

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
        client, args.projects, include_downvotes=not args.nodownvotes)

    # filter out reviews that are not prime review targets
    if args.onlyplustwo:
        reviews = require_plus_x(reviews, 2)
    elif args.onlyplusone:
        reviews = require_plus_x(reviews, 1)
    reviews = ignore_my_good_reviews(
        reviews, username=args.username, email=args.email)
    reviews = ignore_previously_commented(
        reviews, username=args.username, email=args.email)

    # review old stuff before it expires
    reviews = sort_reviews_by_last_updated(reviews)

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
    ssh_config.parse(open(os.path.expanduser('~/.ssh/config')))
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
