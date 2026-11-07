SELECT m.name, COUNT(l.loan_id) AS active_loans
FROM members m
LEFT JOIN loans l ON l.member_id = m.member_id
  AND l.returned_on IS NULL
GROUP BY m.member_id, m.name;
