SELECT m.name
FROM members m JOIN loans l ON l.member_id = m.member_id;
