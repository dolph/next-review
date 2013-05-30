#!/usr/bin/env python

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
            '--all-approvals', '--patch-sets', '--format=JSON']
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


def render_reviews(reviews, maximum=3):
    for review in reviews[:maximum]:
        print review['url'], review['subject'].strip()


def ignore_blocked_reviews(reviews):
    filtered_reviews = []
    for review in reviews:
        votes = [x['value'] for x in review['patchSets'][-1]['approvals']]
        if "-2" not in votes:
            filtered_reviews.append(review)
    return filtered_reviews


def require_jenkins_upvote(reviews):
    filtered_reviews = []
    for review in reviews:
        for vote in review['patchSets'][-1]['approvals']:
            if vote['by']['username'] == 'jenkins' and vote['value'] == '1':
                filtered_reviews.append(review)
    return filtered_reviews


def require_smokestack_upvote(reviews):
    filtered_reviews = []
    for review in reviews:
        for vote in review['patchSets'][-1]['approvals']:
            if vote['by']['username'] == 'smokestack' and vote['value'] == '1':
                filtered_reviews.append(review)
    return filtered_reviews


def ignore_my_reviews(reviews, username=None):
    """Ignore reviews created by me."""
    filtered_reviews = []
    for review in reviews:
        if review['owner']['username'] != username:
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
    reviews = require_smokestack_upvote(reviews)
    reviews = ignore_my_reviews(reviews, username=args.username)

    # review old stuff before it expires
    reviews = sort_reviews_by_last_updated(reviews)

    if reviews and args.no_action:
        render_reviews(reviews, maximum=100)
    elif reviews and not args.no_action:
        render_reviews(reviews, maximum=1)

        # open the oldest code review in a browser
        os.system('open %s' % reviews[0]['url'])
    elif not reviews:
        print 'Nothing to review!'


if __name__ == '__main__':
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
        '--username', default=None,
        help='Your SSH username for gerrit (optional but HIGHLY recommended)')
    parser.add_argument(
        '--key', default=None,
        help='Path to your SSH public key for gerrit')
    parser.add_argument(
        '-N', '--no-action', action='store_true',
        help='Do not attempt to open the review')

    args = parser.parse_args()
    main(args)
