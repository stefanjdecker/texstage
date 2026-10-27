# Security and sensitive reports

This is an unpublished development candidate. No supported release or response
time commitment has been established. Before publication, the maintainer must
enable GitHub private vulnerability reporting or publish a monitored private
contact here, and identify supported versions in this document.

When private reporting is enabled, use the repository's **Security → Report a
vulnerability** action. Do not put exploit details, presenter credentials,
student responses or private course files in a public issue. Include the affected
version, a minimal synthetic reproduction and the expected security boundary.

LaTeX sources and notebooks are executable inputs. Build only material you trust
or use an appropriately isolated environment. Notebook execution runs the
notebook's code. Do not treat no-shell-escape as a complete TeX sandbox.

For texstage deployments, keep presenter keys and server data out of Git and
student-facing downloads. Live PowerPoint decks may carry presenter credentials;
distribute the handout or solutions export to students. Use HTTPS for remote
hosting. Only trust forwarded headers from a proxy under your control. Back up
server data and test recovery before replacing a live deployment.

A passing CI run does not establish a security audit. Dependency hashes establish
artifact integrity, not the absence of vulnerabilities.
