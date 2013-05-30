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

import paramiko


DEFAULT_GERRIT_HOST = 'review.openstack.org'
DEFAULT_GERRIT_PORT = 29418


def ssh_client(host, port, user=None, key=None):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.load_system_host_keys()
    client.connect(host, port=port, key_filename=key, username=user)
    return client


def get_watched_reviews(client):
    reviews = []

    while True:
        query = [
            'gerrit', 'query', 'is:watched', 'is:open', 'limit:100',
            '--current-patch-set', '--comments', '--format=JSON']
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
    """Return a dict of votes like {'name': -1}"""
    return dict([(_name(x['by']), int(x['value']))
                 for x in review['currentPatchSet'].get('approvals', [])])


def _name(ref):
    """Returns the username or email of a reference."""
    return ref.get('username', ref.get('email'))


def render_reviews(reviews, maximum=None):
    for review in reviews[:maximum]:
        print review['url'], review['subject'].strip()


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

    reviews = get_watched_reviews(client)

    # filter out reviews that are not prime review targets
    reviews = ignore_wip(reviews)
    reviews = ignore_blocked_reviews(reviews)
    reviews = require_jenkins_upvote(reviews)
    reviews = ignore_smokestack_downvotes(reviews)
    reviews = ignore_my_reviews(
        reviews, username=args.username, email=args.email)
    reviews = ignore_previously_reviewed(
        reviews, username=args.username, email=args.email)
    reviews = ignore_previously_commented(
        reviews, username=args.username, email=args.email)

    # review old stuff before it expires
    reviews = sort_reviews_by_last_updated(reviews)

    if not reviews:
        print 'Nothing to review!'
    elif args.list:
        render_reviews(reviews)
    else:
        render_reviews(reviews, maximum=1)

        # open the oldest code review in a browser
        os.system('open %s' % reviews[0]['url'])

    sys.exit(len(reviews))


def cli():
    parser = argparse.ArgumentParser(
        prog='next-review',
        description='Start your next gerrit code review without any hassle.')
    parser.add_argument(
        '--host', default=DEFAULT_GERRIT_HOST,
        help='SSH hostname for gerrit')
    parser.add_argument(
        '--port', type=int, default=DEFAULT_GERRIT_PORT,
        help='SSH port for gerrit')
    parser.add_argument(
        '--username', default=os.getlogin(),
        help='Your SSH username for gerrit')
    parser.add_argument(
        '--email', default=None,
        help='Your email address for gerrit')
    parser.add_argument(
        '--key', default=None,
        help='Path to your SSH public key for gerrit')
    parser.add_argument(
        '--list', action='store_true',
        help='List recommended code reviews in order of descending priority.')

    args = parser.parse_args()
    main(args)


if __name__ == '__main__':
    cli()
