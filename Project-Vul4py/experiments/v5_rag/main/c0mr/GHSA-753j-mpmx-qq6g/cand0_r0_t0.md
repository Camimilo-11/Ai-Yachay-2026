## Vulnerability

**Type:** HTTP request smuggling caused by inconsistent header-name parsing (CWE-444). The header-name validation weakness is CWE-20.

**Location:** `tornado/httputil.py`, `HTTPHeaders.parse_line` (lines 179-184), with the consumer in `tornado/http1connection.py` (`_read_body`, line 600).

**Root cause:** `parse_line` takes everything before the first colon as the header name and passes it to `add()` without checking it. `add()` normalizes the name with `_normalize_header`, which splits on `-` and capitalizes each part but never strips whitespace. A name such as `"Content-Length "` (with a trailing space before the colon) therefore becomes the distinct key `"Content-Length "`. RFC 7230 §3.2.4 says such a name must be rejected, and the parser does not reject it.

**Exploit:** An attacker sends a request like:

```
POST / HTTP/1.1
Host: x
Content-Length : 11

hello world
```

Tornado stores the header under `"Content-Length "`. The lookup `"Content-Length" in headers` in `_read_body` then misses, so no body is consumed and the bytes are parsed as the next request on the keep-alive connection. A front-end proxy that trims whitespace before the colon, or that rejects the message, frames the request differently. This desynchronizes the two parsers, so the attacker can smuggle a second request past the proxy's access controls.

```json
{"evidence": [
  {"file": "tornado/httputil.py", "line": 181, "quote": "name, value = line.split(\":\", 1)"},
  {"file": "tornado/httputil.py", "line": 184, "quote": "self.add(name, value.strip())"},
  {"file": "tornado/httputil.py", "line": 139, "quote": "norm_name = _normalize_header(name)"},
  {"file": "tornado/httputil.py", "line": 75, "quote": "return \"-\".join([w.capitalize() for w in name.split(\"-\")])"},
  {"file": "tornado/httputil.py", "line": 218, "quote": "return self._dict[_normalize_header(name)]"},
  {"file": "tornado/http1connection.py", "line": 600, "quote": "if \"Content-Length\" in headers:"},
  {"file": "tornado/http1connection.py", "line": 591, "quote": "headers = httputil.HTTPHeaders.parse(data_str[eol:])"},
  {"file": "tornado/http1connection.py", "line": 294, "quote": "await self.stream.write(b\"HTTP/1.1 400 Bad Request\\r\\n\\r\\n\")"}
]}
```

## Fix

The patch adds a module-level regex for RFC 7230 `token` characters and uses it in `parse_line` to reject any header name that is not a non-empty token. A name with a space or tab before the colon, or any other invalid character, now raises `HTTPInputError`. The request then gets a 400 through the existing handler in `_read_message`, and the header is never stored under a mangled key.

Valid header names are unchanged, so existing behaviour is preserved. Continuation-line (obs-fold) handling, value parsing and `add()` are left as they are. The change does not touch the Content-Length or Transfer-Encoding framing logic in `http1connection.py`, even though the hints point there. I did not verify that framing logic against the upstream fix, and I cannot run tests here.

## Patch

```diff
--- a/tornado/httputil.py
+++ b/tornado/httputil.py
@@ -74,6 +74,9 @@ def _normalize_header(name: str) -> str:
     """
     return "-".join([w.capitalize() for w in name.split("-")])
 
 
+_HEADER_NAME_RE = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
+
+
 class HTTPHeaders(collections.abc.MutableMapping):
     """A dictionary that maintains ``Http-Header-Case`` for all keys.
@@ -179,6 +182,8 @@ class HTTPHeaders(collections.abc.MutableMapping):
         else:
             try:
                 name, value = line.split(":", 1)
             except ValueError:
                 raise HTTPInputError("no colon in header line")
+            if not _HEADER_NAME_RE.fullmatch(name):
+                raise HTTPInputError("invalid header name %r" % name)
             self.add(name, value.strip())
```

## Self-assessment

```json
{"claim": 1, "confidence": 0.4}
```
