import setuptools


setuptools.setup(
    name='next-review',
    description='Start your next gerrit code review without any hassle.',
    version='1.0.1',
    scripts=['next_review.py'],
    install_requires=['paramiko'],
    py_modules=['next_review'],
    entry_points={'console_scripts': ['next-review = next_review:cli']})
