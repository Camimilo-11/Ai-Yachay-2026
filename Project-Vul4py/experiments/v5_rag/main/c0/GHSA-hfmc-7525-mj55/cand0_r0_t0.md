## Vulnerability

**CWE-345: Insufficient Verification of Data Authenticity (Terrapin SSH prefix truncation).** In `asyncssh/connection.py`, `_recv_packet()` advances the receive sequence number for packets accepted before encryption is active, and `send_packet()` carries the send sequence number across `MSG_NEWKEYS`. The key exchange does not negotiate strict packet ordering or reset the counters at the key boundary. An on-path attacker can manipulate unauthenticated handshake traffic to alter packet accounting and, with susceptible encryption modes, suppress early encrypted messages without detection.

```json
{"evidence":[{"file":"asyncssh/connection.py","line":1534,"quote":"pkttype = packet.get_byte()"},{"file":"asyncssh/connection.py","line":1510,"quote":"if self._recv_encryption:"},{"file":"asyncssh/connection.py","line":1512,"quote":"seq, self._packet, rest, 4, mac)"},{"file":"asyncssh/connection.py","line":1555,"quote":"elif pkttype > MSG_KEX_LAST and not self._recv_encryption:"},{"file":"asyncssh/connection.py","line":1579,"quote":"processed = handler.process_packet(pkttype, seq, packet)"},{"file":"asyncssh/connection.py","line":1594,"quote":"self._recv_seq = (seq + 1) & 0xffffffff"},{"file":"asyncssh/connection.py","line":1648,"quote":"self._send_seq = (seq + 1) & 0xffffffff"},{"file":"asyncssh/connection.py","line":1792,"quote":"self.send_packet(MSG_NEWKEYS)"},{"file":"asyncssh/connection.py","line":1404,"quote":"return [b'ext-info-c' if self.is_client() else b'ext-info-s']"},{"file":"asyncssh/connection.py","line":2194,"quote":"if b'ext-info-c' in peer_kex_algs and not self._session_id:"},{"file":"asyncssh/connection.py","line":2199,"quote":"if b'ext-info-s' in peer_kex_algs and not self._session_id:"}]}
```

## Fix

Advertise and negotiate strict key exchange during the initial handshake. In strict mode, require `KEXINIT` to be the first packet, reject unexpected traffic until the first `NEWKEYS`, and reset each direction’s sequence number after its `NEWKEYS`, including on rekey. Reject receive-counter wraparound before encryption so it cannot make a later packet appear to be the first. Peers that do not advertise strict key exchange retain the legacy ordering and counter behavior for normal handshakes.

## Patch

```diff
--- a/asyncssh/connection.py
+++ b/asyncssh/connection.py
@@ -862,6 +862,7 @@
         self._kexinit_sent = False
         self._kex_complete = False
         self._ignore_first_kex = False
+        self._strict_kex = False
 
         self._gss: Optional[GSSBase] = None
         self._gss_kex = False
@@ -1399,9 +1400,15 @@
              b','.join(remote_algs).decode('ascii')))
 
-    def _get_ext_info_kex_alg(self) -> List[bytes]:
-        """Return the kex alg to add if any to request extension info"""
+    def _get_extra_kex_algs(self) -> List[bytes]:
+        """Return extension markers for the initial key exchange"""
 
-        return [b'ext-info-c' if self.is_client() else b'ext-info-s']
+        if self._session_id:
+            return []
+
+        if self.is_client():
+            return [b'ext-info-c', b'kex-strict-c-v00@openssh.com']
+        else:
+            return [b'ext-info-s', b'kex-strict-s-v00@openssh.com']
 
     def _send(self, data: bytes) -> None:
         """Send data to the SSH connection"""
@@ -1546,6 +1553,10 @@
             else:
                 skip_reason = 'kex not in progress'
                 exc_reason = 'Key exchange not in progress'
+        elif (self._strict_kex and not self._recv_encryption and
+                pkttype not in (MSG_NEWKEYS, MSG_DISCONNECT)):
+            skip_reason = 'invalid packet during initial kex'
+            exc_reason = 'Unexpected packet during initial key exchange'
         elif MSG_USERAUTH_FIRST <= pkttype <= MSG_USERAUTH_LAST:
             if self._auth:
                 handler = self._auth
@@ -1581,6 +1592,10 @@
                 raise ProtocolError(str(exc)) from None
 
             if not processed:
+                if self._strict_kex and not self._recv_encryption:
+                    raise ProtocolError('Unexpected packet during initial '
+                                        'key exchange')
+
                 self.logger.debug1('Unknown packet type %d received', pkttype)
                 self.send_packet(MSG_UNIMPLEMENTED, UInt32(seq))
 
@@ -1591,7 +1606,13 @@
             self._auth_final = True
 
         if self._transport:
-            self._recv_seq = (seq + 1) & 0xffffffff
+            if self._strict_kex and pkttype == MSG_NEWKEYS:
+                self._recv_seq = 0
+            elif seq == 0xffffffff and not self._recv_encryption:
+                raise ProtocolError('Sequence number wrapped before new keys')
+            else:
+                self._recv_seq = (seq + 1) & 0xffffffff
+
             self._recv_handler = self._recv_pkthdr
 
         return True
@@ -1645,7 +1666,11 @@
             mac = b''
 
         self._send(packet + mac)
-        self._send_seq = (seq + 1) & 0xffffffff
+
+        if self._strict_kex and pkttype == MSG_NEWKEYS:
+            self._send_seq = 0
+        else:
+            self._send_seq = (seq + 1) & 0xffffffff
 
         if self._kex_complete:
             self._rekey_bytes_sent += pktlen
@@ -1689,7 +1714,7 @@
 
         kex_algs = expand_kex_algs(self._kex_algs, gss_mechs,
                                    bool(self._server_host_key_algs)) + \
-                   self._get_ext_info_kex_alg()
+                   self._get_extra_kex_algs()
 
         host_key_algs = self._server_host_key_algs or [b'null']
 
@@ -2167,6 +2192,6 @@
                 set(extensions.get(b'server-sig-algs', b'').split(b','))
 
-    def _process_kexinit(self, _pkttype: int, _pktid: int,
+    def _process_kexinit(self, _pkttype: int, pktid: int,
                          packet: SSHPacket) -> None:
         """Process a key exchange request"""
 
@@ -2191,14 +2216,19 @@
         if self.is_server():
             self._client_kexinit = packet.get_consumed_payload()
-
-            if b'ext-info-c' in peer_kex_algs and not self._session_id:
-                self._can_send_ext_info = True
+            ext_info_alg = b'ext-info-c'
+            strict_kex_alg = b'kex-strict-c-v00@openssh.com'
         else:
             self._server_kexinit = packet.get_consumed_payload()
+            ext_info_alg = b'ext-info-s'
+            strict_kex_alg = b'kex-strict-s-v00@openssh.com'
 
-            if b'ext-info-s' in peer_kex_algs and not self._session_id:
-                self._can_send_ext_info = True
+        if not self._session_id:
+            self._can_send_ext_info = ext_info_alg in peer_kex_algs
+            self._strict_kex = strict_kex_alg in peer_kex_algs
+
+            if self._strict_kex and pktid != 0:
+                raise ProtocolError('Initial KEXINIT was not first')
 
         if self._kexinit_sent:
             self._kexinit_sent = False
         else:
```

## Self-assessment

```json
{"claim":1,"confidence":0.93}
```
