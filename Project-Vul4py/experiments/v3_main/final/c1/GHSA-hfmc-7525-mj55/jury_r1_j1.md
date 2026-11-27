## Review

### P1

**Removes the vulnerability: yes.**

- **Marker negotiation.** `_get_kex_ext_algs` adds `kex-strict-{c,s}-v00@openssh.com` only to the first KEXINIT, when `_session_id` is empty. `_process_kexinit` sets `_strict_kex` only if the peer's opposite-role marker is present, and only on the first exchange. The marker sits inside the KEXINIT payload, which is hashed into the exchange hash. An attacker who strips it therefore causes a key-exchange failure rather than a silent downgrade.
- **KEXINIT must be first.** `_process_kexinit` runs while `_recv_seq` still holds the current packet's sequence number, because the increment happens at the end of `_recv_packet` (line 1592). A packet injected before KEXINIT, such as an IGNORE, makes `_recv_seq` non-zero, so the patch raises `ProtocolError`.
- **Rollover bypass closed.** The added `seq == 0xffffffff and not self._recv_encryption` guard stops an attacker wrapping the counter back to 0 before KEXINIT.
- **Sequence reset at NEWKEYS.** Receive resets `_recv_seq` to 0 after handling `MSG_NEWKEYS`, which is when `_process_newkeys` installs the new keys. Send resets `_send_seq` to 0 right after writing NEWKEYS, at line 1646, before `send_newkeys` installs the new send encryption. Both directions therefore start at 0 under the new keys, and a dropped post-NEWKEYS packet breaks the MAC or cipher nonce. The flag persists across rekeys, so rekey is covered too.
- **Pre-keys filter.** In strict mode and before receive encryption is installed, any packet other than DISCONNECT or NEWKEYS outside the KEX range is rejected. A KEX-range packet that no handler processes raises instead of triggering UNIMPLEMENTED.

**Preserves functionality: yes.**

- **Non-strict peers.** Behaviour is unchanged for peers that do not negotiate strict KEX, apart from the pre-key rollover guard, which cannot be reached in practice.
- **Own traffic in strict mode.** asyncssh sends no IGNORE before NEWKEYS on the initial exchange, because IGNORE insertion requires `_send_encryption`. At rekey, `_recv_encryption` is set, so the filter is off. EXT_INFO is sent after NEWKEYS, so it is not affected.

**Response to reviewer 2.** The claim that rejecting IGNORE and DEBUG during the initial exchange breaks legitimate behaviour does not hold up. The strict-KEX specification forbids exactly those messages before the first NEWKEYS. That prohibition is what lets a dropped or injected packet be detected. Upstream's fix does the same. The pre-patch guard at line 1561 only rejected types above `MSG_KEX_LAST`, and that is the gap strict mode is meant to close. This restriction applies only when the peer has opted into strict KEX, so interoperability with strict peers (OpenSSH) is preserved. No concrete peer that negotiates strict KEX and still sends IGNORE or DEBUG during the initial exchange would be a conforming one.

**Response to reviewer 1.** I agree with its analysis, including the OpenSSH-matching semantics. The only residual risk it names is tests that reference the renamed private helper, which is not public API.

**Residual risk.** I could not run any tests.

## Verdict

```json
{"candidates": {"P1": {"removes_vulnerability": 1, "preserves_functionality": 1, "claim": 1, "confidence": 0.85, "evidence": [{"file": "asyncssh/connection.py", "line": 1592, "quote": "            self._recv_seq = (seq + 1) & 0xffffffff"}, {"file": "asyncssh/connection.py", "line": 1646, "quote": "        self._send_seq = (seq + 1) & 0xffffffff"}, {"file": "asyncssh/connection.py", "line": 1791, "quote": "        self.send_packet(MSG_NEWKEYS)"}, {"file": "asyncssh/connection.py", "line": 1504, "quote": "        seq = self._recv_seq"}], "counterexample": ""}}, "best": "P1"}
```
