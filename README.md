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
