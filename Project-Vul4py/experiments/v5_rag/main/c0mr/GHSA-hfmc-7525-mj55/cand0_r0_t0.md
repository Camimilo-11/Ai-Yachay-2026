## Vulnerability

**Type:** Improper authentication (CWE-287). The certificate principal check against the requested username is silently disabled.

**Location:** `asyncssh/connection.py`, `SSHServerConnection._validate_openssh_certificate`, around lines 2194-2198. The hinted range 2194-2200 matches this block.

**Root cause:** When the matching `authorized_keys` entry contains a `principals` option, the code overwrites the authenticating `username` with an empty string. The certificate is then validated with that empty string as the principal, so the certificate's principal list is no longer checked against the user who is logging in. The `authorized_keys` lookup earlier in the function passes `cert.principals` to the authorized-keys validator, but that only checks the `principals` option against the certificate. It does not tie the certificate to the requested username.

**Exploit:** An attacker who holds a user certificate signed by a trusted CA, and whose principal list intersects a `principals=` list in `authorized_keys`, can request login as any other username. The certificate's principal does not need to match that username.

I cannot see `asyncssh/public_key.py`, so I cannot confirm how `SSHOpenSSHCertificate.validate` treats an empty principal. The exploit path above assumes an empty principal skips the principal-name check, which is what the `username = ''` workaround implies. The patch below is consistent with that assumption and is the fix I would expect.

```json
{"evidence": [{"file": "asyncssh/connection.py", "line": 2194, "quote": "if self.get_key_option('principals'):"}, {"file": "asyncssh/connection.py", "line": 2195, "quote": "username = ''"}, {"file": "asyncssh/connection.py", "line": 2198, "quote": "cert.validate(CERT_TYPE_USER, username)"}]}
```

## Fix

The patch removes the `if self.get_key_option('principals'): username = ''` override. The certificate is now always validated against the real username, so a certificate must list the user it is authenticating as, in addition to satisfying any `principals=` restriction. Authorized-keys checks, the `cert.validate` call, and all other paths stay unchanged. Behaviour changes only for entries that use `principals=` with a username not listed in the certificate, and those logins should be rejected.

I left the X.509 path (`_validate_x509_certificate_chain`) alone. It has a similar `username = ''` override, but its line numbers are not in the hinted range, so I did not patch it without seeing the exact lines. It may need the same change.

## Patch

```diff
--- a/asyncssh/connection.py
+++ b/asyncssh/connection.py
@@ -2191,9 +2191,6 @@
 
         self._key_options = options
 
-        if self.get_key_option('principals'):
-            username = ''
-
         try:
             cert.validate(CERT_TYPE_USER, username)
         except ValueError:
```

## Self-assessment

```json
{"claim": 1, "confidence": 0.45}
```
