#!/usr/bin/env python
from setuptools import setup

setup(
    name='calm',
    version='20250329',
    description='Cygwin packaging maintenance tool',
    long_description=open('README.md').read(),
    author='Jon Turney',
    author_email='jon.turney@dronecode.org.uk',
    license='MIT',
    packages=['calm'],
    entry_points={
        'console_scripts': [
            'calm = calm.calm:main',
            'calm-tool = calm.tool:main',
            'mkgitoliteconf = calm.mkgitoliteconf:main',
            'mksetupini = calm.mksetupini:main',
        ],
    },
    url='https://cygwin.com/git/?p=cygwin-apps/calm.git',
    test_suite='tests',
    install_requires=[
        'license_expression',
        'markdown',
        'peewee',
        'pidlockfile',
        'python-daemon',
        'xtarfile[zstd]',
    ],
)
