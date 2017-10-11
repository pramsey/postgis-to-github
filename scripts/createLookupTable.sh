#!/bin/sh

# This script creates a 'lookup table', matching SVN revision IDs with GIT revision IDs
# Run it inside a GIT repository that is imported from SVN with "git svn".
#
# Usage:
#	createLookupTable > lookupTable.txt

# Creates a lookup table between SVN IDs and Git IDs
git rev-list --all --pretty=medium > revlist.txt

# Now extract the git hash and the svn ID. Then we join lines pair-wise and we have our table
cat revlist.txt | grep git-svn-id | perl -ne 'print "$1\n" if /@(\d+) /' > svn.txt
cat revlist.txt | grep ^commit | sed -e 's/commit //' > git.txt

# Join them and write the lookup table to standard output
paste svn.txt git.txt | sort -n

# Clean up
rm svn.txt git.txt revlist.txt
