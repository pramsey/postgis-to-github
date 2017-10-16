import sys
import re
import csv
import ConfigParser
import github
import logging
import argparse
from string import replace
import os
from os.path import basename, splitext, join, isfile
import StringIO
import datetime
import psycopg2
from psycopg2.extras import RealDictConnection, RealDictCursor, Json
from psycopg2.extensions import register_type
import requests
import pprint

###############################################################################
# CONFIGURATION
###############################################################################

github_user = "pramsey"
github_password = os.environ["GITHUB_TOKEN"]
github_repo = "postgistest"
github_default_label_color = 'eeeeee'

# svnuser:githubuser
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

# from trac field/value to github label name
traclabelmap = {
    "type":{
        "patch":"Patch",
        "enhancement":"Enhancement",
        "task":"Task",
        "defect":"Defect"
        },
    "component":{
        "raster":"Raster",
        "topology":"Topology",
        "build/upgrade/install":"Build/Install",
        "sfcgal":"SFCGAL",
        "management":"Management",
        "buildbots":"BuildBots",
        "java":"Java",
        "postgis":"Core",
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
# https://trac.osgeo.org/postgis/attachment/ticket/1666/make_dist_pre2quiet.2.patch
attachment_url_prefix = "https://trac.osgeo.org/postgis/attachment/ticket/"


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
    # validate_usermap(hub)
    
    for issue in get_issues(conn, repo, first_id=1501, limit=1):
        logger.info("got issue...")
        
    # For each ticket
    # 
    # for ticket in get_issues(conn, first_ticket=1800, max_tickets=10):
    #     print "======== %s" % ticket.get("id")
    #     print ticket.get("summary")
    #     print "----"
    #     print md_from_trac(ticket.get("description"))
    #     print "----"
    #     for comment in get_trac_comments(conn, ticket.get("id")):
    #         print md_from_trac(comment.get("comment"))


###############################################################################

def get_issues(conn, repo, first_id=1, limit=10):
    
    for ticket in get_trac_tickets(conn, first_ticket=first_id, max_tickets=limit):
        issue = {}
        issue["title"] = ticket["summary"]
        issue["body"] = format_body(ticket)
        issue["created_at"] = ticket["createtime"].isoformat()
        issue["updated_at"] = ticket["changetime"].isoformat()
        issue["assignee"] = trac_user_get_github_user(ticket["owner"])
        issue["closed"] = (ticket["status"] == 'closed')
        
        # Take labels from trac ticket state
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
            issue["milestone"] = milestone.title
        
        # Get comments and attachments in order and add to 
        # the issue
        issue["comments"] = []
        for state in get_trac_comments_and_attachments(conn, ticket["id"]):
            comment = {}
            comment["created_at"] = state["createtime"].isoformat()
            # Comment
            if state["type"] == 'comment':
                comment["body"] = format_comment(state)
            # Attachment
            else:
                comment["body"] = format_attachment(state)
            issue["comments"].append(comment)

        # Log result
        logger.info("Formatted Ticket/Issue #%s" % ticket["id"])
        logger.debug(pprint.pformat(issue))
        yield issue
                


def format_body(ticket):
    md = "**Reported by: %s**\n\n" % trac_user_get_github_user(ticket["reporter"], fallback_to_trac=True)
    md += md_from_trac(ticket["description"])
    return md
        
def format_comment(state):
    md = "**Author: %s**\n\n" % trac_user_get_github_user(state["author"], fallback_to_trac=True)
    md += md_from_trac(state["description"])
    return md

def format_attachment(state):    
    md = "**Attachment: %s**\n\n" % (attachment_url_prefix + state["filename"])
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
        "Authorization": github_password, 
        "Content-Type": "application/json",
        "Accept": "vnd.github.golden-comet-preview+json"
        }
    r = requests.post("http://httpbin.org/post", data=issue_dict)
    if args.debug:
        print(r.text)
    
###############################################################################

def trac_user_get_github_user(trac_user, fallback_to_trac=False):
    if usermap.get(trac_user):
        return usermap.get(trac_user)
    elif fallback_to_trac:
        return trac_user
    else:
        return github_user

###############################################################################

def trac_label_get_github_label(trac_key, trac_value, repo):
    
    # Do we have a configuration for this particular
    # trac key/value combination?
    if not traclabelmap.get(trac_key):
        return None
    elif not traclabelmap[trac_key].get(trac_value):
        return None
    
    labelcolor = traclabelmap[trac_key][trac_value].split(';')
    label = labelcolor[0]
    if len(labelcolor) > 1:
        color = labelcolor[1]
    else:
        color = github_default_label_color
    
    # Yes, we already have this label set up, 
    # so just return the github label object.
    if labelmap.get(label) or labelmap.get(label.lower()):
        return labelmap.get(label)
    
    logger.info("Creating new github label: %s" % label)
    # We have a configuration but it doesn't 
    # exist in github yet, so create it there.
    return repo.create_label(label, color)


def trac_milestone_get_github_milestone(trac_milestone, conn, repo):
    if milestonemap.get(trac_milestone):
        return milestonemap.get(trac_milestone)
        
    ms = get_trac_milestone(conn, trac_milestone)
    if not ms:
        raise Exception("milestone '%s' not found in trac database" % trac_milestone)
    
    logger.debug(pprint.pformat(ms))
    if ms["due"]:
        return repo.create_milestone(title=ms["name"], state=ms["state"], due_on=ms["due"])
    else:
        return repo.create_milestone(title=ms["name"], state=ms["state"])


###############################################################################

def load_revmap(revmapfile):
    d = dict()
    logger.info('loading revmap from %s', revmapfile)
    with open(revmapfile) as f:
        for r in csv.reader(f, delimiter='\t'):
            d[r[0]] = r[1]
    logger.info('loaded %d revmappings', len(d))
    return d

###############################################################################

def load_labelmap(repo):
    l = dict()
    for label in repo.get_labels():
        logger.debug('found label "%s"', label.name)
        l[label.name] = label
    logger.info('found %d labels', len(l))
    return l

def load_milestonemap(repo):
    m = dict()
    for state in ['open', 'closed']:
        for milestone in repo.get_milestones(state=state):
            logger.debug('found milestone "%s"', milestone.title)
            m[milestone.title] = milestone
    logger.info('found %d milestones', len(m))
    return m

###############################################################################

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

def md_from_trac(s):
    
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
    
    # Leading/trailing space
    s = re.sub("^\s*", "", s)
    s = re.sub("\s$", "", s)
    
    # Revision numbers
    p = re.compile('(\s)r(\d+)$')
    s = p.sub(md_from_trac_revision_last, s)
    p = re.compile('^r(\d+)(\W)')
    s = p.sub(md_from_trac_revision_first, s)
    p = re.compile('(\s)r(\d+)(\W)')
    s = p.sub(md_from_trac_revision, s)
    
    return s

###############################################################################

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
    
