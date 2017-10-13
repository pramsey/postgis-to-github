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

###############################################################################
# CONFIGURATION
###############################################################################

github_user = "pramsey"
github_password = os.environ["GITHUB_TOKEN"]
github_repo = "postgistest"

# svnuser:githubuser
usermap = {
    "pramsey":"pramsey",
    "robe":"robe2",
    "strk":"strk",
    "mcayland":"mcayland",
    "pracine":"pierre-racine", 
    "chodgson":"chrishodgson", 
    "colivier":"ocourtin", 
    "dblasby":"DBlasby", 
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
        "patch":"patch",
        "enhancement":"enhancement",
        "task":"task",
        "defect":"defect"
        },
    "component":{
        "raster":"raster",
        "topology":"topology",
        "build/upgrade/install":"build/install",
        "sfcgal":"sfcgal",
        "management":"management",
        "buildbots":"buildbots",
        "java":"java",
        "postgis":"postgis",
        "website":"website",
        "documentation":"documentation",
        "liblwgeom":"liblwgeom",
        "loader/dumper":"loader/dumper",
        "pagc_address_parser":"pagc address parser",
        "tiger geocoder":"tiger geocoder"
        },
    "priority":{
        "priority=blocker":"priority:blocker",
        "critical":"high",
        "high":"high",
        "medium":"low",
        "low":"low"
        },
    "resolution":{
        "wontfix":"wontfix",
        "duplicate":"duplicate",
        "invalid":"invalid",
        "worksforme":"worksforme"
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
    validate_usermap(hub)
    
    # For each ticket
    # 
    # for ticket in get_tickets(conn, first_ticket=1800, max_tickets=10):
    #     print "======== %s" % ticket.get("id")
    #     print ticket.get("summary")
    #     print "----"
    #     print md_from_trac(ticket.get("description"))
    #     print "----"
    #     for comment in get_comments(conn, ticket.get("id")):
    #         print md_from_trac(comment.get("comment"))


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
        h = revmap.get(m.group(1))
        if h:
            return h + m.group(2)
    
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
    p = re.compile('r(\d+)(\W)')
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

def get_tickets(conn, first_ticket=None, max_tickets=None):
    sql = """SELECT id, type, owner, reporter, milestone, status, resolution,
                summary, description, time / 1000000 as posixtime, 
                changetime / 1000000 as modifiedtime
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

def get_comments(conn, ticket):
    sql = """SELECT ticket, time / 1000000 as posixtime, author, newvalue AS comment
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

###############################################################################

def get_attachments(conn, ticket):
    sql = """SELECT id, filename, time / 1000000 as posixtime, author 
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
    
