## Vulnerability

HTTP request smuggling (CWE-444) in `tornado/http1connection.py` and `tornado/httputil.py`. The body reader treats an unsupported `Transfer-Encoding` as though no transfer encoding were present. The header parser also accepts invalid field names and strips whitespace beyond the spaces and tabs allowed in HTTP framing syntax.

An attacker can use this difference to make Tornado and an intermediary disagree about where a request ends. On a reused connection, Tornado can then interpret bytes that the intermediary considered part of the body as a separate request.

```json
{"evidence":[{"file":"tornado/http1connection.py","line":188,"quote":"header_future = self.stream.read_until_regex("},{"file":"tornado/http1connection.py","line":203,"quote":"start_line_str, headers = self._parse_headers(header_data)"},{"file":"tornado/http1connection.py","line":592,"quote":"headers = httputil.HTTPHeaders.parse(data_str[eol:])"},{"file":"tornado/httputil.py","line":170,"quote":"if line[0].isspace():"},{"file":"tornado/httputil.py","line":179,"quote":"name, value = line.split(\":\", 1)"},{"file":"tornado/httputil.py","line":182,"quote":"self.add(name, value.strip())"},{"file":"tornado/http1connection.py","line":613,"quote":"pieces = re.split(r\",\\s*\", headers[\"Content-Length\"])"},
{"file":"tornado/http1connection.py","line":647,"quote":"if headers.get(\"Transfer-Encoding\", \"\").lower() == \"chunked\":"},{"file":"tornado/http1connection.py","line":651,"quote":"return None"},{"file":"tornado/http1connection.py","line":561,"quote":"return connection_header != \"close\""},{"file":"tornado/http1connection.py","line":293,"quote":"except httputil.HTTPInputError as e:"},{"file":"tornado/http1connection.py","line":296,"quote":"await self.stream.write(b\"HTTP/1.1 400 Bad Request\\r\\n\\r\\n\")"},{"file":"tornado/http1connection.py","line":297,"quote":"self.close()"}]}
```

## Fix

Reject unsupported transfer encodings instead of falling back to a bodyless request. Require valid HTTP field names and recognize only space and tab as framing whitespace. Malformed requests use the existing `HTTPInputError` path, which sends a 400 response and closes the connection. The patch leaves valid fixed-length bodies, case-insensitive `chunked` framing, and bodyless requests unchanged.

## Patch

```diff
--- a/tornado/http1connection.py
+++ b/tornado/http1connection.py
@@ -610,7 +610,7 @@
                 # Proxies sometimes cause Content-Length headers to get
                 # duplicated.  If all the values are identical then we can
                 # use them but if they differ it's an error.
-                pieces = re.split(r",\s*", headers["Content-Length"])
+                pieces = re.split(r",[ \t]*", headers["Content-Length"])
                 if any(i != pieces[0] for i in pieces):
                     raise httputil.HTTPInputError(
                         "Multiple unequal Content-Lengths: %r"
@@ -644,7 +644,9 @@
 
         if content_length is not None:
             return self._read_fixed_body(content_length, delegate)
-        if headers.get("Transfer-Encoding", "").lower() == "chunked":
+        if "Transfer-Encoding" in headers:
+            if headers["Transfer-Encoding"].lower() != "chunked":
+                raise httputil.HTTPInputError("Unsupported Transfer-Encoding")
             return self._read_chunked_body(delegate)
         if self.is_client:
             return self._read_body_until_close(delegate)
--- a/tornado/httputil.py
+++ b/tornado/httputil.py
@@ -63,6 +63,9 @@
     import unittest  # noqa: F401
 
 
+_HEADER_NAME_RE = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
+
+
 @lru_cache(1000)
 def _normalize_header(name: str) -> str:
     """Map a header name to Http-Header-Case.
@@ -167,19 +170,21 @@
         >>> h.get('content-type')
         'text/html'
         """
-        if line[0].isspace():
+        if line[0] in " \t":
             # continuation of a multi-line header
             if self._last_key is None:
                 raise HTTPInputError("first header line cannot start with whitespace")
-            new_part = " " + line.lstrip()
+            new_part = " " + line.lstrip(" \t")
             self._as_list[self._last_key][-1] += new_part
             self._dict[self._last_key] += new_part
         else:
             try:
                 name, value = line.split(":", 1)
             except ValueError:
                 raise HTTPInputError("no colon in header line")
-            self.add(name, value.strip())
+            if not _HEADER_NAME_RE.fullmatch(name):
+                raise HTTPInputError("invalid header name")
+            self.add(name, value.strip(" \t"))
 
     @classmethod
     def parse(cls, headers: str) -> "HTTPHeaders":
```

## Self-assessment

```json
{"claim":1,"confidence":0.91}
```
