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

import argparse
import json
import os
import sys
import webbrowser

import paramiko
import pkg_resources


__version__ = pkg_resources.require('next-review')[0].version


DEFAULT_GERRIT_HOST = 'review.openstack.org'
DEFAULT_GERRIT_PORT = 29418


def ssh_client(host, port, user=None, key=None):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.load_system_host_keys()
    client.connect(host, port=port, key_filename=key, username=user)
    return client


def get_reviews(client, projects):
    reviews = []

    while True:
        project_query = '(' + ' OR '.join(projects) + ')'
        query = [
            'gerrit', 'query', project_query, 'is:open', '(-Verified-1)',
            'limit:100', '--current-patch-set', '--comments', '--format=JSON']
        if reviews:
            query.append('resume_sortkey:%s' % reviews[-2]['sortKey'])
        stdin, stdout, stderr = client.exec_command(' '.join(query))

        for line in stdout:
            reviews.append(json.loads(line))
        if reviews[-1]['rowCount'] == 0:
            break

    return [x for x in reviews if 'id' in x]


def sort_reviews_by_last_updated(reviews):
    """Sort reviews in ascending order by last update date."""
    return sorted(reviews, key=lambda review: review['lastUpdated'])


def votes_by_name(review):
    """Return a dict of votes like {'name': -1}."""
    return dict([(_name(x['by']), int(x['value']))
                 for x in review['currentPatchSet'].get('approvals', [])])


def _name(ref):
    """Returns the username or email of a reference."""
    return ref.get('username', ref.get('email'))


def render_reviews(reviews, maximum=None):
    class Colorize(object):
        NORMAL = '\033[0m'
        LINK = '\x1b[34m'

        @property
        def enabled(cls):
            return os.environ.get('CLICOLOR')

        def link(cls, s):
            return cls.LINK + s + cls.NORMAL if cls.enabled else s

    colorize = Colorize()

    for review in reviews[:maximum]:
        print colorize.link(review['url']), review['subject'].strip()


def ignore_blocked_reviews(reviews):
    filtered_reviews = []
    for review in reviews:
        if -2 not in votes_by_name(review).values():
            filtered_reviews.append(review)
    return filtered_reviews


def require_jenkins_upvote(reviews):
    filtered_reviews = []
    for review in reviews:
        votes = votes_by_name(review)
        if 'jenkins' in votes and votes['jenkins'] >= 1:
            filtered_reviews.append(review)
    return filtered_reviews


def ignore_all_downvotes(reviews):
    filtered_reviews = []
    for review in reviews:
        votes = votes_by_name(review)
        values = set(votes.itervalues())
        if not set((-1, -2)) & values:
            filtered_reviews.append(review)
    return filtered_reviews


def ignore_smokestack_downvotes(reviews):
    """Smokestack doesn't verify all reviews, so we can't require upvotes."""
    filtered_reviews = []
    for review in reviews:
        votes = votes_by_name(review)
        if 'smokestack' not in votes or votes['smokestack'] != -1:
            filtered_reviews.append(review)
    return filtered_reviews


def ignore_my_reviews(reviews, username=None, email=None):
    """Ignore reviews created by me."""
    filtered_reviews = []
    for review in reviews:
        if _name(review['owner']) not in (username, email):
            filtered_reviews.append(review)
    return filtered_reviews


def ignore_previously_reviewed(reviews, username=None, email=None):
    """Ignore things I've already reviewed."""
    filtered_reviews = []
    for review in reviews:
        if (username not in votes_by_name(review)
                and email not in votes_by_name(review)):
            filtered_reviews.append(review)
    return filtered_reviews


def ignore_previously_commented(reviews, username=None, email=None):
    """Ignore reviews where I'm the last commenter."""
    filtered_reviews = []
    for review in reviews:
        if _name(review['comments'][-1]['reviewer']) not in (username, email):
            filtered_reviews.append(review)
    return filtered_reviews


def ignore_wip(reviews):
    return [x for x in reviews if x['status'] != 'WORKINPROGRESS']


def main(args):
    client = ssh_client(
        host=args.host, port=args.port, user=args.username, key=args.key)

    reviews = get_reviews(client, args.projects)

    # filter out reviews that are not prime review targets
    reviews = ignore_wip(reviews)
    reviews = ignore_blocked_reviews(reviews)
    reviews = require_jenkins_upvote(reviews)
    reviews = ignore_smokestack_downvotes(reviews)
    if args.nodownvotes:
        reviews = ignore_all_downvotes(reviews)
    reviews = ignore_my_reviews(
        reviews, username=args.username, email=args.email)
    reviews = ignore_previously_reviewed(
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
        print 'Nothing to review!'

    sys.exit(len(reviews))


def cli():
    parser = argparse.ArgumentParser(
        prog='next-review',
        description='Start your next gerrit code review without any hassle.')
    parser.add_argument(
        '--version', action='store_true',
        help='Show version number and exit')
    parser.add_argument(
        '-H', '--host', default=DEFAULT_GERRIT_HOST,
        help='SSH hostname for gerrit')
    parser.add_argument(
        '-p', '--port', type=int, default=DEFAULT_GERRIT_PORT,
        help='SSH port for gerrit')
    parser.add_argument(
        '-u', '--username', default=os.getlogin(),
        help='Your SSH username for gerrit')
    parser.add_argument(
        '-e', '--email', default=None,
        help='Your email address for gerrit')
    parser.add_argument(
        '-k', '--key', default=None,
        help='Path to your SSH public key for gerrit')
    parser.add_argument(
        '-l', '--list', action='store_true',
        help='List recommended code reviews in order of descending priority')
    parser.add_argument(
        '-n', '--nodownvotes', action='store_true',
        help='Ignore reviews that have a downvote from anyone')
    parser.add_argument(
        'projects', metavar='project', nargs='*', default=['is:watched'],
        help='Projects to include when checking reviews')
    args = parser.parse_args()

    if args.version:
        print pkg_resources.require('next-review')[0]
        sys.exit()

    main(args)


if __name__ == '__main__':
    cli()
