#!/bin/bash

# 
# Take a copy of the PgSQL database from OSGeo
#
createdb trac_postgis
ssh -C pramsey@trac.osgeo.org \
	"pg_dump -U postgres --no-owner trac_postgis" \
	| psql trac_postgis


