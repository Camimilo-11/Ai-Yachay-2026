## Vulnerability

**Type:** CWE-113, Improper Neutralization of CRLF Sequences in HTTP Headers (HTTP header injection / request splitting). CWE-113 is my best classification from the code shown, not something I verified against the upstream project.

**Location:**
- `tornado/curl_httpclient.py`, `_curl_setup_request`, where request headers are turned into the libcurl `HTTPHEADER` list (around lines 346-353).
- `tornado/http1connection.py`, `HTTP1Connection.write_headers`, the header-newline check (around lines 455-457).

**Root cause:** Header names and values are written to the wire without rejecting CR or LF characters.
- In the curl client, the header list is built directly from `request.headers.get_all()` and passed to `pycurl.HTTPHEADER`. Nothing checks for `\r` or `\n` before this.
- In the HTTP/1.1 connection, the only check is for `\n`. A bare `\r` in a header name or value passes the check and is written to the stream.

**How an attacker could exploit it:** If an application puts attacker-controlled text into a request header value (for example, a value that is copied from user input when proxying), the attacker can include `\r\n` followed by an extra header line. The curl client would send that extra header as-is, so the outgoing request contains a header the application did not intend to send. Whether this is fully exploitable depends on two things I could not check from the shown files: whether libcurl itself rejects CR/LF in custom headers, and how the receiving server parses bare CR characters.

```json
{"evidence": [
  {"file": "tornado/curl_httpclient.py", "line": 350, "quote": "% (native_str(k).encode(\"ASCII\"), native_str(v).encode(\"ISO8859-1\"))"},
  {"file": "tornado/curl_httpclient.py", "line": 351, "quote": "for k, v in request.headers.get_all()"},
  {"file": "tornado/curl_httpclient.py", "line": 347, "quote": "pycurl.HTTPHEADER,"},
  {"file": "tornado/http1connection.py", "line": 456, "quote": "if b\"\\n\" in line:"},
  {"file": "tornado/http1connection.py", "line": 457, "quote": "raise ValueError(\"Newline in header: \" + repr(line))"}
]}
```

## Fix

The patch makes two changes:

1. **curl client:** Before the `HTTPHEADER` list is built, each header name and value is checked for `\r` or `\n`. If either is found, the code raises `ValueError`. The existing `_process_queue` error path already turns setup exceptions into a 599 response, so this follows the existing error handling.
2. **HTTP/1.1 connection:** The newline check also rejects a bare `\r`, not just `\n`. It still raises the same `ValueError`.

Valid HTTP header field names and values cannot contain CR or LF, so rejecting them does not affect legitimate requests. The only behaviour change is that malformed headers, which were previously sent through, now raise an error.

## Patch

```diff
--- a/tornado/curl_httpclient.py
+++ b/tornado/curl_httpclient.py
@@ -342,6 +342,11 @@ class CurlAsyncHTTPClient(AsyncHTTPClient):
         # libcurl adds Pragma: no-cache by default; disable that too
         if "Pragma" not in request.headers:
             request.headers["Pragma"] = ""
 
+        for k, v in request.headers.get_all():
+            for s in (native_str(k), native_str(v)):
+                if "\r" in s or "\n" in s:
+                    raise ValueError("Illegal characters in header: %r" % (s,))
+
         curl.setopt(
             pycurl.HTTPHEADER,
--- a/tornado/http1connection.py
+++ b/tornado/http1connection.py
@@ -455,4 +455,4 @@ class HTTP1Connection(httputil.HTTPConnection):
         for line in lines:
-            if b"\n" in line:
+            if b"\r" in line or b"\n" in line:
                 raise ValueError("Newline in header: " + repr(line))
         future = None
```

## Self-assessment

```json
{"claim": 1, "confidence": 0.5}
```
