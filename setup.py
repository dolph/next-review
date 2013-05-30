import setuptools


setuptools.setup(
    name='next-review',
    version='1.0.0',
    scripts=['next_review.py'],
    install_requires=['paramiko'],
    py_modules=['next_review'],
    entry_points={'console_scripts': ['next-review = next_review:cli']})
