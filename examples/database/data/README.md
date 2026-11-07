# Library data

All people and records are fictional. Each book row represents a physical copy;
historical loans can refer to that copy again. Checkout dates are omitted. At
most one loan per copy is open in this snapshot. The supplied SQL DDL does not
claim to enforce that cross-row rule.

Primary keys identify members, books and loans. Names are not unique. Each loan
has a non-null reference to an existing member and book. Members and books may
have no loans. In this model a null returned_on means an open loan.

The RDF seed represents the same snapshot with explicit :open/:closed status,
and a return-date literal for closed loans. Missing assertions are not themselves
assertions of falsehood. The example.org namespace needs no network access.

Shared class contributions do not modify either seed. Turtle activities use the
seed's prefixes but compare the submitted graph separately.
