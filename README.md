# PostGIS Github Migration

This repository captures the steps and scripts them so that a clean migration can be run in a few hours, if and when a migration is ever approved by the PSC.

The migration will encompass the following steps:

* Create blank Github repository/project
* Convert SVN to git and push to Github
  * retain branch and tag information
* Convert trac tickets to github format
  * retain revision links (r1234) as hash links
  * map ticket references (#1234) to github ticket references
  * map trac users to github users
  * map milestones and versions to github tags


### 01-svn-to-git.sh

This reads an SVN repository into a Git repository and then runs some specific commands to get rid of un-wanted PostGIS branches and tags. When complete it generates a text file of revision/hash references to that the Trac tickets can be re-written when they are migrated.

### 02-trac-to-local.sh 

Quick and dirty command to pipe the PostgreSQL trac database into a local instance for easy querying.

### 03-tract-to-gh.sh

Really just runs the `trac2github.py` script, where all the logic is.

The `CONFIGURATION` section needs extensive customization for any particular repo load.

* Load tags and milestones from repo.
* Convert trac wiki syntax into markdown.
* Add comments and attachments.
* Use the new Github "beta" [Import Issue API](https://gist.github.com/jonmagic/5282384165e0f86ef105) to support post-dated comments and issues.

Note that the Import Issue API runs asyncronously, so to find out the status of any given import, a secont REST query is required, for example:

    curl -X GET -H "Authorization: token xxxxxxxx" \
      -H "Accept: application/vnd.github.golden-comet-preview+json" \
      https://api.github.com/repos/pramsey/postgis-gh/import/issues/1420269

Frequently a import will be accepted but the content will be rejected later because:

* Issue assignee not in the repository organization (cannot assign issues to people you don't "know", as it were)
* Milestone unknown, label unknown.

Unfortunately the ownership of all issues and comments will be that of the user doing the loading, usually a synthetic user, like the @mapserver-bot.
