import sys
import re
import csv
import github
import logging
import argparse
from string import replace
import os
from os.path import basename, splitext, join, isfile
import StringIO
import datetime
import psycopg2
import json
from psycopg2.extras import RealDictConnection, RealDictCursor, Json
from psycopg2.extensions import register_type
import requests
import pprint

###############################################################################
# CONFIGURATION
###############################################################################

github_user = "pramsey"
github_password = os.environ["GITHUB_TOKEN"]
github_repo = "postgis-gh"
github_default_label_color = 'eeeeee'

#
# svnuser:githubuser
#
usermap = {
    "pramsey":"pramsey",
    "robe":"robe2",
    "strk":"strk",
    "mcayland":"mcayland",
    "pracine":"pierre-racine", 
    "chodgson":"chrishodgson", 
    "colivier":"ocourtin", 
    "dblasby":"dblasby", 
    "devrim":"devrimgunduz", 
    "dustymugs":"dustymugs", 
    "dzwarg":"dzwarg", 
    "jeffloun":"jeffloun", 
    "jorgearevalo":"jorgeas80", 
    "mcayland":"mcayland", 
    "mleslie":"markles", 
    "mloskot":"mloskot", 
    "mschaber":"markusschaber", 
    "nicklas":"nicklasaven", 
    "warmerdam":"warmerdam", 
    "xingkth":"xinglin", 
    "snowman":"sfrost", 
    "woodbri":"woodbri", 
    "dbaston":"dbaston", 
    "bjornharrtell":"bjornharrtell"
    }

#
# Maps from trac field/value to github label name.
#
# Only map those combinations that really make sense. You
# probably don't want to map a label that will end up on 
# 95% of the tickets, since that doesn't provide any
# useful information.
#
# You can add colors after each GH tag name, see the hex
# colors below in the "priority" section. Using multi-word
# labels might be a bad idea, because they are harder to 
# type into the advanced search box on GH, but it might 
# be good because they are easier to read, and people use
# the dropdown lists a lot.
#
traclabelmap = {
    "type":{
        "patch":"Patch",
        "enhancement":"Enhancement",
        "task":"Task",
        "defect":"Bug"
        },
    "component":{
        "raster":"Raster",
        "topology":"Topology",
        "build/upgrade/install":"Build/Install",
        "sfcgal":"SFCGAL",
        "management":"Management",
        "buildbots":"BuildBots",
        "java":"Java",
        "website":"Website",
        "documentation":"Documentation",
        "liblwgeom":"liblwgeom",
        "loader/dumper":"Loader/Dumper",
        "pagc_address_parser":"Address Parser",
        "tiger geocoder":"Tiger Geocoder"
        },
    "priority":{
        "blocker":"Blocker;ff0000",
        "critical":"High Priority;ee8888",
        "high":"High Priority;ee6666"
        },
    "resolution":{
        "wontfix":"Won't Fix",
        "duplicate":"Duplicate",
        "invalid":"Invalid",
        "worksforme":"Works For Me"
        }
    }


revmapfile = "/Users/pramsey/Code/postgis-to-github/work/rev-lookup.txt"

db = {
    "dbname":"trac_postgis",
    "cursor_factory":RealDictCursor,
    "port":5432,
    "host":"localhost",
    "user":"pramsey",
    "password":"xxxxxxx"
    }

# For example
# https://trac.osgeo.org/postgis/raw-attachment/ticket/1666/make_dist_pre2quiet.2.patch
attachment_url_tmpl = "https://trac.osgeo.org/postgis/raw-attachment/ticket/%(ticket)s/%(filename)s"
ticket_url_prefix = "https://trac.osgeo.org/postgis/ticket/"

###############################################################################
# GLOBALS
###############################################################################

revmap = {}  # from svn revision number to git hash
labelmap = {}  # from label name to github label
milestonemap = {}  # from milestone name to github milestone
ticketmap = {}  # from trac ticket number to github ticket number


###############################################################################

