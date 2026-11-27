## Vulnerability

**Type:** CWE-113, Improper Neutralization of CRLF Sequences in HTTP Headers (HTTP request/header injection).

**Location:** `tornado/curl_httpclient.py`, `CurlAsyncHTTPClient._curl_setup_request`, where request headers are turned into the libcurl `HTTPHEADER` option (lines 347-354). The `http1connection.py` newline check at lines 453-455 is the protected counterpart.

**Root cause:** Each header name and value is encoded and joined as `b"%s: %s"`, then passed straight to `pycurl.HTTPHEADER`. Nothing checks for `\r` or `\n` in names or values. The non-curl path (`HTTP1Connection.write_headers`) rejects any header line containing `\n`, but the curl path has no such check. Only `\n` is rejected on the HTTP/1 side, so a bare `\r` is accepted there too.

**Exploit:** If an application copies attacker-influenced data into a request header value (for example a query parameter, a redirect target, or a proxied header), an attacker can supply `%0d%0a`. The decoded value contains CR/LF, so the curl client emits extra header lines or a complete smuggled request on the same connection. This can add or override headers such as `Authorization` or `Host`, or split requests against a backend. I could not confirm whether `HTTPHeaders` insertion in `httputil.py` rejects CR/LF, because that file is not shown. I also assume libcurl forwards custom header strings verbatim, as the code implies but I cannot verify here. The exploit path depends on the application feeding untrusted data into headers.

```json
{"evidence": [
  {"file": "tornado/curl_httpclient.py", "line": 348, "quote": "pycurl.HTTPHEADER,"},
  {"file": "tornado/curl_httpclient.py", "line": 351, "quote": "% (native_str(k).encode(\"ASCII\"), native_str(v).encode(\"ISO8859-1\"))"},
  {"file": "tornado/curl_httpclient.py", "line": 352, "quote": "for k, v in request.headers.get_all()"},
  {"file": "tornado/curl_httpclient.py", "line": 247, "quote": "callback(HTTPResponse(request=request, code=599, error=e))"},
  {"file": "tornado/http1connection.py", "line": 454, "quote": "if b\"\\n\" in line:"},
  {"file": "tornado/http1connection.py", "line": 455, "quote": "raise ValueError(\"Newline in header: \" + repr(line))"}
]}
```

## Fix

The patch adds the same kind of check to both header-writing paths.

- **`curl_httpclient.py`:** The header byte-lines are built into a list first. Each line is then checked for `\r` or `\n`, and a `ValueError` is raised on a match. `_process_queue` already wraps `_curl_setup_request` in `try/except Exception` and returns the error as a 599 response, so an injected header fails the request cleanly. Valid headers produce the same list as before and are passed to `HTTPHEADER` unchanged.
- **`http1connection.py`:** The existing newline check also rejects `\r`, closing the bare-CR gap.

Valid HTTP header names and values never contain CR or LF, so no legitimate request changes behaviour. The hint lines 456-457 in `http1connection.py` were the basis for the second hunk, but my line numbering of that file may be off by a line or two, so the hunk relies on its context lines to apply.

## Patch

```diff
--- a/tornado/curl_httpclient.py
+++ b/tornado/curl_httpclient.py
@@ -345,13 +345,14 @@
             request.headers["Pragma"] = ""
 
-        curl.setopt(
-            pycurl.HTTPHEADER,
-            [
-                b"%s: %s"
-                % (native_str(k).encode("ASCII"), native_str(v).encode("ISO8859-1"))
-                for k, v in request.headers.get_all()
-            ],
-        )
+        header_lines = [
+            b"%s: %s"
+            % (native_str(k).encode("ASCII"), native_str(v).encode("ISO8859-1"))
+            for k, v in request.headers.get_all()
+        ]
+        for line in header_lines:
+            if b"\r" in line or b"\n" in line:
+                raise ValueError("Newline in header: " + repr(line))
+        curl.setopt(pycurl.HTTPHEADER, header_lines)
 
         curl.setopt(
             pycurl.HEADERFUNCTION,
--- a/tornado/http1connection.py
+++ b/tornado/http1connection.py
@@ -453,3 +453,3 @@
         for line in lines:
-            if b"\n" in line:
+            if b"\r" in line or b"\n" in line:
                 raise ValueError("Newline in header: " + repr(line))
```

## Self-assessment

```json
{"claim": 1, "confidence": 0.6}
```
