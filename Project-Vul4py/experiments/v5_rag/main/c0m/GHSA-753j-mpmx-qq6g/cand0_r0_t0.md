## Vulnerability

- **Type:** HTTP request smuggling caused by inconsistent header parsing (CWE-444). The header-name check that would reject malformed names is missing (CWE-20 on the input side).
- **Location:** `tornado/httputil.py`, `HTTPHeaders.parse_line`, lines 176–179. The parsed header lines are consumed by `tornado/http1connection.py`, `_parse_headers` (line 590) and `_read_body` (line 599).
- **Root cause:** `parse_line` splits each header line at the first colon and passes the raw name straight to `add()` without validating it. A name with whitespace before the colon, such as `Content-Length : 5` or `Transfer-Encoding : chunked`, keeps that whitespace. `_normalize_header` only capitalizes each dash-separated segment, so `"Content-Length "` stays as a distinct key that does not match `"Content-Length"`. Tornado therefore does not see the framing header, treats the body as absent, and parses the body bytes as the next request on a keep-alive connection. A front-end proxy that trims the name would frame the message differently.
- **Exploit:** An attacker sends a request with `Content-Length : N` (or `Transfer-Encoding : chunked`) followed by a smuggled request. Tornado ignores the length header and handles the smuggled request as a separate request on the same connection, which can bypass proxy access controls or poison the response queue.

```json
{"evidence": [
  {"file": "tornado/httputil.py", "line": 176, "quote": "name, value = line.split(\":\", 1)"},
  {"file": "tornado/httputil.py", "line": 179, "quote": "self.add(name, value.strip())"},
  {"file": "tornado/httputil.py", "line": 71, "quote": "return \"-\".join([w.capitalize() for w in name.split(\"-\")])"},
  {"file": "tornado/http1connection.py", "line": 590, "quote": "headers = httputil.HTTPHeaders.parse(data_str[eol:])"},
  {"file": "tornado/http1connection.py", "line": 599, "quote": "if \"Content-Length\" in headers:"}
]}
```

## Fix

The patch validates the header name in `parse_line` before it is stored. A name must be a non-empty RFC 7230 token, so whitespace (including whitespace before the colon) and other separators are rejected. The rejection raises `HTTPInputError`. `_read_message` already catches that exception around `_parse_headers`, so a server responds with `400 Bad Request` and closes the connection. Names that are valid tokens are stored exactly as before, so normal traffic is unaffected. The only behaviour change is that malformed header lines, including empty names, are now rejected instead of silently stored under a mangled key.

## Patch

```diff
--- a/tornado/httputil.py
+++ b/tornado/httputil.py
@@ -174,8 +174,10 @@
         else:
             try:
                 name, value = line.split(":", 1)
             except ValueError:
                 raise HTTPInputError("no colon in header line")
+            if re.fullmatch(r"[-!#$%&'*+.^_`|~0-9A-Za-z]+", name) is None:
+                raise HTTPInputError("invalid header name: %r" % name)
             self.add(name, value.strip())
 
     @classmethod
```

## Self-assessment

```json
{"claim": 1, "confidence": 0.5}
```
