SELECT m.name, b.title
FROM loans l
JOIN members m ON m.member_id = l.member_id
JOIN books b ON b.book_id = l.book_id
WHERE l.returned_on IS NULL;
