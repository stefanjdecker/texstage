# Activity coverage

The full deck includes every currently available built-in database engine,
both shared-graph input shapes, and all nine quiz types in a database context.
It is a starting collection of exercises, not a complete database curriculum.

| Activity ID | Interaction | Source | What students do |
| --- | --- | --- | --- |
| primary-key | Single choice | [04](slides/04-primary-key.tex) | Use a declared primary-key constraint |
| constraints | Multiple choice | [05](slides/05-constraints.tex) | Distinguish keys, references and optional borrowing |
| er-sketch | Sketch | [06](slides/06-er-sketch.tex) | Model Loan as an entity with cardinalities |
| sql-filter | SQL | [08](slides/08-sql-filter.tex) | Select book titles by topic |
| sql-join | SQL | [09](slides/09-sql-join.tex) | Join three tables and test IS NULL |
| sql-count | SQL | [10](slides/10-sql-count.tex) | Preserve members with zero open loans |
| sql-available | SQL | [12](slides/12-sql-available.tex) | Find absence with an anti-join |
| sql-bags | SQL | [13](slides/13-sql-bags.tex) | Preserve duplicate result rows |
| duplicates | True/false | [14](slides/14-duplicates.tex) | Explain the effect of DISTINCT |
| active-total | Numeric slider | [15](slides/15-active-total.tex) | Count open loans |
| distinct-keyword | Text answer | [16](slides/16-distinct.tex) | Name DISTINCT |
| query-order | Ordering | [17](slides/17-query-order.tex) | Separate logical clause order from a physical plan |
| crowd-facts | Three-field graph | [19](slides/19-crowd-facts.tex) | Submit and review labeled borrowing edges |
| crowd-pairs | Two-field graph | [20](slides/20-crowd-pairs.tex) | Classify books with two-person agreement |
| sparql-select | SPARQL SELECT | [21](slides/21-sparql-select.tex) | Join graph patterns into bindings |
| sparql-ask | SPARQL ASK | [22](slides/22-sparql-ask.tex) | Ask about a pattern in the supplied graph |
| sparql-construct | SPARQL CONSTRUCT | [23](slides/23-sparql-construct.tex) | Derive borrowing triples |
| turtle-one | Turtle | [24](slides/24-turtle-one.tex) | Use a resource, not its title literal |
| turtle-many | Turtle | [25](slides/25-turtle-many.tex) | Express two triples using shorthand |
| entity-cloud | Open word cloud | [26](slides/26-word-cloud.tex) | Distinguish types, instances and attributes |
| explain-zero | Open response list | [27](slides/27-explain.tex) | Explain a NULL-extended join row |
| topic-poll | Multiple-selection poll | [28](slides/28-topic-poll.tex) | Choose a topic to revisit |

The [transaction preview](slides/29-transaction-preview.tex) demonstrates a lost
update through discussion. The planned transaction engine and schedule editor
will extend this collection after their implementation and conformance checks.
There is currently no automatic grading of ER diagrams or arbitrary prose.

Prerequisite slides introduce the data, join instructions, SQL syntax and RDF
vocabulary. [Slide 11](slides/11-zero-debrief.tex) explains the zero-count trap;
[slide 30](slides/30-takeaways.tex) distinguishes an observed reference match
from a proof of equivalence.