def main():

    global revmap
    global labelmap
    global milestonemap

    hub = github.Github(github_user, github_password)
    repo = hub.get_user().get_repo(github_repo)
    
    conn = get_pgsql_connection(db)
    revmap = load_revmap(revmapfile)
    labelmap = load_labelmap(repo)
    milestonemap = load_milestonemap(repo)
    validate_usermap(hub)
    
    for issue in get_issues(conn, repo, first_id=1000, limit=1):
        # Only turn this on when you're ready to rock
        # In order to maintain exact ticket/issue number correspondance
        # you cannot create the same issue twice, ever. Otherwise 
        # delete the repo and start again, sorry.
        r = github_create_issue(issue)
        logger.info("id:%(id)s status:%(status)s url:%(url)s" % r)
        
        
        
        
###############################################################################

def get_issues(conn, repo, first_id=1, limit=1):
    
    for ticket in get_trac_tickets(conn, first_ticket=first_id, max_tickets=limit):
        issue = {}
        issue["title"] = ticket["summary"]
        issue["body"] = format_body(ticket)
        issue["created_at"] = ticket["createtime"].isoformat()
        issue["updated_at"] = ticket["changetime"].isoformat()
        issue["closed"] = (ticket["status"] == 'closed')
        
        # Assignee must me a member of the organization or by an 
        # invited collaborator on the repository. 
        # issue["assignee"] = trac_user_get_github_user(ticket["owner"])
        
        # Take labels from trac ticket state
        # Brittleness: Github checks label existence based on 
        # case-insensitive test, but our map is case-sensitive.
        labels = []
        for k in ["type", "component", "priority", "resolution"]:
            label = trac_label_get_github_label(k, ticket[k], repo)
            if label:
                labels.append(label.name)
        if labels:
            issue["labels"] = labels
        
        # Ensure milestone exists in github (already, or create it)
        # before applying to the issue
        milestone = trac_milestone_get_github_milestone(ticket["milestone"], conn, repo)
        if milestone:
            issue["milestone"] = milestone.number
        
        # Get comments and attachments in order and add to 
        # the issue
        comments = []
        for state in get_trac_comments_and_attachments(conn, ticket["id"]):
            comment = {}
            comment["created_at"] = state["createtime"].isoformat()
            # Comment
            if state["type"] == 'comment':
                comment["body"] = format_comment(state)
            # Attachment
            else:
                comment["body"] = format_attachment(state)
            comments.append(comment)

        # Compose into a github issue json
        gh = {"issue": issue, "comments": comments}

        # Log result
        logger.info("Formatted Ticket/Issue #%(id)s: %(summary)s" % ticket)
        logger.debug(json.dumps(gh))
        yield gh
                


def format_body(ticket):
    md = "**Reporter: %s**\n" % trac_user_get_github_user(ticket.get("reporter"), fallback_to_trac=True)
    md += "**Trac URL: %s**\n\n" % (ticket_url_prefix + str(ticket.get("id")))
    md += md_from_trac(ticket["description"])
    return md
        
def format_comment(state):
    md = "**Author: %s**\n\n" % trac_user_get_github_user(state["author"], fallback_to_trac=True)
    md += md_from_trac(state["description"])
    return md

def format_attachment(state):    
    md = "**Author: %s**\n" % trac_user_get_github_user(state["author"], fallback_to_trac=True)
    md += "**Attachment: %s**\n\n" % (attachment_url_tmpl % state)
    md += md_from_trac(state["description"])
    return md

###############################################################################
# Use the Github beta Issue import API
# https://gist.github.com/jonmagic/5282384165e0f86ef105
# {
#   "issue": {
#     "title": "Imported from some other system",
#     "body": "...",
#     "created_at": "2014-01-01T12:34:58Z",
#     "closed_at": "2014-01-02T12:24:56Z",
#     "updated_at": "2014-01-03T11:34:53Z",
#     "assignee": "jonmagic",
#     "milestone": 1,
#     "closed": true,
#     "labels": [
#       "bug",
#       "low"
#     ]
#   },
#   "comments": [
#     {
#       "created_at": "2014-01-02T12:34:56Z",
#       "body": "talk talk"
#     }
#   ]
# }
#
# curl -X POST -H "Authorization: token ${GITHUB_TOKEN}" \
#   -H "Accept: application/vnd.github.golden-comet-preview+json" \
#   -d '{"issue":...}' \
#   https://api.github.com/${GITHUB_REPO}/${GITHUB_USER}/foo/import/issues

