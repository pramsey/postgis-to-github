#!/bin/bash

# Stop on error
set -e

# Load config info
source 00-config.sh

if [ ! -d $work_dir ]; then
    mkdir -p $work_dir
    pushd $work_dir
fi

#
# Fetch the username map
#
echo "Fetching $svn_url/trunk/authors.git into users.txt"
curl $svn_url/trunk/authors.git > users.txt

#
# Clone the SVN repository locally
#
echo "Cloning $svn_url into git repository ./$git_dir"
git svn clone $svn_url \
    --stdlayout \
	--prefix "" \
    --authors-file=users.txt \
    -s $git_dir

#--no-metadata \

#
# Enter repo
#
pushd $git_dir

#
# Fix up the tags, per
# https://git-scm.com/book/en/v2/Git-and-Other-Systems-Migrating-to-Git
# "move the tags so they’re actual tags rather than strange remote branches"
#
echo "Turning remote branches into tags"
for t in $(git for-each-ref --format='%(refname:short)' refs/remotes/tags); do
    git tag ${t/tags\//} $t && git branch -D -r $t
done

#
# "move the rest of the references under refs/remotes to be local branches" 
#
echo "Turning remote references into local branches"
for b in $(git for-each-ref --format='%(refname:short)' refs/remotes); do 
    git branch $b refs/remotes/$b && git branch -D -r $b
done

#
# "If you do not care anymore about the peg-revisions, simply remove them"
#
echo "Dropping peg revisions"
for p in $(git for-each-ref --format='%(refname:short)' | grep @); do 
    git branch -D $p
done

#
# "Unfortunately, git svn creates an extra branch named trunk"
#
echo "Dropping 'trunk' branch in favor of 'master'"
git branch -d trunk

#
# Drop some specific postgis branches
#
git branch -D gSoC2007
git branch -D gSoC2007_raster
git branch -D pgis_0_9_0
git branch -D pgis_1_0
git branch -D refractions

#
# Drop some tags that already exist with nicer names
#
git tag -d pgis_0_5_0
git tag -d pgis_0_6_0
git tag -d pgis_0_6_1
git tag -d pgis_0_6_2
git tag -d pgis_0_7_0
git tag -d pgis_0_7_1
git tag -d pgis_0_7_2
git tag -d pgis_0_7_3
git tag -d pgis_0_7_4
git tag -d pgis_0_7_5
git tag -d pgis_0_8_0
git tag -d pgis_0_8_1
git tag -d pgis_0_8_2
git tag -d pgis_0_9_1
git tag -d pgis_0_9_2
git tag -d pgis_1_0_0
git tag -d pgis_1_0_0RC1
git tag -d pgis_1_0_0RC2
git tag -d pgis_1_0_0RC3
git tag -d pgis_1_0_0RC4
git tag -d pgis_1_0_0RC5
git tag -d pgis_1_0_0RC6
git tag -d pgis_1_0_1
git tag -d pgis_1_0_2
git tag -d pgis_1_0_3
git tag -d pgis_1_0_4
git tag -d pgis_1_0_5
git tag -d pgis_1_0_6
git tag -d pgis_1_1_0
git tag -d pgis_1_1_1
git tag -d pgis_1_1_2
git tag -d pgis_1_1_3
git tag -d postgis-0_7
git tag -d postgis_0_5
git tag -d pre_1_0_2_rc1
git tag -d pre_1_0_2_unionTest
git tag -d start

exit

# find all files that are large
# git rev-list --objects --all | sort -k 2 > allfileshas.txt;git gc && git verify-pack -v .git/objects/pack/pack-*.idx | egrep "^\w+ blob\W+[0-9]+ [0-9]+ [0-9]+$" | sort -k 3 -n -r > bigobjects.txt
# sort by largest
# for SHA in `cut -f 1 -d\  < bigobjects.txt`; do echo $(grep $SHA bigobjects.txt) $(grep $SHA allfileshas.txt) | awk '{print$1,$3,$7}' >> bigtosmall.txt; done
# purge large files
# git filter-branch -f --prune-empty --index-filter 'git rm -rf --cached --ignore-unmatch MY-BIG-DIRECTORY-OR-FILE' --tag-name-filter cat -- --all


#
# Create revision-hash lookup table
# https://github.com/poseidix/TRAC-SVN-to-GIT-migration/blob/master/createLookupTable.sh
#
../../scripts/createLookupTable.sh > ../rev-lookup.txt

#
# Add the Github repository as an origin
#
echo "Pushing repository back to $github_remote"
git remote add origin $github_remote
git push origin --all
git push origin --tags

#
# Return home
#
popd && popd
echo "Done source code cloning step"


