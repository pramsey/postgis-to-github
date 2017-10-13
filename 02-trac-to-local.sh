#!/bin/bash

# 
# Take a copy of the PgSQL database from OSGeo
#
dropdb --if-exists trac_postgis
createdb trac_postgis
ssh -C pramsey@trac.osgeo.org \
	"pg_dump -U postgres --no-owner trac_postgis" \
	| psql trac_postgis


DROP TABLE IF EXISTS attachments_dump;
CREATE TABLE attachments_dump AS
SELECT 
  id, 
  filename, 
  time / 1000000 as PosixTime,
  author 
from attachment
order by id asc;

\copy attachment_dump TO 'attachments.csv' with (format csv)

DROP TABLE IF EXISTS comments_dump;
CREATE TABLE comments_dump AS
select
    ticket,
    time / 1000000 as PosixTime,
    author,
    newvalue
from
    ticket_change
where
    field = 'comment'
    and newvalue <> ''
order
    by ticket, time;
	
\copy comments_dump TO 'comments.csv' with (format csv)
	
DROP TABLE IF EXISTS tickets_dump;
CREATE TABLE tickets_dump AS
select
    id,
    type,
    owner,
    reporter,
    milestone,
    status,
    resolution,
    summary,
    description,
    time / 1000000 as PosixTime,
    changetime / 1000000 as ModifiedTime
from
    ticket
order
    by id;
	
\copy tickets_dump TO 'tickets.csv' with (format csv)
	