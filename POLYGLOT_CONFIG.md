## Configuration
* REQUIRED: Key:'api_key' Value: See [here](https://rachio.readme.io/v1.0/docs) for instructions on how to obtain Rachio API Key.
* REQUIRED: Key: 'host' Value: External address for polyglot server (External static IP or Dynamic DNS host name).  Not required or used for polyglot cloud.
* OPTIONAL: Key: 'port' Value: External port (integer) for polyglot server.  Note: This port must be opened through firewall and forwarded to the internal polyglot server.  Defaults to '3001' if no entry given but opening port is not optional (required for Rachio websockets).  ot required or used for polyglot cloud.
* OPTIONAL: Key:'nodeAdditionInterval' Value: On discovery, nodes will be added at this interval (in seconds).

Additional notes available on the [github page](https://github.com/fahrer16/udi-rachio-poly) for this node server
