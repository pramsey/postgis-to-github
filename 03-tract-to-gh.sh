#!/bin/bash

# 
# The CONFIGURATION section of trac2github.py needs extensive editing
# before the script can be run. You'll also need to get yourself a 
# "personal access token" if you have 2-factor auth enabled on your account
# https://help.github.com/articles/creating-a-personal-access-token-for-the-command-line/
#
# You'll probably need to pip install 
# - pygithub
# - psychopg2
# - requests

python scripts/trac2github.py

