next-review
===========

Start your next gerrit code review without any hassle.

So you have 10 minutes to spend on code reviews and you want to be as
productive as possible. You definitely don't want to spend 9 minutes shuffling
through code reviews that Jenkins already hates, you've already reviewed, etc.,
and you should definitely be looking at that awesome patch that's about to
expire due to two weeks of inactivity.

Solution: Use `next-review` to immediately jump to the "highest priority" code
review currently awaiting your gracious downvotes. Inhale some code, articulate
your opinion, cast your vote and then move on to your `next-review`. Got it?

Installation
------------

    $ python setup.py install

Usage
-----

If you can use `git-review`, you can probably use `next-review`. Assuming
you're watching some projects in gerrit, have an SSH key public key somewhere
obvious and your login name matches your gerrit username, you can just do:

    $ next-review
    https://review.openstack.org/20404 Use AuthRef for some client fields

The link will be automatically opened for you, because that's how lazy I am.

You can also abuse the return code to see how many reviews you have left to go
until it's time for beer and/or sleep.

    $ echo $?
    5

Or, you can just view the entire list without automatically opening any links:

    $ next-review --list
    https://review.openstack.org/20404 Use AuthRef for some client fields
    https://review.openstack.org/26665 Fail-safe mechanism: issue unscoped token if user's default project is invalid.
    https://review.openstack.org/29878 A minor refactor in wsgi.py
    https://review.openstack.org/29393 bp/temporary-user-provisioning
    https://review.openstack.org/30386 Add name arguments to keystone command.

Philosophy
----------

1. Older changes should be reviewed first.
2. If Jenkins is failing a change, then the author has work to do.
3. If SmokeStack is failing a change, then the author has work to do. If
   SmokeStack hasn't reviewed a change, that's okay... SmokeStack is lazy, too.
4. If a change is already blocked by a core reviewer or marked WIP or Draft,
   then it's not going to merge right now anyway.