def github_create_issue(issue_dict):
    
    url = "https://api.github.com/repos/%s/%s/import/issues" % (github_user, github_repo)
    logger.debug("POST to %s" % url)
    headers = {
        "Authorization": "token " + github_password, 
        "Content-Type": "application/json",
        "Accept": "application/vnd.github.golden-comet-preview+json"
        }
    r = requests.post(url, data=json.dumps(issue_dict), headers=headers)
    logger.debug(r.text)
    return json.loads(r.text)
    
###############################################################################
# For the text of comments, etc, we need a user name, and we'll use the 
# GH one if we can, but settle for the Trac one if we cannot.
#
def trac_user_get_github_user(trac_user, fallback_to_trac=False):
    if usermap.get(trac_user):
        return usermap.get(trac_user)
    elif fallback_to_trac:
        return trac_user
    else:
        return github_user

###############################################################################
# We only want to copy over label information we have pre-configured, this
# way we can drop information that will just add noise to the tickets.
# So we check if the requested metadata is in our map, and if it is, see if
# we have already cached the GH object for it, and if we have, return that.
#
def trac_label_get_github_label(trac_key, trac_value, repo):
    # so we can write back new labels
    global labelmap
    
    # Do we have a configuration for this particular
    # trac key/value combination?
    if not traclabelmap.get(trac_key):
        return None
    elif not traclabelmap[trac_key].get(trac_value):
        return None
    
    label_and_color = traclabelmap[trac_key][trac_value].split(';')
    label = label_and_color[0]
    if len(label_and_color) > 1:
        color = label_and_color[1]
    else:
        color = github_default_label_color
    
    # Yes, we already have this label set up, 
    # so just return the github label object.
    if labelmap.get(label):
        return labelmap.get(label)
    if labelmap.get(label.lower()):
        return labelmap.get(label.lower())
    
    
    logger.info("Creating new github label: %s" % label)
    # We have a configuration but it doesn't 
    # exist in github yet, so create it there.
    gh_label = repo.create_label(label, color)
    labelmap[label.lower()] = gh_label
    return gh_label


def trac_milestone_get_github_milestone(trac_milestone, conn, repo):
    # so we can write back new milestones
    global milestonemap
    
    # reflect None back
    if not trac_milestone:
        return None
    # return already-mapped milestone
    if milestonemap.get(trac_milestone):
        return milestonemap.get(trac_milestone)
    # read milestone info from database
    ms = get_trac_milestone(conn, trac_milestone)
    if not ms:
        return None

    # create github milestone using db info and 
    # store in global dictionary
    logger.debug(pprint.pformat(ms))
    due_on = ms.get("due") if ms.get("due") else github.GithubObject.NotSet
    title = ms.get("name")
    logger.info("Creating new github milestone: %s" % title)
    gh_milestone = repo.create_milestone(title=title, state=ms["state"], due_on=due_on)
    milestonemap[title] = gh_milestone
    return gh_milestone


###############################################################################
# Read the revision/hash map from the text file we generated during the 
# SVN->Git process
#
def load_revmap(revmapfile):
    d = dict()
    logger.info('loading revmap from %s', revmapfile)
    with open(revmapfile) as f:
        for r in csv.reader(f, delimiter='\t'):
            d[r[0]] = r[1]
    logger.info('loaded %d revmappings', len(d))
    return d

###############################################################################
# Read all the existing labels in our repo, so we don't try and
# re-create them.
#
def load_labelmap(repo):
    l = dict()
    for label in repo.get_labels():
        logger.debug('found label "%s"', label.name)
        l[label.name.lower()] = label
    logger.info('found %d labels', len(l))
    return l

