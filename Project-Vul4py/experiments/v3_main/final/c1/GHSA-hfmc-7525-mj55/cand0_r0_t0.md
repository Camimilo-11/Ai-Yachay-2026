## Vulnerability

**SSH transport prefix truncation (Terrapin, CWE-345)** in `asyncssh/connection.py`. The receive path counts packets before encryption is enabled and carries that sequence state into encrypted packet verification. The send path likewise advances its sequence number across `NEWKEYS` instead of resetting it. An active network attacker can exploit this gap to suppress early encrypted messages, such as extension negotiation, when a susceptible cipher and MAC mode is negotiated.

```json
{"evidence":[{"file":"asyncssh/connection.py","line":1314,"quote":"        self._inpbuf += data"},{"file":"asyncssh/connection.py","line":1504,"quote":"        seq = self._recv_seq"},{"file":"asyncssh/connection.py","line":1510,"quote":"                seq, self._packet, rest, 4, mac)"},{"file":"asyncssh/connection.py","line":1515,"quote":"            packet_data = self._packet[4:] + rest"},{"file":"asyncssh/connection.py","line":1577,"quote":"                processed = handler.process_packet(pkttype, seq, packet)"},{"file":"asyncssh/connection.py","line":1592,"quote":"            self._recv_seq = (seq + 1) & 0xffffffff"},{"file":"asyncssh/connection.py","line":1640,"quote":"            packet, mac = self._send_encryption.encrypt_packet(seq, hdr, packet)"},{"file":"asyncssh/connection.py","line":1646,"quote":"        self._send_seq = (seq + 1) & 0xffffffff"},{"file":"asyncssh/connection.py","line":1791,"quote":"        self.send_packet(MSG_NEWKEYS)"}]}
```

## Fix

Negotiate strict key exchange using the role-specific SSH extension markers. When negotiated, require `KEXINIT` to be the first inbound packet, reject unexpected packets during the initial exchange, and reset each direction’s sequence number immediately after that direction’s `NEWKEYS`, including at rekey. Also reject receive sequence rollover before keys are installed so it cannot bypass the first-packet check.

The patch leaves extension-info advertisement in place and retains legacy packet handling and sequence numbering for peers that do not negotiate strict key exchange, apart from the pre-key rollover guard. Those connections do not gain strict-mode protection. Tests were not run.

## Patch

```diff
diff --git a/asyncssh/connection.py b/asyncssh/connection.py
--- a/asyncssh/connection.py
+++ b/asyncssh/connection.py
@@ -859,6 +859,7 @@
         self._kexinit_sent = False
         self._kex_complete = False
         self._ignore_first_kex = False
+        self._strict_kex = False
 
         self._gss: Optional[GSSBase] = None
         self._gss_kex = False
@@ -1396,10 +1397,17 @@
             (alg_type, b','.join(local_algs).decode('ascii'),
              b','.join(remote_algs).decode('ascii')))
 
-    def _get_ext_info_kex_alg(self) -> List[bytes]:
-        """Return the kex alg to add if any to request extension info"""
+    def _get_kex_ext_algs(self) -> List[bytes]:
+        """Return the extension markers to advertise in KEXINIT"""
 
-        return [b'ext-info-c' if self.is_client() else b'ext-info-s']
+        if self.is_client():
+            ext_info = b'ext-info-c'
+            strict_kex = b'kex-strict-c-v00@openssh.com'
+        else:
+            ext_info = b'ext-info-s'
+            strict_kex = b'kex-strict-s-v00@openssh.com'
+
+        return [ext_info] if self._session_id else [ext_info, strict_kex]
 
     def _send(self, data: bytes) -> None:
         """Send data to the SSH connection"""
@@ -1544,6 +1552,10 @@
             else:
                 skip_reason = 'kex not in progress'
                 exc_reason = 'Key exchange not in progress'
+        elif (self._strict_kex and not self._recv_encryption and
+              pkttype not in (MSG_DISCONNECT, MSG_NEWKEYS)):
+            skip_reason = 'unexpected packet during initial key exchange'
+            exc_reason = 'Unexpected packet during strict key exchange'
         elif MSG_USERAUTH_FIRST <= pkttype <= MSG_USERAUTH_LAST:
             if self._auth:
                 handler = self._auth
@@ -1579,6 +1591,9 @@
                 raise ProtocolError(str(exc)) from None
 
             if not processed:
+                if self._strict_kex and not self._recv_encryption:
+                    raise ProtocolError('Unexpected key exchange packet')
+
                 self.logger.debug1('Unknown packet type %d received', pkttype)
                 self.send_packet(MSG_UNIMPLEMENTED, UInt32(seq))
 
@@ -1589,7 +1604,12 @@
             self._auth_final = True
 
         if self._transport:
-            self._recv_seq = (seq + 1) & 0xffffffff
+            if self._strict_kex and pkttype == MSG_NEWKEYS:
+                self._recv_seq = 0
+            elif seq == 0xffffffff and not self._recv_encryption:
+                raise ProtocolError('Sequence number wrapped before kex')
+            else:
+                self._recv_seq = (seq + 1) & 0xffffffff
             self._recv_handler = self._recv_pkthdr
 
         return True
@@ -1643,7 +1663,10 @@
             mac = b''
 
         self._send(packet + mac)
-        self._send_seq = (seq + 1) & 0xffffffff
+        if self._strict_kex and pkttype == MSG_NEWKEYS:
+            self._send_seq = 0
+        else:
+            self._send_seq = (seq + 1) & 0xffffffff
 
         if self._kex_complete:
             self._rekey_bytes_sent += pktlen
@@ -1687,7 +1710,7 @@
 
         kex_algs = expand_kex_algs(self._kex_algs, gss_mechs,
                                    bool(self._server_host_key_algs)) + \
-                   self._get_ext_info_kex_alg()
+                   self._get_kex_ext_algs()
 
         host_key_algs = self._server_host_key_algs or [b'null']
 
@@ -2199,7 +2222,16 @@
             if b'ext-info-s' in peer_kex_algs and not self._session_id:
                 self._can_send_ext_info = True
 
+        if not self._session_id:
+            strict_alg = (b'kex-strict-s-v00@openssh.com' if self.is_client()
+                          else b'kex-strict-c-v00@openssh.com')
+            self._strict_kex = strict_alg in peer_kex_algs
+
+            if self._strict_kex and self._recv_seq != 0:
+                raise ProtocolError('KEXINIT was not the first packet '
+                                    'in strict key exchange')
+
         if self._kexinit_sent:
             self._kexinit_sent = False
         else:
             self._send_kexinit()
```

## Self-assessment

```json
{"claim":1,"confidence":0.89}
```
