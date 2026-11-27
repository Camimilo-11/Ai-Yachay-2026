## Overview

`asyncssh/connection.py` contains shared connection machinery, client- and server-side SSH connection classes, their option classes, and module-level functions for opening connections and listeners. The shared connection class handles protocol state and SSH packet processing; the client and server subclasses provide role-specific operations. The module also defines the public entry points for establishing SSH connections, listening for them, and querying server authentication information.

## Components

### `asyncssh/connection.py`

- `SSHConnection(SSHPacketHandler, asyncio.Protocol)`: Shared connection implementation, including transport lifecycle, packet processing, key exchange, authentication coordination, and channel management.
- `SSHClientConnection(SSHConnection)`: Client-side connection implementation, with client authentication, session creation, and forwarding operations.
- `SSHServerConnection(SSHConnection)`: Server-side connection implementation, with client authentication validation, session handling, and forwarding operations.
- `SSHConnectionOptions(Options)`: Common connection configuration, including protocol algorithms, authentication settings, and timeouts.
- `SSHClientConnectionOptions(SSHConnectionOptions)`: Client-specific options, including identity, known-hosts, and session defaults.
- `SSHServerConnectionOptions(SSHConnectionOptions)`: Server-specific options, including host keys, authorized client keys, and session factories.
- `SSHAcceptor`: Wrapper around an asyncio server listener, with listener control and an `update()` method for options.
- `_connect(...)`: Internal coroutine that establishes an outbound connection using a socket, tunnel, proxy command, or direct connection.
- `_listen(...)`: Internal coroutine that creates an inbound listener directly or through a tunnel.
- `connect(...)`: Public coroutine for opening an SSH client connection.
- `connect_reverse(...)`: Public coroutine for opening a reverse-direction SSH connection.
- `listen(...)`: Public coroutine for starting an SSH server listener.
- `listen_reverse(...)`: Public coroutine for starting a reverse-direction SSH listener.
- `get_server_host_key(...)`: Public coroutine for retrieving a server host key during the SSH handshake.
- `get_server_auth_methods(...)`: Public coroutine for retrieving the server’s available authentication methods.

## Data flow and inputs

- Connection setup functions accept host and port arguments, optional sockets, tunnel and proxy settings, configuration paths, options objects, and keyword arguments.
- Connection option preparation combines caller-supplied values with configuration values and defaults; the client and server option classes each implement their own `prepare()` method.
- The connection receives network data through `data_received()`, appends it to an input buffer, and dispatches packet processing through the active receive handler.
- Outbound packets are assembled by `send_packet()` and written to the connection transport when one is present.
- Authentication and session behavior can involve callbacks or factories supplied through connection options or the owning client/server object.
- Client configuration can use the local username, environment variables, and files under the user’s `.ssh` directory; the server configuration can load host keys and authorized client keys.

## Behaviour to preserve

- Preserve the public coroutine entry points and their accepted arguments, including the distinction between client, server, and reverse-direction connections.
- Preserve the connection lifecycle contract: connection setup waits for the configured stage, and connection shutdown is exposed through `close()`, `abort()`, and `wait_closed()`.
- Preserve the client/server split: client connections expose client-oriented session and forwarding operations, while server connections process incoming requests and validate client authentication.
- Preserve packet handling and state transitions for version exchange, key exchange, authentication, channel operations, and global requests.
- Preserve option resolution behavior, including the use of configuration values and defaults when arguments are omitted.
- Preserve the client and server listener APIs, including `SSHAcceptor` methods such as `close()`, `wait_closed()`, and `update()`.

## Verified facts
- The module implements a shared SSH connection class using the asyncio protocol interface. (asyncssh/connection.py:620)
- The shared connection implementation routes inbound data through a receive handler. (asyncssh/connection.py:1097)
- Outgoing SSH packets are handled by the shared connection's send_packet method. (asyncssh/connection.py:862)
- The module defines a distinct SSH client connection subclass. (asyncssh/connection.py:1401)
- The client connection implementation provides a create_session coroutine. (asyncssh/connection.py:1692)
- The module defines a distinct SSH server connection subclass. (asyncssh/connection.py:2194)
- The server connection implementation provides a reload_config coroutine. (asyncssh/connection.py:2311)
- The module defines common connection options in SSHConnectionOptions. (asyncssh/connection.py:2899)
- The module defines client-specific options in SSHClientConnectionOptions. (asyncssh/connection.py:3093)
- The module defines server-specific options in SSHServerConnectionOptions. (asyncssh/connection.py:3580)
- SSHAcceptor provides methods to close the listener and wait for closure. (asyncssh/connection.py:574)
- The public connect coroutine creates a client connection and awaits _connect. (asyncssh/connection.py:4030)
- The public listen coroutine creates an SSHAcceptor through _listen. (asyncssh/connection.py:4235)
- The connection option preparation code uses SSHClientConfig.load to load client configuration. (asyncssh/connection.py:3372)
- The connection option preparation code uses SSHServerConfig.load to load server configuration. (asyncssh/connection.py:3905)
- Inbound data is appended to the connection input buffer before packet processing. (asyncssh/connection.py:1092)
- The connection writes outgoing bytes through its transport when the transport exists. (asyncssh/connection.py:844)
- The module-level get_server_host_key function returns an optional SSHKey. (asyncssh/connection.py:4386)
- The module-level get_server_auth_methods function returns a sequence of strings. (asyncssh/connection.py:4510)