###############################################################################
# Read all the existing milestones in our repo, so we don't try and
# re-create them.
#
def load_milestonemap(repo):
    m = dict()
    for state in ['open', 'closed']:
        for milestone in repo.get_milestones(state=state):
            logger.debug('found milestone "%s"', milestone.title)
            m[milestone.title] = milestone
    logger.info('found %d milestones', len(m))
    return m

###############################################################################
# Check that all the users in the usermap actually do exist in GH.
#
def validate_usermap(hub):
    for tu in usermap:
        gu = usermap[tu]
        logger.debug('checking trac => github map: %s => %s' % (tu, gu))
        try:
            hub.get_user(gu)
        except:
            raise Exception(u'Trac user "%s" must be mapped to an existing Github user instead of "%s"'
                    % (tu, gu))
                
###############################################################################
# Support functions for converting TracWiki syntax to Markdown
#
def md_from_trac_url(m):
    if m:
        return "[%s](%s)" % (m.group(2), m.group(1))
    else:
        return None

def md_from_trac_italic(m):
    if m:
        return "*%s*" % (m.group(1))
    else:
        return None

def md_from_trac_revision(m):
    if m:
        h = revmap.get(m.group(2))
        if h:
            return m.group(1)+h+m.group(3)
    return None

def md_from_trac_revision_first(m):
    if m:
        h = revmap.get(m.group(1))
        if h:
            return h+m.group(2)    
    return None

def md_from_trac_revision_last(m):
    if m:
        h = revmap.get(m.group(2))
        if h:
            return m.group(1)+h
    return None

def md_from_trac_revision_lone(m):
    if m:
        h = revmap.get(m.group(1))
        if h:
            return h
    return None

def md_from_trac_revision_wiki(m):
    if m:
        h = revmap.get(m.group(1))
        if h:
            return h
    return None

def md_from_trac(s):
    
    if not s:
        return ""
        
    # Simple tracwiki formatting
    s = replace(s, "'''", "**")
    s = replace(s, "''", "*")
    s = replace(s, "{{{", "```")
    s = replace(s, "}}}", "```")
    s = replace(s, "\r", "")
    
    # Old link style
    p = re.compile('\[(http\S+) (.*?)\]')
    s = p.sub(md_from_trac_url, s)
        
    # Old <i></i>
    p = re.compile('<i>(.*?)<\/i>', re.IGNORECASE)
    s = p.sub(md_from_trac_italic, s)
    
    # Headers
    s = re.sub("^=== ", "### ", s)
    s = re.sub("^== ", "## ", s)
    s = re.sub("^= ", "# ", s)
    
    # Leading/trailing space
    s = re.sub("^\s*", "", s)
    s = re.sub("\s*$", "", s)
    
    # Revision numbers
    p = re.compile('(\s)r(\d+)$')
    s = p.sub(md_from_trac_revision_last, s)
    p = re.compile('^r(\d+)(\W)')
    s = p.sub(md_from_trac_revision_first, s)
    p = re.compile('(\s)r(\d+)(\W)')
    s = p.sub(md_from_trac_revision, s)
    p = re.compile('^r(\d+)$')
    s = p.sub(md_from_trac_revision_lone, s)

    # [changeset:"15743" 15743]:
    p = re.compile('\[changeset:\"(\d+)\" (\d+)\]')
    s = p.sub(md_from_trac_revision_wiki, s)
    
    # Newlines
    s = replace(s, "[[br]]", "\n")
    s = replace(s, "\\\\", "\n")
    
    return s

###############################################################################
# Connect to the trac database. 
#
def get_pgsql_connection(config):
    assert logger
    keys = ["dbname", "host", "port", "user", "password", "cursor_factory"]
    pgdb = {k: config[k] for k in keys if k in config}
    logger.debug("connection parameters: %s" % str(pgdb))
    return psycopg2.connect(**pgdb)

###############################################################################

