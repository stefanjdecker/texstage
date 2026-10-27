# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The engines of live activities (docs/live-activities-design.md, section 8.3), by the name a deck
gives (engine=): the half of their table that the build and the server need - the files a seed may
be, with the media type the server gives each (the first is the bundle's), the tokens every
activity's bar offers, what a phone's keyboard hides, and what a student's text is called in the
server's messages. The other half, which runs them in the presenter's browser, is
web/engines/index.js.

    sparql   queries over the seed's graph (Turtle)
    sql      queries over the seed's tables (SQL statements)
    turtle   a graph written in Turtle; of the seed (Turtle) only its @base and @prefix lines count (8.9)"""

ENGINES = {
    "sparql": {"seed": {".ttl": "text/turtle; charset=utf-8"}, "tokens": ["{", "}", "?", ".", ";", ":"],
               "text": "a query"},
    "sql": {"seed": {".sql": "application/sql"}, "tokens": ["*", ",", "(", ")", "=", "'", "."], "text": "a query"},
    "turtle": {"seed": {".ttl": "text/turtle; charset=utf-8"},
               "tokens": [":", ".", ";", ",", '"', "@", "^^", "<", ">", "_:", "[", "]", "(", ")"],
               "text": "a Turtle text"},
}
