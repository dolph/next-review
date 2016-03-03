===========
next-review
===========

Start your next gerrit code review without any hassle.

So you have 10 minutes to spend on code reviews and you want to be as
productive as possible. You definitely don't want to spend 9 minutes shuffling
through code reviews that Jenkins already hates, you've already reviewed, etc.,
and you should definitely be looking at that awesome patch that's about to
expire due to two weeks of inactivity.

Solution: Use ``next-review`` to immediately jump to the "highest priority"
code review currently awaiting your gracious downvotes. Inhale some code,
articulate your opinion, cast your vote and then move on to your
``next-review``. Got it?

Installation
------------

.. image:: https://img.shields.io/pypi/v/next-review.svg
   :target: https://pypi.python.org/pypi/next-review

From PyPi::

    $ pip install next-review

Usage
-----

If you can use ``git-review``, you can probably use ``next-review``. Assuming
you're watching some projects in gerrit, have an SSH key public key somewhere
obvious and your login name matches your gerrit username, you can just do::

    $ next-review
    https://review.openstack.org/88443 stackforge/python-openstacksdk Add Transport doc

The link will be automatically opened for you, because that's how lazy I am.

You can also abuse the return code to see how many reviews you have left to go
until it's time for beer and/or sleep::

    $ echo $?
    5

Or, you can just view the entire list without automatically opening any links::

    $ next-review --list
    https://review.openstack.org/88443 stackforge/python-openstacksdk Add Transport doc
    https://review.openstack.org/85210 openstack/keystone Fix variable passed to driver module
    https://review.openstack.org/89458 openstack/python-keystoneclient Make auth_token return a V2 Catalog
    https://review.openstack.org/90943 openstack/keystone Refactor create_trust for readability
    https://review.openstack.org/91440 openstack/identity-api Replace non-breaking space

Configuration File
------------------
``next-review`` has the concept of a multi-section (ini-style) configuration
file.  The default location it looks for it is ``~/.next_review``.  In this
configuration file the default section is ``[DEFAULT]`` and the following
options are supported: ``host``, ``port``, ``username``, ``email``, ``key``,
and ``projects``.  These values will override the defaults, but any
cli-arguments that are explicitly set will take precedence over the config
file.

If you specify sections other than ``[DEFAULT]`` you can use the ``--config-section``
argument to specify the section that should be used.  If a given option does not
exist in the specified section, the parser will look in ``[DEFAULT]`` and if
the option does not exist in either section, it will fall back to the global
defaults.  So the order of precedence would be option passed on the command
line, options in the section specified by the ``--config-section`` argument,
options in the ``[DEFAULT]`` section, and finally the global defaults.

Philosophy
----------

1. Older changes should be reviewed first.
2. If Jenkins is failing a change, then the author has work to do.
3. If SmokeStack is failing a change, then the author has work to do. If
   SmokeStack hasn't reviewed a change, that's okay... SmokeStack is lazy, too.
4. If a change is already blocked by a core reviewer or marked WIP or Draft,
   then it's not going to merge right now anyway.
