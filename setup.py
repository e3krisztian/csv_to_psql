#!/usr/bin/env python
# coding: utf8

# distutils is nice and recommended, but pip will not install requires=
# requirements :(, so going with setuptools - as everyone else?!
# from distutils.core import setup
from setuptools import setup, find_packages
import sys

setup(
    name='csv_to_psql',
    version=':versiontools:csv_to_psql:',
    description=(
        'Convert CSV input on STDIN to a psql script on STDOUT that imports it'
    ),
    author='Krisztián Fekete',
    author_email='fekete.krisztyan@gmail.com',
    url='http://maybe.later',
    packages=find_packages(),
    setup_requires=['versiontools >= 1.8'],
    install_requires=[],
    tests_require=[
        'fixtures>=0.3.14',
        'testtools>=0.9.32',
        'nose >=1.3'
    ],
    test_suite='nose.collector',
    entry_points={
        'console_scripts': [
            'csv_to_psql = csv_to_psql.main:main',
        ]
    },
    use_2to3=sys.version_info.major > 2
    )
