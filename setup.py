#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from setuptools import find_packages, setup

setup(
    name="aws-sso-credentials",
    version="0.0.1",
    author="Foo",
    author_email="foo@example.org",
    description="",
    url="https://github.com/kwark/aws-sso-credentials",
    package_dir={'': 'src'},
    packages=find_packages(where='src'),
    include_package_data=True,
    keywords=[],
    entry_points={"console_scripts": ["awssso=awssso.main:main"]},
    install_requires=[
        "boto3 >= 1.12.6",
        "inquirer >= 2.6.3",
        "python-dateutil >=2.8.1"
    ],
    python_requires=">=3.6",
    license="License :: OSI Approved :: MIT License",
    classifiers=[
        "Programming Language :: Python :: 3",
        # "Operating System :: OS Independent",
        # "Private :: Do Not Upload"
    ],
)