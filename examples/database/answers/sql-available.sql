SELECT b.title FROM books b
WHERE NOT EXISTS (
  SELECT 1 FROM loans l
  WHERE l.book_id = b.book_id
    AND l.returned_on IS NULL
);
