#!/bin/bash

# Stop on error
set -e

# Load config info
source 00-config.sh

if [ ! -d $workdir ]; then
    mkdir -p $workdir
    pushd $workdir
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
    --authors-file=users.txt \
    --no-metadata \
    --prefix "" \
    -s $git_dir

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

# find all files that are large
# git rev-list --objects --all | sort -k 2 > allfileshas.txt;git gc && git verify-pack -v .git/objects/pack/pack-*.idx | egrep "^\w+ blob\W+[0-9]+ [0-9]+ [0-9]+$" | sort -k 3 -n -r > bigobjects.txt
# sort by largest
# for SHA in `cut -f 1 -d\  < bigobjects.txt`; do echo $(grep $SHA bigobjects.txt) $(grep $SHA allfileshas.txt) | awk '{print$1,$3,$7}' >> bigtosmall.txt; done
# purge large files
# git filter-branch -f --prune-empty --index-filter 'git rm -rf --cached --ignore-unmatch MY-BIG-DIRECTORY-OR-FILE' --tag-name-filter cat -- --all


#
# Create revision-hash lookup table
#
wget https://github.com/poseidix/TRAC-SVN-to-GIT-migration/blob/master/createLookupTable.sh
chmod 755 createLookupTable.sh
./createLookupTable.sh > $workdir/rev-lookuptable.txt

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


