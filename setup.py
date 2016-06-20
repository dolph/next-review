import setuptools


setuptools.setup(
    name='next-review',
    version='1.6.0',
    description='Start your next gerrit code review without any hassle.',
    author='Dolph Mathews',
    author_email='dolph.mathews@gmail.com',
    url='http://github.com/dolph/next-review',
    scripts=['next_review.py'],
    install_requires=['paramiko'],
    py_modules=['next_review'],
    entry_points={'console_scripts': ['next-review = next_review:cli']},
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Topic :: Utilities',
    ],
)