def get_trac_tickets(conn, first_ticket=None, max_tickets=None):
    sql = """SELECT id, type, owner, reporter, milestone, 
                status, resolution,
                summary, description, 
                component, priority,
                to_timestamp(time / 1000000) as createtime, 
                to_timestamp(changetime / 1000000) as changetime
            FROM ticket
            WHERE id >= %s
            ORDER BY id ASC
            """
    if not first_ticket:
        first_ticket = 1
    if max_tickets:
        sql += "LIMIT %s" % max_tickets
    
    with conn.cursor() as cur:
        cur.execute(sql, (first_ticket,))
        for r in cur:
            yield r

###############################################################################

def get_trac_comments(conn, ticket):
    sql = """SELECT ticket, 
                case when time > 0 then to_timestamp(time / 1000000) else NULL end as createtime, 
                author, newvalue AS comment
            FROM ticket_change
            WHERE field = 'comment'
            AND newvalue <> ''
            AND ticket = %s
            ORDER BY ticket ASC, time ASC
            """
    with conn.cursor() as cur:
        cur.execute(sql, (ticket,))
        for r in cur:
            yield r

def get_trac_milestone(conn, milestone):
    sql = """SELECT name,
            CASE WHEN due = 0 THEN NULL ELSE to_timestamp(due / 1000000) END AS due,
            CASE WHEN completed > 0 THEN 'closed' ELSE 'open' END AS state
            FROM milestone
            WHERE name = %s
            """
    with conn.cursor() as cur:
        cur.execute(sql, (milestone,))
        return cur.fetchone()

###############################################################################
# Unify the comments/attachments into one record set for easy creation of
# GitHub comment stream.
#
# {
#  "ticket": 1234, 
#  "type": "comment", # comment|attachment
#  "createtime": "2017-01-01 01:01:01",
#  "author": "pramsey",
#  "description": "some stuff",
#  "filename": ""
# }
#
def get_trac_comments_and_attachments(conn, ticket):
    sql = """SELECT 
                ticket, 
                'comment' AS type,
                case when time > 0 then to_timestamp(time / 1000000) else NULL end as createtime, 
                author, 
                newvalue AS description,
                NULL AS filename
            FROM ticket_change
            WHERE field = 'comment'
                AND newvalue <> ''
                AND ticket = %s
            UNION
            SELECT 
                id::integer AS ticket,
                'attachment' AS type,
                case when time > 0 then to_timestamp(time / 1000000) else NULL end as createtime, 
                author,
                description,
                filename
            FROM attachment
            WHERE id = %s::text
            AND type = 'ticket'
            ORDER BY ticket, createtime
            """
    with conn.cursor() as cur:
        cur.execute(sql, (ticket,ticket))
        for r in cur:
            yield r

###############################################################################        

def get_trac_attachments(conn, ticket):
    sql = """SELECT id, filename, 
            case when time > 0 then to_timestamp(time / 1000000) else NULL end as createtime, 
            author 
            FROM attachment
            WHERE id = %s
            ORDER BY id ASC, time ASC
            """

    with conn.cursor() as cur:
        cur.execute(sql, (ticket,))
        for r in cur:
            yield r

###############################################################################

def get_logger(log_level=logging.INFO):
    script = splitext(basename(__file__))[0]
    logger = logging.getLogger(script)
    logger.setLevel(log_level)
    info_handler = logging.StreamHandler()

    # create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    info_handler.setFormatter(formatter)
    info_handler.setLevel(log_level)

    # add the handlers to logger
    logger.addHandler(info_handler)
    return logger

###############################################################################

def get_arguments():    
    parser = argparse.ArgumentParser(description="Read Trac tickets from database and write to Github API")
    # parser.add_argument('--config', required=True, default=None, help='Configuration file')
    parser.add_argument('--really', action="store_const", const=True, default=False, help='Actually apply send data to GitHub')
    parser.add_argument('--debug', action="store_const", const=logging.DEBUG, default=logging.INFO)
    args = parser.parse_args()
    return args
    
################################################################################
# Set up global logger and config objects, then run main()
#
if __name__ == '__main__':
    args = get_arguments()
    logger = get_logger(log_level=args.debug)
    main()
    
