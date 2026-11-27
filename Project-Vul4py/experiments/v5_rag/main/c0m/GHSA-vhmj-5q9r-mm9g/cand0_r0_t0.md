## Vulnerability

- **Type:** CWE-549, Missing Password Field Masking (plaintext display of a sensitive value). Low severity.
- **Location:** `edumfa/static/components/config/views/config.radius.edit.html`, the RADIUS "Secret" input (around lines 70-75 in the shown file).
- **Root cause:** The shared RADIUS secret input uses `type="secret"`, which is not a valid HTML input type. Browsers fall back to a plain text input, so the secret is shown in clear text as it is typed. The neighbouring password field (`type="password"`) is masked correctly, which makes this field the inconsistent one.
- **Exploit:** Anyone who can see the admin's screen, such as a shoulder-surfer, someone watching a screen share, or a screenshot, can read the RADIUS shared secret while it is entered or edited. That secret protects RADIUS traffic to the configured server.

**Caveat:** I could not confirm this is the intended vulnerability. The localization hint lists html lines 65 and 128, which do not match this file (line 65 is blank and the file ends near line 127). I found no other issue in the shown code that I can support with a verbatim quote, and I cannot run the application.

```json
{"evidence": [
  {"file": "edumfa/static/components/config/views/config.radius.edit.html", "line": 71, "quote": "<input name=\"secret\" class=\"form-control\""},
  {"file": "edumfa/static/components/config/views/config.radius.edit.html", "line": 72, "quote": "type=\"secret\""},
  {"file": "edumfa/static/components/config/views/config.radius.edit.html", "line": 106, "quote": "<input type=\"password\" class=\"form-control\" class=\"col\""}
]}
```

## Fix

Change the secret input's type from the invalid `"secret"` to `"password"`, matching the other password field in the same template. The browser then masks the value.

Behaviour is otherwise unchanged. `ng-model="params.secret"`, `required`, and the placeholder are untouched, so the value is still bound and submitted the same way.

## Patch

```diff
--- a/edumfa/static/components/config/views/config.radius.edit.html
+++ b/edumfa/static/components/config/views/config.radius.edit.html
@@ -70,5 +70,5 @@
         <div class="col-sm-9">
             <input name="secret" class="form-control"
-                   type="secret"
+                   type="password"
                    ng-model="params.secret"
                    required
```

## Self-assessment

```json
{"claim": 0, "confidence": 0.3}
```
