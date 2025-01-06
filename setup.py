#!/usr/bin/env python
# -*- coding:utf-8 -*-

# Author: gm.zhibo.wang
# E-mail: gm.zhibo.wang@gmail.com
# Date  :
# Desc  :

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name='xdeek_logger',
    version='0.0.4',
    author='gm.zhibo.wang',
    author_email='gm.zhibo.wang@gmail.com',
    description='An enhanced logger based on Loguru',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/wang-zhibo/xdeek_logger',
    packages=find_packages(),
    include_package_data=True,
    python_requires='>=3.6',
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        'loguru==0.7.0',
        'requests'
    ],
    project_urls={
        "Bug Reports": "https://github.com/wang-zhibo/xdeek_logger/issues",
        "Source": "https://github.com/wang-zhibo/xdeek_logger",
    },
)



