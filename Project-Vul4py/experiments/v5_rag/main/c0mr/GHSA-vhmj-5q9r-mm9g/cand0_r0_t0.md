## Vulnerability

**Type:** CWE-22 (Improper Limitation of a Pathname to a Restricted Directory). A user-supplied filesystem path is used without restriction, so the server can be made to read arbitrary local files.

**Location:**
- Source of the untrusted input: the `dictionary` parameter of the create endpoint (`edumfa/api/radiusserver.py`, lines 70-71) and of the test endpoint (lines 129-130). The value is taken from the request and passed on to `add_radius` (line 74) and `test_radius` (line 133).
- Dangerous use: `RADIUSServer.request` takes the stored or supplied value (`config.dictionary`) and passes it to `Dictionary(...)` (`edumfa/lib/radiusserver.py`, lines 93 and 105).

**Root cause:** The `dictionary` value has no validation at either the API layer or the library layer. It is used as-is as a path. `request` falls back to the `radius.dictfile` config value only when `config.dictionary` is empty. Since the value is persisted and reused on every RADIUS request, a bad path also affects later authentications, not just the test call.

**Exploit:** A user who has the `RADIUSSERVERWRITE` right can set `dictionary` to an absolute path such as `/etc/passwd` or to a traversal path. The value is stored and then used by pyrad's `Dictionary`, which is given a filesystem path. Pyrad is not among the shown files, so I cannot confirm from this code what pyrad does with the file, including whether parse errors reveal file content. The risk is that eduMFA reads files outside its configuration directory.

I have not located the exact upstream change. The localization hints mostly point to lines around the timeout, retries and audit calls, not directly to the dictionary handling. My identification rests on the dictionary lines quoted below, so my confidence is moderate.

```json
{"evidence": [
  {"file": "edumfa/api/radiusserver.py", "line": 70, "quote": "dictionary = getParam(param, \"dictionary\","},
  {"file": "edumfa/api/radiusserver.py", "line": 71, "quote": "default=\"/etc/edumfa/dictionary\")"},
  {"file": "edumfa/api/radiusserver.py", "line": 74, "quote": "description=description, dictionary=dictionary,"},
  {"file": "edumfa/api/radiusserver.py", "line": 129, "quote": "dictionary = getParam(param, \"dictionary\","},
  {"file": "edumfa/api/radiusserver.py", "line": 133, "quote": "dictionary=dictionary, retries=retries, timeout=timeout)"},
  {"file": "edumfa/lib/radiusserver.py", "line": 93, "quote": "r_dict = config.dictionary or get_from_config(\"radius.dictfile\","},
  {"file": "edumfa/lib/radiusserver.py", "line": 105, "quote": "dict=Dictionary(r_dict))"}
]}
```

## Fix

The patch adds a single sink-side check in `edumfa/lib/radiusserver.py`. A helper `_get_safe_dictionary_path` resolves the path with `os.path.realpath`, which removes `..` components and follows symlinks, then requires the result to lie inside `DICTIONARY_BASE_DIR = "/etc/edumfa"`. Otherwise it raises the existing `ConfigAdminError`. `RADIUSServer.request` passes the path through this helper before calling `Dictionary(...)`.

Why this works:
- Every use of the dictionary path goes through `request`, so the check also covers values already stored in the database and the test endpoint.
- The default `/etc/edumfa/dictionary` (the API default and the `radius.dictfile` default) stays inside the allowed directory, so default setups keep working.

Behaviour change: dictionaries stored outside `/etc/edumfa` are now rejected. This is an intentional restriction, but it is a real change for any deployment that relies on such a location.

## Patch

```diff
--- a/edumfa/lib/radiusserver.py
+++ b/edumfa/lib/radiusserver.py
@@ -27,2 +27,3 @@
 import logging
+import os
 from edumfa.lib.log import log_with
@@ -48,3 +49,26 @@
 
 
+# RADIUS dictionaries are only read from this directory. Paths outside of it
+# are rejected, so that a user who may write RADIUS server definitions cannot
+# make the server read arbitrary files.
+DICTIONARY_BASE_DIR = "/etc/edumfa"
+
+
+def _get_safe_dictionary_path(path):
+    """
+    Resolve the path of a RADIUS dictionary and make sure it is located
+    inside DICTIONARY_BASE_DIR. Symbolic links and ".." are resolved first.
+
+    :param path: The path of the RADIUS dictionary
+    :return: The resolved absolute path
+    :raises ConfigAdminError: if the path is outside of DICTIONARY_BASE_DIR
+    """
+    base_dir = os.path.realpath(DICTIONARY_BASE_DIR)
+    real_path = os.path.realpath(path)
+    if os.path.commonpath([base_dir, real_path]) != base_dir:
+        raise ConfigAdminError("The RADIUS dictionary must be located in "
+                               "{0!s}.".format(base_dir))
+    return real_path
+
+
 class RADIUSServer:
@@ -104,3 +128,3 @@
                      secret=to_bytes(decryptPassword(config.secret)),
-                     dict=Dictionary(r_dict))
+                     dict=Dictionary(_get_safe_dictionary_path(r_dict)))
 
```

## Self-assessment

```json
{"claim": 0, "confidence": 0.3}
```

Claim is 0 because I am not certain the dictionary path is the intended vulnerability, and the patch deliberately rejects dictionaries outside `/etc/edumfa`, which changes existing behaviour for those setups. I could not run the code or the tests, and pyrad's file-handling behaviour is not visible in the shown files.
