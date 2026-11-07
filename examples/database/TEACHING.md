# Teaching notes and reference outcomes

All tasks use the declared model in data/README.md. A name is not a key merely
because the four displayed names happen to differ. Book rows identify physical
copies, and historical loans can refer to a copy more than once.

## SQL

| Example | Expected rows | Useful misconception |
| --- | --- | --- |
| [Filter](answers/sql-filter.sql) | Database Basics; Practical SQL | Returning every title ignores the predicate |
| [Join](answers/sql-join.sql) | Ada / Database Basics; Ben / Graph Stories; Cara / Network Notes | Equality to NULL is not IS NULL |
| [Count](answers/sql-count.sql) | Ada 1; Ben 1; Cara 1; Dan 0 | COUNT(*) counts the NULL-extended row |
| [Available books](answers/sql-available.sql) | Practical SQL | A closed historical loan does not exclude a simultaneous open loan from consideration |
| [Bags](answers/sql-bags.sql) | Ada; Ada; Ben; Ben; Cara | DISTINCT changes the requested multiplicity |

The query checker ignores row order and output-column labels, but respects column
order, values and duplicate multiplicity. The reference queries are examples of
valid solutions; learners can use other SQL formulations.

For the count task, ask learners to predict what happens after adding a member
with only returned loans. A filter in WHERE may drop this member entirely.
Putting the open-loan condition in the join predicate preserves them. Then add
another member named Ada: grouping only by name incorrectly combines different
members. The executable checker includes both cases.

SQL submissions are read-only. The seed creates tables once when the activity
loads; a student's DROP/INSERT/UPDATE is refused and does not alter later work.

## RDF, SPARQL and Turtle

| Example | Expected result |
| --- | --- |
| [SELECT](answers/sparql-select.rq) | The same three name/title pairs as the SQL join |
| [ASK](answers/sparql-ask.rq) | false: no open-loan pattern for Dan in this supplied graph |
| [CONSTRUCT](answers/sparql-construct.rq) | ada borrows b101; ben borrows b102; cara borrows b104 |
| [One Turtle fact](answers/turtle-one.ttl) | ben borrows b102 |
| [Turtle shorthand](answers/turtle-many.ttl) | ada hasBorrowed b101; ada hasBorrowed b103 |

Identifiers in this table are abbreviated with the seed's default prefix.
SPARQL SELECT returns RDF bindings, ASK a boolean, and CONSTRUCT a graph. The
constructed graph is an output; it does not modify the seed.

ASK false describes pattern matching in the supplied graph. It does not establish
that a fact is false in every larger graph or in the real world. The explicit
open/closed status in this seed avoids treating a missing return-date assertion
as evidence that a loan is open.

Turtle is data syntax. A resource such as :b102 differs from the string
"Graph Stories". Full IRIs and prefixed names can identify the same resource.
Comma shorthand and separate statements can express the same graph. Repeating
an identical triple does not duplicate a graph fact. These examples avoid blank
nodes and do not claim support for general graph-isomorphism reasoning.

## Discussion activities and quizzes

- **ER sketch:** require Member, Book and Loan with identifiers. Each Loan refers
  to exactly one Member and one Book; each parent participates in zero to many
  historical loans. Accept different explained notations. Discuss the drawing
  in the gallery; do not call the sketch interface an ER correctness checker.
- **Reviewed graph:** approve the three active borrowing facts. It is a graph of
  contributed labels, not a Turtle parser or an update to the RDF seed.
- **Classification graph:** Database Basics and Practical SQL point to databases;
  Graph Stories to graphs; Network Notes to networks. Two distinct participants
  must support an edge when Minimum is two.
- **Key/constraint questions:** member_id is the key; loans reference existing
  members. Dan demonstrates optional borrowing. Names are not unique.
- **True/false, numeric and text:** false; three; DISTINCT.
- **Ordering:** FROM/JOIN, WHERE, GROUP BY, HAVING, SELECT, ORDER BY. This is a
  conceptual reasoning order and does not prescribe optimizer execution.
- **Word cloud:** distinguish entity types Member/Book/Loan from Ada or title.
- **Explanation list:** a retained join row is not a real loan; COUNT(*) counts
  it, while COUNT(loan_id) ignores its NULL. Ask for a repair.
- **Poll:** no correct answer. The instructor decides how to act on preferences.

## Transaction preview

Each of two transactions reads 100 and later writes its remembered value plus
ten. Both write 110, so the final value is 110 rather than the serial result 120.
This is a lost update. The slide is a static discussion example. A future plugin
will add prediction, execution tracing, conflict graphs and schedule repair.
