## Vulnerability

**CWE-345: Insufficient Verification of Data Authenticity (Blast-RADIUS).** In `edumfa/lib/radiusserver.py`, `RADIUSServer.request` sends an Access-Request without explicitly adding a `Message-Authenticator` and treats a returned `Access-Accept` as sufficient to grant access. An on-path attacker who can forge an `Access-Accept` that passes the underlying client’s reply checks could cause a rejected login to be accepted.

```json
{"evidence":[{"file":"edumfa/lib/radiusserver.py","line":69,"quote":"    def request(config, user, password):"},{"file":"edumfa/lib/radiusserver.py","line":113,"quote":"        req = srv.CreateAuthPacket(code=pyrad.packet.AccessRequest,"},{"file":"edumfa/lib/radiusserver.py","line":118,"quote":"        req[\"User-Password\"] = req.PwCrypt(password)"},{"file":"edumfa/lib/radiusserver.py","line":120,"quote":"            response = srv.SendPacket(req)"},{"file":"edumfa/lib/radiusserver.py","line":122,"quote":"            if response.code == pyrad.packet.AccessAccept:"},{"file":"edumfa/lib/radiusserver.py","line":125,"quote":"                success = True"}]}
```

## Fix

Add a `Message-Authenticator` to outgoing requests. Before granting access, require exactly one correctly sized `Message-Authenticator` in the reply and verify it using the shared secret and the original request authenticator. Valid replies retain the existing success behavior; peers that omit the attribute now fail closed.

## Patch

```diff
--- a/edumfa/lib/radiusserver.py
+++ b/edumfa/lib/radiusserver.py
@@ -116,10 +116,20 @@
 
         # PwCrypt encodes unicode strings to UTF-8
         req["User-Password"] = req.PwCrypt(password)
+        req.add_message_authenticator()
         try:
             response = srv.SendPacket(req)
 
             if response.code == pyrad.packet.AccessAccept:
+                authenticators = response.get(80, ())  # Message-Authenticator
+                if (len(authenticators) != 1
+                        or len(authenticators[0]) != 16
+                        or not response.verify_message_authenticator(
+                            secret=req.secret,
+                            original_authenticator=req.authenticator)):
+                    log.warning("Radiusserver %s returned an Access-Accept without "
+                                "a valid Message-Authenticator." % config.server)
+                    return False
                 log.info("Radiusserver %s granted "
                          "access to user %s." % (config.server, user))
                 success = True
```

## Self-assessment

```json
{"claim":1,"confidence":0.87}
```
