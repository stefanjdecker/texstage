-- SPDX-License-Identifier: Apache-2.0
-- Synthetic data. Each book row is one physical copy.
PRAGMA foreign_keys = ON;
CREATE TABLE members (member_id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE books (book_id INTEGER PRIMARY KEY, title TEXT NOT NULL, topic TEXT NOT NULL);
CREATE TABLE loans (
  loan_id INTEGER PRIMARY KEY,
  member_id INTEGER NOT NULL REFERENCES members(member_id),
  book_id INTEGER NOT NULL REFERENCES books(book_id),
  returned_on TEXT
);
INSERT INTO members VALUES (1,'Ada'),(2,'Ben'),(3,'Cara'),(4,'Dan');
INSERT INTO books VALUES
  (101,'Database Basics','databases'), (102,'Graph Stories','graphs'),
  (103,'Practical SQL','databases'), (104,'Network Notes','networks');
INSERT INTO loans VALUES
  (201,1,101,NULL), (202,2,102,NULL), (203,1,103,'2026-10-01'),
  (204,3,104,NULL), (205,2,101,'2026-10-02');
